"""Integrations, shown as "Master vN" (spec 004; v2 design D5). URLs say /stacks to keep /masters for
calibration masters (spec 001). No `from __future__ import annotations` here: see substation.api."""

from datetime import date, datetime
from pathlib import Path
from typing import Literal

from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.catalogue.api import router
from apps.catalogue.models import Dataset
from substation.api import ApiError, Schema, Status
from substation.tasks import enqueue
from substation.tasks.models import Task, TaskStatus

from . import masters as svc
from .annotation_schemas import AnnotationOut, AnnotationsOut
from .models import Master, MasterMember, MasterState

Rule = Literal["default", "accepted", "graded", "everything"]


class StackOptions(Schema):
    rejection: Literal["winsorized", "sigma", "linear"] | None = None
    weighting: Literal["grade", "snr", "equal"] | None = None
    reference: Literal["best_fwhm", "most_stars"] | None = None
    # 004-DR-35: Drizzle ×2 (twice the width and height) or Bin 2×2 (half), else the subs' own resolution
    resolution: Literal["normal", "drizzle2", "bin2"] | None = None


class StackIn(Schema):
    rule: Rule = "default"
    nights: list[date] | None = None
    date_from: date | None = None  # 004 T008: a date range instead of (or as well as) chosen nights
    date_to: date | None = None
    datasets: list[int] | None = None  # more datasets of the same target, filter, camera and telescope
    include: list[str] | None = None  # 004 T009: subs to use whatever their grade
    exclude: list[str] | None = None  # subs to leave out whatever their grade
    options: StackOptions | None = None  # this master only; Settings → Stacking holds the defaults (004 T016)


class StackPreviewOut(Schema):
    subs: int
    integration_s: float
    nights: int
    excluded: int
    not_calibrated: int
    rule_text: str
    sharpness_note: str = ""


class StackOut(Schema):
    id: int
    dataset_id: int
    version: int
    state: str
    state_reason: str
    rule: str
    rule_text: str
    nights: list[date] | None
    step: str
    progress: float
    steps: list[str]
    sub_count: int
    session_count: int
    integration_s: float
    report: dict
    error: str | None
    has_preview: bool
    file_path: str = ""  # where the master is on the server; the UI maps it to the viewer's own drive
    created_by: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    engine_version: str
    method: str
    resolution: str = "normal"  # normal, drizzle2 or bin2 (004-DR-35)


def stack_out(m: Master) -> StackOut:
    rule = m.recipe.get("rule", "default")
    nights = m.recipe.get("nights")
    return StackOut(
        id=m.pk,
        dataset_id=m.dataset_id,
        version=m.version,
        state=m.state,
        state_reason=m.state_reason,
        rule=rule,
        rule_text=svc.RULES.get(rule, rule),
        nights=[date.fromisoformat(n) for n in nights] if nights else None,
        step=m.step,
        progress=m.progress,
        steps=svc.STEPS,
        sub_count=m.sub_count,
        session_count=m.session_count,
        integration_s=m.integration_s,
        report=m.report or {},
        error=m.error,
        has_preview=bool(m.preview_path),
        file_path=m.output_path or "",
        created_by=m.created_by.get_username() if m.created_by else None,
        created_at=m.created_at,
        started_at=m.started_at,
        finished_at=m.finished_at,
        engine_version=m.engine_version,
        method=method(m),
        resolution=svc.resolution_of(m),
    )


def method(m: Master) -> str:
    """ "winsorised σ 3.0 · grade weights" (004-DR-03)."""
    o = m.recipe.get("options", {})
    lo, hi = (o.get("sigma") or [3.0, 3.0])[:2]
    sigma = f"{lo:g}" if lo == hi else f"{lo:g}/{hi:g}"
    weights = {"grade": "grade weights", "snr": "noise weights", "equal": "equal weights"}.get(
        o.get("weighting", "grade"), "grade weights"
    )
    rej = {"winsorized": "winsorised", "sigma": "sigma clipping", "linear": "linear fit clipping"}.get(
        o.get("rejection", "winsorized"), "winsorised"
    )
    res = svc.RESOLUTIONS.get(svc.resolution_of(m), "")
    return f"{rej} σ {sigma} · {weights}" + (f" · {res}" if res else "")


@router.get("/datasets/{id}/stacks", response=list[StackOut])
def list_stacks(request, id: int):  # noqa: A002
    svc.reconcile_states()
    get_object_or_404(Dataset, pk=id)
    return [
        stack_out(m)
        for m in Master.objects.filter(dataset_id=id)
        .exclude(state=MasterState.DELETED)
        .select_related("created_by")
        .order_by("-version")
    ]


class PartnerOut(Schema):
    id: int
    label: str
    subs: int
    collection: str | None


@router.get("/datasets/{id}/stack-partners", response=list[PartnerOut])
def stack_partners(request, id: int):  # noqa: A002
    """Datasets that can be stacked with this one (004 T008): same target, filter, camera and telescope (another
    rig name or panel split that grouped them apart)."""
    from apps.catalogue.api_library import label

    ds = get_object_or_404(Dataset, pk=id)
    qs = (
        Dataset.objects.filter(
            target=ds.target,
            filter_norm=ds.filter_norm,
            camera=ds.camera,
            telescope=ds.telescope,
            sub_count__gt=0,
        )
        .exclude(pk=ds.pk)
        .select_related("rig", "collection")
    )
    return [
        PartnerOut(
            id=d.pk, label=label(d), subs=d.sub_count, collection=d.collection.name if d.collection else None
        )
        for d in qs
        if not svc.stackable_with(ds, d)
    ]


@router.post("/datasets/{id}/stacks/preview", response=StackPreviewOut)
def preview_stack(request, id: int, body: StackIn):  # noqa: A002
    ds = get_object_or_404(Dataset, pk=id)
    try:
        out = svc.preview(ds, body.nights, body.rule, _scope(body))
    except ValueError as e:
        raise ApiError(422, "cannot_stack", str(e)) from None
    return StackPreviewOut(**out, rule_text=svc.RULES[body.rule])


def _scope(body: StackIn) -> dict:
    return {
        k: v
        for k, v in {
            "date_from": body.date_from and body.date_from.isoformat(),
            "date_to": body.date_to and body.date_to.isoformat(),
            "datasets": body.datasets,
            "include": body.include,
            "exclude": body.exclude,
        }.items()
        if v
    }


@router.post("/datasets/{id}/stacks", response={201: StackOut})
def start_stack(request, id: int, body: StackIn):  # noqa: A002
    ds = get_object_or_404(Dataset, pk=id)
    try:
        opts = {k: v for k, v in (body.options.dict() if body.options else {}).items() if v is not None}
        m = svc.start(ds, body.nights, body.rule, request.user, opts or None, _scope(body))
    except ValueError as e:
        raise ApiError(422, "cannot_stack", str(e)) from None
    return Status(201, stack_out(m))


class CompareRow(Schema):
    label: str
    a: float | None
    b: float | None
    unit: str
    better: Literal["a", "b", "same", ""]  # which is better on this measure ("" when it can't be said)


class CompareOut(Schema):
    a: int
    b: int
    a_label: str
    b_label: str
    rows: list[CompareRow]
    summary: str


def _better(a: float | None, b: float | None, lower_is_better: bool, tol: float = 0.03) -> str:
    if a is None or b is None or not a or not b:
        return ""
    if abs(a - b) / max(abs(a), abs(b)) < tol:
        return "same"
    return ("a" if a < b else "b") if lower_is_better else ("a" if a > b else "b")


@router.get("/stacks/compare", response=CompareOut)
def compare_stacks(request, a: int, b: int):
    """Two masters side by side (004 T006): integration, subs, stars, sharpness and roundness overall and by region.
    Noise is shown but never decides on its own: it depends on integration and on the stretch, not quality alone."""
    ma, mb = get_object_or_404(Master, pk=a), get_object_or_404(Master, pk=b)
    ra, rb = ma.report or {}, mb.report or {}

    def zone(r: dict, z: str, k: str) -> float | None:
        return ((r.get("regional") or {}).get("zones") or {}).get(z, {}).get(k)

    rows = [
        CompareRow(
            label="Integration",
            a=round((ma.integration_s or 0) / 3600, 2),
            b=round((mb.integration_s or 0) / 3600, 2),
            unit="h",
            better=_better(ma.integration_s, mb.integration_s, False),  # type: ignore[arg-type]
        ),
        CompareRow(label="Subs", a=ma.sub_count, b=mb.sub_count, unit="", better=""),
        CompareRow(
            label="Stars detected",
            a=ra.get("stars"),
            b=rb.get("stars"),
            unit="",
            better=_better(ra.get("stars"), rb.get("stars"), False, 0.05),  # type: ignore[arg-type]
        ),
        CompareRow(
            label="FWHM",
            a=ra.get("fwhm_arcsec"),
            b=rb.get("fwhm_arcsec"),
            unit="″",
            better=_better(ra.get("fwhm_arcsec"), rb.get("fwhm_arcsec"), True),  # type: ignore[arg-type]
        ),
        CompareRow(
            label="Roundness",
            a=ra.get("roundness"),
            b=rb.get("roundness"),
            unit="",
            better=_better(ra.get("roundness"), rb.get("roundness"), False, 0.01),  # type: ignore[arg-type]
        ),
    ]
    for z, name in (
        ("centre", "Centre"),
        ("top_left", "Top left"),
        ("top_right", "Top right"),
        ("bottom_left", "Bottom left"),
        ("bottom_right", "Bottom right"),
    ):
        za, zb = zone(ra, z, "fwhm_px"), zone(rb, z, "fwhm_px")
        if za is not None or zb is not None:
            rows.append(
                CompareRow(
                    label=f"FWHM {name.lower()}",
                    a=za,
                    b=zb,
                    unit=" px",
                    better=_better(za, zb, True, 0.05),  # type: ignore[arg-type]
                )
            )
    rows.append(
        CompareRow(label="Background noise", a=ra.get("noise"), b=rb.get("noise"), unit=" ADU", better="")
    )
    va, vb = f"v{ma.version}", f"v{mb.version}"
    wins = {"a": [r.label for r in rows if r.better == "a"], "b": [r.label for r in rows if r.better == "b"]}
    if not ra or not rb:
        summary = "Not finished yet."
    elif not wins["a"] and not wins["b"]:
        summary = f"{va} and {vb} are level on every measure."
    else:
        bits = [
            f"{v} is better on {', '.join(w).lower()}" for v, w in ((va, wins["a"]), (vb, wins["b"])) if w
        ]
        summary = "; ".join(bits) + ". Noise isn't judged on its own."
    return CompareOut(
        a=ma.pk,
        b=mb.pk,
        a_label=f"{ma.dataset.display_name} {va}",
        b_label=f"{mb.dataset.display_name} {vb}",
        rows=rows,
        summary=summary,
    )


@router.post("/stacks/{id}/rerun", response={201: StackOut})
def rerun_stack(request, id: int):  # noqa: A002
    old = get_object_or_404(Master, pk=id)
    nights = [date.fromisoformat(n) for n in old.recipe.get("nights") or []] or None
    try:
        m = svc.start(
            old.dataset,
            nights,
            old.recipe.get("rule", "default"),
            request.user,
            old.recipe.get("options"),
            svc.scope_of(old.recipe),
        )
    except ValueError as e:
        raise ApiError(422, "cannot_stack", str(e)) from None
    return Status(201, stack_out(m))


@router.post("/stacks/{id}/cancel", response=StackOut)
def cancel_stack(request, id: int):  # noqa: A002
    m = get_object_or_404(Master, pk=id)
    if m.state not in (MasterState.QUEUED, MasterState.RUNNING):
        raise ApiError(409, "not_running", "This master isn't being integrated.")
    who = f"Cancelled by {request.user.get_username()}."
    jobs = (
        Task.objects.filter(pk=m.task_id)
        if m.task_id
        else Task.objects.filter(name__endswith="masters.integrate", args__0=m.pk)
    )
    if m.state == MasterState.RUNNING:
        # Siril is stopped at its next check (within a few seconds); the integration marks itself cancelled
        jobs.filter(status=TaskStatus.RUNNING).update(cancel_requested=True)
        m.state_reason = who
        m.save(update_fields=["state_reason"])
        return stack_out(m)
    jobs.filter(status=TaskStatus.READY).update(status=TaskStatus.CANCELLED, finished_at=timezone.now())
    m.state, m.state_reason = MasterState.CANCELLED, who
    m.save(update_fields=["state", "state_reason"])
    return stack_out(m)


@router.delete("/stacks/{id}", response={204: None})
def delete_stack(request, id: int):  # noqa: A002
    m = get_object_or_404(Master, pk=id)
    if m.state == MasterState.RUNNING:
        raise ApiError(409, "running", "Still integrating. Wait for it to finish.")
    for p in (m.output_path, m.preview_path):
        if p:
            Path(p).unlink(missing_ok=True)
            Path(p).with_name(Path(p).stem + "_t.jpg").unlink(missing_ok=True)
    # the record stays (constitution VIII): who deleted it and when; only SubStation's own files go
    m.state, m.deleted_by, m.deleted_at = MasterState.DELETED, request.user, timezone.now()
    m.state_reason = f"Deleted by {request.user.get_username()}."
    m.output_path = m.preview_path = ""
    m.save(update_fields=["state", "deleted_by", "deleted_at", "state_reason", "output_path", "preview_path"])
    return Status(204, None)


class MemberOut(Schema):
    sha256: str
    file: str
    night: date | None
    included: bool
    weight: float
    reason: str


@router.get("/stacks/{id}/inputs", response=list[MemberOut])
def stack_inputs(request, id: int):  # noqa: A002
    m = get_object_or_404(Master, pk=id)
    out = []
    for mm in (
        MasterMember.objects.filter(master=m).select_related("frame__night").prefetch_related("frame__copies")
    ):
        c = next(iter(mm.frame.copies.all()), None)
        out.append(
            MemberOut(
                sha256=mm.frame_id,
                file=c.rel_path.rsplit("/", 1)[-1] if c else mm.frame_id[:12],
                night=mm.frame.night.date if mm.frame.night else None,
                included=mm.included,
                weight=mm.weight,
                reason=mm.reason,
            )
        )
    return out


class StackDetailOut(Schema):
    method: str
    full: int
    weighted: int
    left_out: int
    left_out_reasons: dict[str, int]
    output_path: str | None
    engine_version: str
    notes: list[str]
    calibration: list[dict]
    regional: dict = {}


@router.get("/stacks/{id}/detail", response=StackDetailOut)
def stack_detail(request, id: int):  # noqa: A002
    """What went into a master and how (004-DR-04)."""
    from collections import Counter

    from apps.catalogue.models import Copy

    from .models import SubMeasurement

    m = get_object_or_404(Master, pk=id)
    members = list(
        MasterMember.objects.filter(master=m).values_list("frame_id", "included", "weight", "reason")
    )
    inc = [x for x in members if x[1]]
    used: Counter[tuple[str, str]] = Counter()
    for dark, flat in SubMeasurement.objects.filter(frame_id__in=[x[0] for x in inc]).values_list(
        "dark_id", "flat_id"
    ):
        for kind, sha in (("dark", dark), ("flat", flat)):
            if sha:
                used[(kind, sha)] += 1
    names = {
        c.frame_id: c.rel_path.rsplit("/", 1)[-1]
        for c in Copy.objects.filter(frame_id__in=[k[1] for k in used], present=True)
    }
    return StackDetailOut(
        method=method(m),
        full=sum(1 for x in inc if x[2] >= 0.999),
        weighted=sum(1 for x in inc if x[2] < 0.999),
        left_out=len(members) - len(inc),
        left_out_reasons=dict(Counter(x[3] or "left out" for x in members if not x[1])),
        output_path=m.output_path or None,
        engine_version=m.engine_version or "",
        notes=list((m.report or {}).get("notes") or []),
        calibration=[
            {"kind": k, "file": names.get(sha, sha[:12]), "subs": n, "sha256": sha}
            for (k, sha), n in used.most_common()
        ],
        regional=(m.report or {}).get("regional") or {},
    )


@router.get("/stacks/{id}/preview", response={200: None, 404: None})
def stack_preview(request, id: int, size: Literal["screen", "thumb"] = "screen"):  # noqa: A002
    m = get_object_or_404(Master, pk=id)
    p = Path(m.preview_path) if m.preview_path else None
    if p is not None and size == "thumb":
        p = p.with_name(p.stem + "_t.jpg")
    if p is None or not p.exists():
        return HttpResponse(status=404)
    return FileResponse(p.open("rb"), content_type="image/jpeg")


@router.get("/stacks/{id}/download", response={200: None, 404: None})
def stack_download(request, id: int):  # noqa: A002
    m = get_object_or_404(Master, pk=id)
    p = Path(m.output_path) if m.output_path else None
    if p is None or not p.exists():
        return HttpResponse(status=404)
    name = f"{m.dataset.display_name.replace(' · ', '_').replace(' ', '')}_master_v{m.version}.fit"
    return FileResponse(p.open("rb"), as_attachment=True, filename=name)


# ---- combined masters (004-DR-05, T022) ---------------------------------------------------------------------
class CombinedInput(Schema):
    master: int
    dataset: int
    label: str
    version: int | None = None
    integration_s: float | None = None
    subs: int | None = None
    registered: bool | None = None
    stale: bool | None = None  # an older master (newer subs since), used as it is


class CombinedOut(Schema):
    id: int
    filter: str
    version: int
    method: str = "stack"  # 004-DR-32: stitch (a mosaic's panels on one canvas) or stack (one field, deeper)
    state: str
    state_reason: str
    stale: str
    integration_s: float
    inputs: list[CombinedInput]
    error: str | None
    finished_at: datetime | None
    has_preview: bool
    file_path: str = ""


class CombinedPlanOut(Schema):
    method: str = "stack"  # the operation this plan is for (004-DR-32)
    default_method: str = "stack"  # the one that fits the project: stitch for a mosaic
    methods: list[str] = ["stack"]  # the ones that make sense here
    reference: int | None
    reference_label: str | None = None
    filters: dict[str, list[CombinedInput]]
    left_out: list[str] = []
    notes: list[str] = []
    combined: list[CombinedOut]


def _combined_out(c) -> CombinedOut:  # noqa: ANN001
    from .combine import staleness

    return CombinedOut(
        id=c.pk,
        filter=c.filter_norm,
        version=c.version,
        method=c.method,
        state=c.state,
        state_reason=c.state_reason,
        stale=staleness(c),
        integration_s=c.integration_s,
        inputs=c.inputs,
        error=c.error,
        finished_at=c.finished_at,
        has_preview=bool(c.preview_path),
        file_path=getattr(c, "output_path", "") or "",
    )


@router.get("/collections/{id}/combined", response=CombinedPlanOut)
def combined_masters(
    request,
    id: int,  # noqa: A002
    project: int | None = None,
    method: Literal["stitch", "stack"] | None = None,
):
    """What Stitch mosaic or Stack together would use (the project's kind chooses when `method` isn't given), and
    the masters made so far (latest per filter)."""
    from apps.catalogue.models import Collection

    from .combine import plan, shown_combined

    col = get_object_or_404(Collection, pk=id)
    return CombinedPlanOut(
        **plan(col, project, method), combined=[_combined_out(c) for c in shown_combined(col, project)]
    )


class CombineIn(Schema):
    # 004-DR-34: only these filters are stitched or stacked (all of the plan's when empty); a mosaic's canvas still
    # covers every panel of every filter, so a filter made later lines up pixel for pixel
    filters: list[str] | None = None


@router.post("/collections/{id}/combined", response={201: list[CombinedOut]})
def start_combined(
    request,
    id: int,  # noqa: A002
    project: int | None = None,
    method: Literal["stitch", "stack"] | None = None,
    body: CombineIn | None = None,
):
    """Stitch mosaic or Stack together, for the chosen filters of the project (004-DR-32, -34)."""
    from apps.catalogue.models import Collection

    from .combine import start

    col = get_object_or_404(Collection, pk=id)
    try:
        rows = start(col, project, method, body.filters if body else None)
    except ValueError as e:
        raise ApiError(422, "cannot_combine", str(e)) from None
    return Status(201, [_combined_out(c) for c in rows])


@router.get("/combined/{id}/preview", response={200: None, 404: None})
def combined_preview(request, id: int, size: Literal["screen", "thumb"] = "screen"):  # noqa: A002
    from .models import CombinedMaster

    c = get_object_or_404(CombinedMaster, pk=id)
    p = Path(c.preview_path) if c.preview_path else None
    if p is not None and size == "thumb":
        p = p.with_name(p.stem + "_t.jpg")
    if p is None or not p.exists():
        return HttpResponse(status=404)
    return FileResponse(p.open("rb"), content_type="image/jpeg")


@router.get("/combined/{id}/download", response={200: None, 404: None})
def combined_download(request, id: int):  # noqa: A002
    from .models import CombinedMaster

    c = get_object_or_404(CombinedMaster, pk=id)
    p = Path(c.output_path) if c.output_path else None
    if p is None or not p.exists():
        return HttpResponse(status=404)
    return FileResponse(p.open("rb"), as_attachment=True, filename=p.name)


@router.delete("/combined/{id}", response={204: None})
def delete_combined(request, id: int):  # noqa: A002
    """Delete a combined master's output: its file and preview go, the row stays as the record (state deleted)."""
    from apps.accounts.roles import no_viewers

    from .models import CombinedMaster

    no_viewers(request, "Read-only users can't delete masters.")
    c = get_object_or_404(CombinedMaster, pk=id)
    if c.state in (MasterState.QUEUED, MasterState.RUNNING):
        raise ApiError(409, "running", "Still combining. Wait for it to finish, or cancel it.")
    for p in (c.output_path, c.preview_path):
        if p:
            Path(p).unlink(missing_ok=True)
            Path(p).with_name(Path(p).stem + "_t.jpg").unlink(missing_ok=True)
    c.state = MasterState.DELETED
    c.state_reason = f"Deleted by {request.user.get_username()}."
    c.output_path = c.preview_path = ""
    c.save(update_fields=["state", "state_reason", "output_path", "preview_path"])
    return Status(204, None)


# ---- 100% views of masters and palettes (owner 2026-10-10) --------------------------------------------------
class IntegrationPart(Schema):
    """One input of a stitched or stacked master (a panel, a dataset's master), or one filter of a palette."""

    label: str
    filter: str = ""
    panel: int | None = None
    integration_s: float
    subs: int
    used: bool = True  # false: left out (its stars couldn't be matched to the rest)


class IntegrationOut(Schema):
    """What a master holds, for the viewer's side panel (004-DR-36, 010-DR-30)."""

    kind: Literal["master", "stitch", "stack", "palette"]
    filter: str = ""
    integration_s: float
    subs: int
    sessions: int | None = None  # a dataset master's nights
    parts: list[IntegrationPart] = []  # per panel or master (stitched, stacked); per filter (a palette)


class LookOut(Schema):
    ready: bool
    generating: bool = False
    failed: bool = False  # the last attempt to draw it failed; `note` says why
    full: str | None = None
    inspector: str | None = None
    note: str = ""
    integration: IntegrationOut | None = None  # masters, stitched or stacked masters and palettes


def master_integration(m: Master) -> IntegrationOut:
    return IntegrationOut(
        kind="master",
        filter=m.dataset.filter_norm or "",
        integration_s=m.integration_s,
        subs=m.sub_count,
        sessions=m.session_count,
    )


def combined_integration(c) -> IntegrationOut:  # noqa: ANN001
    """Per input (a mosaic's panels, the masters stacked together), the ones left out marked; the total counts the
    ones used."""
    from .combine import STITCH

    panels = dict(
        Dataset.objects.filter(pk__in=[i.get("dataset") for i in c.inputs]).values_list("pk", "panel")
    )
    parts = [
        IntegrationPart(
            label=str(i.get("label") or ""),
            filter=c.filter_norm,
            panel=panels.get(i.get("dataset")),
            integration_s=float(i.get("integration_s") or 0),
            subs=int(i.get("subs") or 0),
            used=i.get("registered") is not False,
        )
        for i in c.inputs
    ]
    parts.sort(key=lambda p: (not p.used, p.panel if p.panel is not None else 1 << 16, -p.integration_s))
    used = [p for p in parts if p.used]
    return IntegrationOut(
        kind="stitch" if c.method == STITCH else "stack",
        filter=c.filter_norm,
        integration_s=sum(p.integration_s for p in used),
        subs=sum(p.subs for p in used),
        parts=parts,
    )


def palette_integration(collection_id: int, project_id: int | None, name: str) -> IntegrationOut | None:
    """Per filter: the stitched or stacked master each colour comes from."""
    from .combine import in_project
    from .models import CombinedMaster
    from .tasks import PALETTES

    parts = []
    for filt in dict.fromkeys(PALETTES[name].values()):
        cm = (
            CombinedMaster.objects.filter(
                collection_id=collection_id,
                filter_norm=filt,
                state=MasterState.CURRENT,
                **in_project(project_id),
            )
            .order_by("-version")
            .first()
        )
        if cm is None:
            return None
        one = combined_integration(cm)
        parts.append(IntegrationPart(label=filt, filter=filt, integration_s=one.integration_s, subs=one.subs))
    return IntegrationOut(
        kind="palette",
        integration_s=sum(p.integration_s for p in parts),
        subs=sum(p.subs for p in parts),
        parts=parts,
    )


def look_progress(key: str, idle: str) -> dict:
    """A 100% view that isn't there yet: being drawn, failed last time (and why), or not asked for (`idle`)."""
    import re

    last = Task.objects.filter(dedupe_key=key).order_by("-enqueued_at").first()
    if last is not None and last.status in ("ready", "running"):
        return {"generating": True, "note": "Drawing the 100% view…"}
    if last is not None and last.status == "failed":
        found = re.findall(r"^\w*(?:Error|Exception): (.+)$", last.error or "", re.M)
        why = found[-1] if found else "no reason given"
        return {"failed": True, "note": f"Couldn't draw the 100% view: {why[:200]}"}
    return {"note": idle}


@router.get("/stacks/{id}/view", response=LookOut)
def master_look(request, id: int):  # noqa: A002
    from .tasks import master_view_paths

    m = get_object_or_404(Master.objects.select_related("dataset"), pk=id)
    if not m.output_path:
        return LookOut(ready=False, note="This master has no file.")
    full, inspect = master_view_paths(m)
    integration = master_integration(m)
    if full.exists() and inspect.exists():
        return LookOut(
            ready=True,
            full=f"/api/v1/stacks/{id}/view/full",
            inspector=f"/api/v1/stacks/{id}/view/inspector",
            integration=integration,
        )
    return LookOut(
        ready=False,
        integration=integration,
        **look_progress(f"master-view:{id}", "No 100% view of this master yet."),
    )


@router.post("/stacks/{id}/view", response=LookOut)
def make_master_look(request, id: int):  # noqa: A002
    from .tasks import master_view

    get_object_or_404(Master, pk=id)
    enqueue(master_view, id, dedupe_key=f"master-view:{id}")
    return LookOut(ready=False, generating=True, note="Drawing the 100% view…")


@router.get("/stacks/{id}/view/{kind}", response={200: None, 404: None})
def master_look_file(request, id: int, kind: Literal["full", "inspector"]):  # noqa: A002
    from .tasks import master_view_paths

    full, inspect = master_view_paths(get_object_or_404(Master, pk=id))
    p = full if kind == "full" else inspect
    return FileResponse(p.open("rb"), content_type="image/jpeg") if p.exists() else HttpResponse(status=404)


@router.get("/combined/{id}/view", response=LookOut)
def combined_look(request, id: int):  # noqa: A002
    from .models import CombinedMaster
    from .tasks import master_view_paths

    cm = get_object_or_404(CombinedMaster, pk=id)
    if not cm.output_path:
        return LookOut(ready=False, note="Not made yet.")
    full, inspect = master_view_paths(cm)
    integration = combined_integration(cm)
    if full.exists() and inspect.exists():
        return LookOut(
            ready=True,
            full=f"/api/v1/combined/{id}/view/full",
            inspector=f"/api/v1/combined/{id}/view/inspector",
            integration=integration,
        )
    return LookOut(
        ready=False, integration=integration, **look_progress(f"combined-view:{id}", "No 100% view yet.")
    )


@router.post("/combined/{id}/view", response=LookOut)
def make_combined_look(request, id: int):  # noqa: A002
    from .models import CombinedMaster
    from .tasks import combined_view

    get_object_or_404(CombinedMaster, pk=id)
    enqueue(combined_view, id, dedupe_key=f"combined-view:{id}")
    return LookOut(ready=False, generating=True, note="Drawing the 100% view…")


@router.get("/combined/{id}/view/{kind}", response={200: None, 404: None})
def combined_look_file(request, id: int, kind: Literal["full", "inspector"]):  # noqa: A002
    from .models import CombinedMaster
    from .tasks import master_view_paths

    full, inspect = master_view_paths(get_object_or_404(CombinedMaster, pk=id))
    p = full if kind == "full" else inspect
    return FileResponse(p.open("rb"), content_type="image/jpeg") if p.exists() else HttpResponse(status=404)


@router.get("/collections/{id}/palette/{name}", response=LookOut)
def palette_look(request, id: int, name: Literal["hoo", "sho"], project: int | None = None):  # noqa: A002
    """HOO or SHO at 100%, made from the project's combined masters (registered to one framing)."""
    from .tasks import palette_inputs, palette_paths

    full, inspect, _screen = palette_paths(id, project, name)
    q = f"?project={project}" if project else ""
    if full.exists() and inspect.exists():
        return LookOut(
            ready=True,
            full=f"/api/v1/collections/{id}/palette/{name}/full{q}",
            inspector=f"/api/v1/collections/{id}/palette/{name}/inspector{q}",
            integration=palette_integration(id, project, name),
        )
    if palette_inputs(id, project, name) is None:
        from apps.catalogue.models import Project

        if project is None and Project.objects.filter(collection_id=id).exists():
            return LookOut(ready=False, note="Pick a project.")
        need = "Hα and OIII" if name == "hoo" else "SII, Hα and OIII"
        return LookOut(ready=False, note=f"Needs combined {need} masters.")
    return LookOut(
        ready=False, **look_progress(f"palette:{id}:{project}:{name}", f"No {name.upper()} view yet.")
    )


@router.post("/collections/{id}/palette/{name}", response=LookOut)
def make_palette_look(request, id: int, name: Literal["hoo", "sho"], project: int | None = None):  # noqa: A002
    from .tasks import palette_inputs, palette_view

    if palette_inputs(id, project, name) is None:
        raise ApiError(422, "missing", "Stitch the mosaic or stack the masters together first.")
    enqueue(palette_view, id, project, name, dedupe_key=f"palette:{id}:{project}:{name}")
    return LookOut(ready=False, generating=True, note="Drawing the 100% view…")


@router.get("/collections/{id}/palette/{name}/{kind}", response={200: None, 404: None})
def palette_look_file(
    request,
    id: int,
    name: Literal["hoo", "sho"],
    kind: Literal["full", "inspector"],  # noqa: A002
    project: int | None = None,
):
    from .tasks import palette_paths

    full, inspect, _screen = palette_paths(id, project, name)
    p = full if kind == "full" else inspect
    return FileResponse(p.open("rb"), content_type="image/jpeg") if p.exists() else HttpResponse(status=404)


@router.get("/stacks/{id}/annotations", response=AnnotationsOut)
def master_annotations(request, id: int):  # noqa: A002
    """The named objects in a solved master's field, placed on its preview (009 amendment 2026-10-12)."""
    from .annotations import for_master

    m = get_object_or_404(Master, pk=id)
    if "ra_deg" not in (m.solve or {}):
        failed = (m.solve or {}).get("failed")
        return AnnotationsOut(
            solved=False, note="Siril couldn't solve this master." if failed else "Not plate solved yet."
        )
    return AnnotationsOut(solved=True, objects=[AnnotationOut(**o) for o in for_master(m)])


class PostStageOut(Schema):
    step: str
    label: str
    state: str  # done, skipped, failed
    reason: str = ""
    tool: str = ""
    seconds: float | None = None
    params: dict = {}
    preview: str | None = None  # URL
    full: str | None = None  # URL of the 100% view, drawn with the master's stretch
    tool_label: str = ""  # "GraXpert", "BlurXTerminator", … for the version tabs
    stats: dict = {}  # background_adu, noise_adu, peak_adu, snr
    file_path: str = ""  # the stage's linear 32-bit file
    download: str | None = None  # the same file, for a viewer who downloads rather than opens in place


class PostRunOut(Schema):
    run: int
    started_at: str
    finished_at: str
    stages: list[PostStageOut]
    original_stats: dict = {}
    chosen: list[str] | None = None  # the steps asked for on this run; None: Settings' selection (010-DR-29)
    helper: str = ""  # the helper that ran it, when one did


class PostStepChoice(Schema):
    """A step a run can be asked for (010-DR-29): on by default when Settings has it on."""

    step: str
    label: str
    tool: str
    on: bool
    available: bool
    reason: str = ""


class PostIn(Schema):
    steps: list[str] | None = (
        None  # exactly these steps, with Settings' parameters; None: Settings' selection
    )


class PostOut(Schema):
    enabled: bool
    queued: bool
    runs: list[PostRunOut]
    steps: list[PostStepChoice] = []
    helper_online: bool = False  # a helper asked for work in the last two minutes
    helper_host: str = ""
    helper_seen_at: str | None = None


def _tool_label(s: dict) -> str:
    step, tool = s.get("step"), s.get("tool")
    if step == "deconvolve":
        return "BlurXTerminator"
    if step == "denoise":
        return "NoiseXTerminator" if tool == "rc_astro" else "GraXpert denoise"
    if step == "starless":
        return "StarXTerminator"
    if step == "trim":
        return "Edges trimmed"
    return "GraXpert"


def _post_out(m) -> PostOut:  # noqa: ANN001 — a Master or a CombinedMaster
    from .config import processing_settings
    from .models import CombinedMaster

    combined = isinstance(m, CombinedMaster)
    base = f"/api/v1/combined/{m.pk}/post" if combined else f"/api/v1/stacks/{m.pk}/post"
    task_name = (
        "apps.processing.postprocess.postprocess_combined"
        if combined
        else "apps.processing.postprocess.postprocess_master"
    )
    runs: list[PostRunOut] = []
    for r in (m.report or {}).get("post_runs", []):
        # a run recorded by an older helper or version may lack a field or carry a null: never fail the whole list
        stages = [
            PostStageOut(
                step=s.get("step") or "",
                label=s.get("label") or s.get("step") or "",
                state=s.get("state") or "",
                reason=s.get("reason") or "",
                tool=s.get("tool") or "",
                seconds=s.get("seconds"),
                params=s.get("params") or {},
                preview=f"{base}/{r['run']}/{i}/preview" if s.get("preview") else None,
                full=f"{base}/{r['run']}/{i}/full" if s.get("full") else None,
                tool_label=_tool_label(s),
                stats=s.get("stats") or {},
                file_path=s.get("path", "") if s.get("state") == "done" else "",
                download=f"{base}/{r['run']}/{i}/download"
                if s.get("state") == "done" and s.get("path")
                else None,
            )
            for i, s in enumerate(r.get("stages", []))
        ]
        runs.append(
            PostRunOut(
                run=r.get("run") or len(runs) + 1,
                started_at=r.get("started_at") or "",
                finished_at=r.get("finished_at") or r.get("started_at") or "",
                stages=stages,
                original_stats=r.get("original_stats") or {},
                chosen=r.get("chosen"),
                helper=r.get("helper") or "",
            )
        )
    from datetime import datetime, timedelta

    seen = processing_settings().get("helper_seen") or {}
    at = seen.get("at")
    online = isinstance(at, str) and timezone.now() - datetime.fromisoformat(at) < timedelta(minutes=2)
    key = f"post-combined:{m.pk}" if combined else f"post:{m.pk}"
    queued = (
        Task.objects.filter(dedupe_key=key, status__in=["ready", "running"]).exists()
        or Task.objects.filter(name=task_name, args__0=m.pk, status__in=["ready", "running"]).exists()
    )
    from .postprocess import step_choices

    ps = processing_settings()
    return PostOut(
        enabled=bool(ps["post"].get("enabled")),
        queued=queued,
        runs=list(reversed(runs)),
        steps=[PostStepChoice(**c) for c in step_choices(ps["post"], ps.get("post_tools"))],
        helper_online=online,
        helper_host=seen.get("host", ""),
        helper_seen_at=at,
    )


@router.get("/stacks/{id}/post", response=PostOut)
def master_post(request, id: int):  # noqa: A002
    """Spec 010: a master's post-processing runs, newest first, each stage with its tool and reason."""
    return _post_out(get_object_or_404(Master, pk=id))


def _run_overrides(body: PostIn | None) -> tuple:
    """The task arguments after the master's id: none for Settings' selection, else exactly the chosen steps."""
    from .config import processing_settings
    from .postprocess import chosen_overrides

    if body is None or body.steps is None:
        return ()
    try:
        return (chosen_overrides(processing_settings()["post"], body.steps),)
    except ValueError as e:
        raise ApiError(422, "unknown_step", str(e)) from None


@router.post("/stacks/{id}/post", response=PostOut)
def start_master_post(request, id: int, body: PostIn | None = None):  # noqa: A002
    """Spec 010 US3: post-process this master again, from the untouched master, with the current settings, or
    with the steps chosen for this run (010-DR-29)."""
    from .postprocess import postprocess_master

    m = get_object_or_404(Master, pk=id)
    if not m.output_path:
        raise ApiError(409, "no_file", "This master has no file to process.")
    enqueue(postprocess_master, m.pk, *_run_overrides(body), dedupe_key=f"post:{m.pk}")
    return _post_out(m)


@router.get("/stacks/{id}/post/{run}/{stage}/full", response={200: None, 404: None})
def master_post_full(request, id: int, run: int, stage: int):  # noqa: A002
    """A stage at 100%, drawn with its master's stretch."""
    m = get_object_or_404(Master, pk=id)
    for r in (m.report or {}).get("post_runs", []):
        if r["run"] == run and 0 <= stage < len(r.get("stages", [])):
            p = Path(r["stages"][stage].get("full") or "")
            if p.is_file():
                return FileResponse(p.open("rb"), content_type="image/jpeg")
    return 404, None


@router.get("/stacks/{id}/post/{run}/{stage}/download", response={200: None, 404: None})
def master_post_download(request, id: int, run: int, stage: int):  # noqa: A002
    """A processed version's linear 32-bit file, to download (spec 010 FR-008, 2026-10-15)."""
    m = get_object_or_404(Master, pk=id)
    for r in (m.report or {}).get("post_runs", []):
        if r["run"] == run and 0 <= stage < len(r.get("stages", [])):
            s = r["stages"][stage]
            p = Path(s.get("path") or "")
            if s.get("state") == "done" and p.is_file():
                base = m.dataset.display_name.replace(" · ", "_").replace(" ", "")
                return FileResponse(
                    p.open("rb"),
                    as_attachment=True,
                    filename=f"{base}_master_v{m.version}_{s['step']}{p.suffix}",
                )
    return 404, None


@router.post("/stacks/{id}/post/views", response=PostOut)
def redraw_post(request, id: int):  # noqa: A002
    """Redraw this master's stages with its stretch, at 100% too."""
    from .postprocess import redraw_post_views

    m = get_object_or_404(Master, pk=id)
    enqueue(redraw_post_views, m.pk, dedupe_key=f"post-views:{m.pk}")
    return _post_out(m)


@router.get("/stacks/{id}/post/{run}/{stage}/preview", response={200: None, 404: None})
def master_post_preview(request, id: int, run: int, stage: int, size: Literal["screen", "thumb"] = "screen"):  # noqa: A002
    m = get_object_or_404(Master, pk=id)
    for r in (m.report or {}).get("post_runs", []):
        if r["run"] == run and 0 <= stage < len(r.get("stages", [])):
            p = Path(r["stages"][stage].get("preview") or "")
            if size == "thumb":
                p = p.with_name(p.stem + "_t.jpg")
            if p.is_file():
                return FileResponse(p.open("rb"), content_type="image/jpeg")
    return 404, None


# ---- post-processing a stitched or stacked master (spec 010 US6, 2026-10-24) ------------------------------------
def _combined(id: int):  # noqa: A002, ANN202
    from .models import CombinedMaster

    return get_object_or_404(CombinedMaster.objects.select_related("collection"), pk=id)


def _stage(m, run: int, stage: int) -> dict | None:  # noqa: ANN001
    for r in (m.report or {}).get("post_runs", []):
        if r["run"] == run and 0 <= stage < len(r.get("stages", [])):
            return r["stages"][stage]
    return None


@router.get("/combined/{id}/post", response=PostOut)
def combined_post(request, id: int):  # noqa: A002
    """A stitched or stacked master's post-processing runs, newest first, as a dataset master's."""
    return _post_out(_combined(id))


@router.post("/combined/{id}/post", response=PostOut)
def start_combined_post(request, id: int, body: PostIn | None = None):  # noqa: A002
    """Post-process this stitched or stacked master (again), from its untouched file, with the current settings or
    the steps chosen for this run (010-DR-29). Admins only: a run on a big canvas takes a helper a long time."""
    from apps.accounts.roles import is_admin

    from .postprocess import postprocess_combined

    if not is_admin(request.user):
        raise ApiError(403, "admin_only", "Only an admin can start post-processing.")
    cm = _combined(id)
    if not cm.output_path or cm.state != MasterState.CURRENT:
        raise ApiError(409, "no_file", "This master has no current file to process.")
    enqueue(postprocess_combined, cm.pk, *_run_overrides(body), dedupe_key=f"post-combined:{cm.pk}")
    return _post_out(cm)


@router.post("/combined/{id}/post/views", response=PostOut)
def redraw_combined_post(request, id: int):  # noqa: A002
    """Redraw this combined master's stages with its stretch, at 100% too."""
    from .postprocess import redraw_post_views

    cm = _combined(id)
    enqueue(redraw_post_views, cm.pk, "combined", dedupe_key=f"post-views-combined:{cm.pk}")
    return _post_out(cm)


@router.get("/combined/{id}/post/{run}/{stage}/preview", response={200: None, 404: None})
def combined_post_preview(
    request,
    id: int,  # noqa: A002
    run: int,
    stage: int,
    size: Literal["screen", "thumb"] = "screen",
):
    s = _stage(_combined(id), run, stage)
    p = Path((s or {}).get("preview") or "")
    if size == "thumb":
        p = p.with_name(p.stem + "_t.jpg")
    return (
        FileResponse(p.open("rb"), content_type="image/jpeg")
        if s and p.is_file()
        else HttpResponse(status=404)
    )


@router.get("/combined/{id}/post/{run}/{stage}/full", response={200: None, 404: None})
def combined_post_full(request, id: int, run: int, stage: int):  # noqa: A002
    """A stage at 100%, drawn with the combined master's stretch."""
    s = _stage(_combined(id), run, stage)
    p = Path((s or {}).get("full") or "")
    return (
        FileResponse(p.open("rb"), content_type="image/jpeg")
        if s and p.is_file()
        else HttpResponse(status=404)
    )


@router.get("/combined/{id}/post/{run}/{stage}/download", response={200: None, 404: None})
def combined_post_download(request, id: int, run: int, stage: int):  # noqa: A002
    """A processed version's linear 32-bit file, to download."""
    cm = _combined(id)
    s = _stage(cm, run, stage)
    p = Path((s or {}).get("path") or "")
    if not s or s.get("state") != "done" or not p.is_file():
        return HttpResponse(status=404)
    return FileResponse(
        p.open("rb"), as_attachment=True, filename=f"{Path(cm.output_path).stem}_{s['step']}{p.suffix}"
    )


class PostToolsOut(Schema):
    checked_at: str | None = None
    host: str = ""
    note: str = ""
    graxpert: dict = {}
    rc_astro: dict = {}
    checking: bool = False


class ActivateIn(Schema):
    code: str


def _tools_out() -> PostToolsOut:
    from .config import processing_settings

    st = processing_settings().get("post_tools") or {}
    busy = Task.objects.filter(
        name__in=["apps.processing.postprocess.check_tools", "apps.processing.postprocess.activate_rc_astro"],
        status__in=[TaskStatus.READY, TaskStatus.RUNNING],
    ).exists()
    return PostToolsOut(**{k: v for k, v in st.items() if k in PostToolsOut.model_fields}, checking=busy)


@router.get("/post/tools", response=PostToolsOut)
def post_tools(request):
    """Spec 010: which finishing tools the finisher can run, as it last reported."""
    return _tools_out()


@router.post("/post/tools/check", response=PostToolsOut)
def check_post_tools(request):
    from .postprocess import check_tools

    enqueue(check_tools, dedupe_key="post-tools-check")
    return _tools_out().model_copy(update={"checking": True})


@router.post("/post/tools/rc-astro", response=PostToolsOut)
def activate_rc_astro_api(request, body: ActivateIn):
    """Owner 2026-10-12: paste an RC-Astro activation code here instead of running a command on the finisher."""
    from .postprocess import activate_rc_astro

    if not request.user.is_staff:
        raise ApiError(403, "forbidden", "Only an admin can activate RC-Astro.")
    enqueue(activate_rc_astro, body.code.strip(), dedupe_key="rc-astro-activate")
    return _tools_out().model_copy(update={"checking": True})
