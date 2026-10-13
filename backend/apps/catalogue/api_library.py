"""Library, collections and rigs (spec 006; v2 design L1–L3). On the catalogue router. No
`from __future__ import annotations` here: see substation.api."""

import shutil
from collections import defaultdict
from datetime import date, datetime
from typing import Literal

from django.conf import settings
from django.db.models import Max, Min, Sum
from django.shortcuts import get_object_or_404

from substation.api import ApiError, Schema, Status, admin_required

from .api import DatasetOut, dataset_out, router
from .models import Collection, Dataset, DatasetNight, Rig
from .services.library import add_to_collection, centre, ensure_rig, label, refresh_objects, suggest


class RigOut(Schema):
    id: int
    name: str
    telescope: str
    camera: str
    focal_mm: float | None
    image_scale: float | None
    sessions: int
    datasets: int
    calibration: str
    mount: str = ""


class LibDatasetOut(Schema):
    dataset: DatasetOut
    label: str
    rig: str | None
    sessions: int
    last_night: date | None
    master_state: str | None
    suggestion: dict | None
    master_version: int | None = None
    master_progress: float | None = None
    master_finished: datetime | None = None
    nights: list[date] = []


class CollectionMasterOut(Schema):
    id: int
    dataset_id: int
    dataset: str
    version: int
    state: str
    sub_count: int
    integration_s: float
    finished_at: datetime | None
    has_preview: bool


class FilterTime(Schema):
    """A filter's exposure: everything captured, and how much of it is usable or rejected so far. The rest is
    still waiting (for calibration or grading)."""

    total_s: float
    accepted_s: float
    rejected_s: float


class CollectionCard(Schema):
    id: int
    name: str
    objects: str
    datasets: int
    rigs: list[str]
    filters: dict[str, float]
    filter_time: dict[str, FilterTime] = {}
    first_night: date | None
    last_night: date | None
    sessions: int
    accepted_integration_s: float
    states: list[str]
    preview_master: int | None
    constellation: str = ""
    nights: list[date] = []  # every session's date, for the Library's date filter


class LibraryHomeOut(Schema):
    readouts: dict
    collections: list[CollectionCard]
    ungrouped: list[LibDatasetOut]
    rigs: int
    counts: dict[str, int]


def _lib_dataset(d: Dataset, with_suggestion: bool, centres: dict | None = None) -> LibDatasetOut:
    ensure_rig(d)
    agg = DatasetNight.objects.filter(dataset=d).aggregate(n=Sum(1), last=Max("night__date"))
    sessions = DatasetNight.objects.filter(dataset=d).count()
    from apps.processing.models import Master

    m = Master.objects.filter(dataset=d).exclude(state="deleted").order_by("-version").first()
    return LibDatasetOut(
        dataset=dataset_out(d),
        label=label(d),
        rig=d.rig.name if d.rig else None,
        sessions=sessions,
        last_night=agg["last"],
        master_state=m.state if m else None,
        suggestion=suggest(d, centres) if with_suggestion else None,
        master_version=m.version if m else None,
        master_progress=m.progress if m else None,
        master_finished=m.finished_at if m else None,
        nights=sorted(DatasetNight.objects.filter(dataset=d).values_list("night__date", flat=True)),
    )


def _states(datasets: list[Dataset]) -> list[str]:
    from apps.processing.models import Master

    out = []
    if Master.objects.filter(dataset__in=datasets, state__in=["queued", "running"]).exists():
        out.append("integ")
    if Master.objects.filter(dataset__in=datasets, state="stale").exists():
        out.append("stale")
    newest = (
        Master.objects.filter(dataset__in=datasets)
        .exclude(state="deleted")
        .order_by("dataset_id", "-version")
        .distinct()
    )
    if any(m.state == "failed" for m in {m.dataset_id: m for m in reversed(list(newest))}.values()):
        out.append("failed")
    if any(d.state == "awaiting_calibration" for d in datasets):
        out.append("await")
    if any(d.state == "needs_reconciliation" for d in datasets):
        out.append("recon")
    return out


def _card(col: Collection) -> CollectionCard:
    ds = list(col.datasets.select_related("rig"))
    for d in ds:
        ensure_rig(d)
    filters: dict[str, float] = defaultdict(float)
    split: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for d in ds:
        f = d.filter_norm or "?"
        filters[f] += d.accepted_integration_s or 0
        split[f][0] += d.integration_s or 0
        split[f][1] += d.accepted_integration_s or 0
        split[f][2] += d.rejected_integration_s or 0
    nights = DatasetNight.objects.filter(dataset__in=ds)
    span = nights.aggregate(first=Min("night__date"), last=Max("night__date"))
    from apps.processing.models import Master

    m = (
        Master.objects.filter(dataset__in=ds, state="current")
        .exclude(preview_path="")
        .order_by("-finished_at")
        .first()
    )
    return CollectionCard(
        id=col.pk,
        name=col.name,
        objects=col.objects_text,
        datasets=len(ds),
        rigs=sorted({d.rig.name for d in ds if d.rig}),
        filters=dict(filters),
        filter_time={
            k: FilterTime(total_s=max(t, a + r), accepted_s=a, rejected_s=r) for k, (t, a, r) in split.items()
        },
        first_night=span["first"],
        last_night=span["last"],
        sessions=nights.values("night").distinct().count(),
        accepted_integration_s=sum(d.accepted_integration_s or 0 for d in ds),
        states=_states(ds),
        preview_master=m.pk if m else None,
        constellation=col.constellation,
        nights=sorted(set(nights.values_list("night__date", flat=True))),
    )


def _main_job() -> str:
    """What the workers are mostly doing, for the Processing readout (006-DR-02): "Hα master integrating"."""
    from apps.processing.models import Master
    from substation.tasks.models import Task, TaskStatus

    m = Master.objects.filter(state="running").select_related("dataset__rig").first()
    if m is not None:
        return f"{m.dataset.filter_norm} master integrating"
    names = list(Task.objects.filter(status=TaskStatus.RUNNING).values_list("name", flat=True))
    if any(n.endswith("calibrate_measure") for n in names):
        return "grading new subs"
    if any(n.endswith("build_master") for n in names):
        return "building calibration masters"
    if any(n.startswith("apps.ingest") for n in names):
        return "reading new files"
    return ""


@router.get("/library", response=LibraryHomeOut)
def library(request):
    cols = [_card(c) for c in Collection.objects.order_by("name")]
    # each suggestion compares one dataset's pointing with every grouped dataset's: work each out once
    centres = {d.pk: centre(d) for d in Dataset.objects.filter(collection__isnull=False)}
    ungrouped = [
        _lib_dataset(d, True, centres)
        for d in Dataset.objects.filter(collection__isnull=True, sub_count__gt=0)
        .select_related("rig")
        .order_by("target", "filter_norm")
    ]
    last = DatasetNight.objects.aggregate(last=Max("night__date"))["last"]
    last_subs = (
        DatasetNight.objects.filter(night__date=last).aggregate(n=Sum("sub_count"))["n"] if last else 0
    )
    last_rigs = (
        Dataset.objects.filter(nights__night__date=last).values("rig").distinct().count() if last else 0
    )
    try:
        free = shutil.disk_usage(settings.STATION_ROOT).free
    except OSError:
        free = None
    from substation.tasks.models import Task, TaskStatus, Worker

    busy = Worker.objects.filter(state="busy").count()
    running = Task.objects.filter(status=TaskStatus.RUNNING).values_list("name", flat=True)
    return LibraryHomeOut(
        readouts={
            "last_night": last,
            "last_night_subs": last_subs or 0,
            "last_night_rigs": last_rigs,
            "accepted_integration_s": sum(Dataset.objects.values_list("accepted_integration_s", flat=True)),
            "workers_busy": busy,
            "jobs_running": len(running),
            "integrating": any("stack" in n or "master" in n for n in running),
            "disk_free_bytes": free,
            "main_job": _main_job(),
        },
        collections=cols,
        ungrouped=ungrouped,
        rigs=Rig.objects.count(),
        counts={
            "datasets": Dataset.objects.filter(sub_count__gt=0).count(),
            "collections": len(cols),
            "ungrouped": len(ungrouped),
        },
    )


class CollectionIn(Schema):
    name: str
    dataset_ids: list[int] = []


class CollectionPatch(Schema):
    name: str | None = None


class SessionDot(Schema):
    night: date
    rig: str
    accepted_s: float
    subs: int
    filters: list[str]


class CollectionOut(Schema):
    card: CollectionCard
    datasets: list[LibDatasetOut]
    matrix: dict[str, dict[str, float]]
    rig_details: list[RigOut]
    sessions: list[SessionDot]
    masters: list[CollectionMasterOut] = []


def _rig_out(r: Rig) -> RigOut:
    return RigOut(
        id=r.pk,
        name=r.name,
        telescope=r.telescope,
        camera=r.camera,
        focal_mm=r.focal_mm,
        image_scale=r.image_scale,
        sessions=DatasetNight.objects.filter(dataset__rig=r).values("night").distinct().count(),
        datasets=r.datasets.count(),
        calibration=r.calibration,
        mount=r.mount,
    )


@router.post("/collections/accept-suggestions", response=dict[str, int])
def accept_all_suggestions(request):
    """Group every ungrouped dataset as suggested, creating collections named after their object."""
    made = added = 0
    for d in Dataset.objects.filter(collection__isnull=True, sub_count__gt=0).order_by("target"):
        s = suggest(d)
        col = Collection.objects.filter(pk=s["collection_id"]).first() if s["collection_id"] else None
        if col is None:
            col = Collection.objects.create(name=d.target or "Unnamed")
            made += 1
        add_to_collection([d.pk], col)
        added += 1
    return {"collections_created": made, "datasets_added": added}


@router.get("/collections/{id}", response=CollectionOut)
def get_collection(request, id: int):  # noqa: A002
    from apps.processing.models import Master

    col = get_object_or_404(Collection, pk=id)
    ds = list(col.datasets.select_related("rig").order_by("rig__name", "filter_norm", "panel"))
    matrix: dict[str, dict[str, float]] = defaultdict(dict)
    for d in ds:
        ensure_rig(d)
        r = d.rig.name if d.rig else "?"
        matrix[r][d.filter_norm or "?"] = matrix[r].get(d.filter_norm or "?", 0) + (
            d.accepted_integration_s or 0
        )
    dots: dict[tuple[date, str], dict] = defaultdict(lambda: {"s": 0.0, "n": 0, "f": set()})
    for dn in DatasetNight.objects.filter(dataset__in=ds).select_related("night", "dataset__rig"):
        dot = dots[(dn.night.date, dn.dataset.rig.name if dn.dataset.rig else "?")]
        dot["s"] += dn.integration_s
        dot["n"] += dn.sub_count
        dot["f"].add(dn.dataset.filter_norm or "?")
    rigs = {d.rig for d in ds if d.rig}
    return CollectionOut(
        card=_card(col),
        datasets=[_lib_dataset(d, False) for d in ds],
        matrix=dict(matrix),
        rig_details=[_rig_out(r) for r in rigs],
        sessions=[
            SessionDot(night=k[0], rig=k[1], accepted_s=v["s"], subs=v["n"], filters=sorted(v["f"]))
            for k, v in sorted(dots.items())
        ],
        masters=[
            CollectionMasterOut(
                id=m.pk,
                dataset_id=m.dataset_id,
                dataset=label(m.dataset),
                version=m.version,
                state=m.state,
                sub_count=m.sub_count,
                integration_s=m.integration_s,
                finished_at=m.finished_at,
                has_preview=bool(m.preview_path),
            )
            for m in Master.objects.filter(dataset__in=ds)
            .exclude(state="deleted")
            .select_related("dataset__rig")
            .order_by("-finished_at", "-pk")
        ],
    )


@router.post("/collections", response={201: CollectionCard})
def create_collection(request, body: CollectionIn):
    if not body.name.strip():
        raise ApiError(422, "invalid", "Give the collection a name.")
    col = Collection.objects.create(name=body.name.strip())
    add_to_collection(body.dataset_ids, col)
    return Status(201, _card(col))


@router.patch("/collections/{id}", response=CollectionCard)
def patch_collection(request, id: int, body: CollectionPatch):  # noqa: A002
    col = get_object_or_404(Collection, pk=id)
    if body.name is not None and body.name.strip():
        col.name = body.name.strip()
        col.save(update_fields=["name"])
    return _card(col)


@router.delete("/collections/{id}", response={204: None})
def delete_collection(request, id: int):  # noqa: A002
    col = get_object_or_404(Collection, pk=id)
    col.delete()  # datasets stay (their collection is cleared); files are never touched
    return Status(204, None)


class DatasetIds(Schema):
    dataset_ids: list[int]


@router.post("/collections/{id}/datasets", response=CollectionCard)
def add_datasets(request, id: int, body: DatasetIds):  # noqa: A002
    col = get_object_or_404(Collection, pk=id)
    add_to_collection(body.dataset_ids, col)
    return _card(col)


class CandidateOut(Schema):
    dataset_id: int
    label: str
    target: str
    subs: int
    integration_s: float
    offset_arcmin: float | None
    in_collection: str | None
    note: str
    overlap: float | None = None
    rotation_diff: float | None = None


class FramingOut(Schema):
    dataset_id: int
    label: str
    reference: bool
    solved: int
    corners: list[list[float]]
    fov_w: float
    fov_h: float
    scale: float
    rotation: float
    offset_arcmin: float
    overlap: float
    panel: int | None = None
    filter: str | None = None
    image: str | None = None  # sha256 of the sub whose preview shows this field
    image_url: str | None = None  # the master's preview when solved, else the sub's
    image_kind: str = "sub"  # "master" or "sub"
    master_id: int | None = None
    image_corners: list[list[float]] = []  # that preview's top-left, top-right, bottom-right, bottom-left
    image_mirrored_known: bool = False  # False until a solve has said whether the image is mirrored


@router.get("/collections/{id}/framing", response=list[FramingOut])
def collection_framing(request, id: int, reference: int | None = None, project: int | None = None):  # noqa: A002
    """Every dataset's solved field over the reference framing, north up (009 P10/P12, 006-DR-09), each with a
    sub's preview placed exactly where it sits on the sky. The reference is the one asked for, else the solved
    dataset with the most accepted integration. Mosaic panels come back side by side."""
    import math

    from apps.processing.models import PlateSolve
    from apps.processing.solving import _tangent, corners, framing, image_corners, master_corners, overlap

    col = get_object_or_404(Collection, pk=id)
    rows: list[tuple[Dataset, dict]] = []
    scope = col.datasets.filter(project_id=project) if project else col.datasets.all()
    for d in scope.select_related("rig"):
        f = framing(d)
        if f is not None:
            rows.append((d, f))
    if not rows:
        return []
    chosen = [r for r in rows if r[0].pk == reference]
    ref_d, ref = chosen[0] if chosen else max(rows, key=lambda r: r[0].accepted_integration_s or 0)
    out = []
    for d, f in rows:
        x, y = _tangent(f, ref)
        img_corners: list[list[float]] = []
        url, kind = None, "sub"
        if f.get("master") is not None:
            from apps.catalogue.models import Frame

            m = f["master"]
            some = Frame.objects.filter(dataset=d, frame_type="light").prefetch_related("headers").first()
            img_corners = [[round(a, 5), round(b, 5)] for a, b in master_corners(m, some, ref)]
            url, kind = f"/api/v1/stacks/{m.pk}/preview", "master"
        elif f["image"]:
            ps = PlateSolve.objects.select_related("frame").get(frame_id=f["image"])
            img_corners = [[round(a, 5), round(b, 5)] for a, b in image_corners(ps, ref)]
            url = f"/api/v1/frames/{f['image']}/preview"
        out.append(
            FramingOut(
                dataset_id=d.pk,
                label=label(d),
                reference=d.pk == ref_d.pk,
                solved=f["solved"],
                corners=[[round(a, 5), round(b, 5)] for a, b in corners(f, ref)],
                fov_w=f["fov_w"],
                fov_h=f["fov_h"],
                scale=f["scale"],
                rotation=f["rotation"],
                offset_arcmin=round(math.hypot(x, y) * 60, 1),
                overlap=round(overlap(f, ref) if d.pk != ref_d.pk else 1.0, 3),
                panel=d.panel,
                filter=d.filter_norm,
                image=f["image"],
                image_url=url,
                image_kind=kind,
                image_corners=img_corners,
                master_id=f["master"].pk if f.get("master") is not None else None,
                image_mirrored_known=f["image_flipped"] is not None and bool(f.get("image_source")),
            )
        )
    return sorted(out, key=lambda r: (not r.reference, r.panel or 0, r.offset_arcmin))


@router.get("/collections/{id}/candidates", response=list[CandidateOut])
def candidates(request, id: int):  # noqa: A002
    """Datasets that could join this collection (006-DR-05). Where both sides are plate solved (009 P11) the
    ranking is by how much of the reference field they cover, then rotation difference; otherwise by the
    distance between median header pointings."""
    from apps.processing.solving import _tangent, framing, overlap

    from .services.library import centre, separation

    col = get_object_or_404(Collection, pk=id)
    mine = [c for c in (centre(d) for d in col.datasets.all()) if c is not None]
    targets = {(d.target or "").casefold() for d in col.datasets.all()}
    solved = [(d, f) for d in col.datasets.all() if (f := framing(d)) is not None]
    ref = max(solved, key=lambda r: r[0].accepted_integration_s or 0)[1] if solved else None
    out = []
    for d in (
        Dataset.objects.filter(sub_count__gt=0).exclude(collection=col).select_related("rig", "collection")
    ):
        c = centre(d)
        sep = min((separation(c, m) for m in mine), default=None) if c is not None else None
        same_name = (d.target or "").casefold() in targets
        if not same_name and (sep is None or sep > 3):
            continue
        f = framing(d) if ref is not None else None
        cover = rot = None
        if f is not None and ref is not None:
            import math

            x, y = _tangent(f, ref)
            sep = math.hypot(x, y)
            cover = round(overlap(f, ref), 3)
            # A field turned 180° frames the same sky; what matters is the angle between the two outlines.
            rot = round(abs(((f["rotation"] - ref["rotation"] + 90) % 180) - 90), 1)
            note = f"Solved: {sep * 60:.0f}′ off, rotated {rot:.0f}°, {cover * 100:.0f}% overlap."
        elif same_name and sep is None:
            note = f"Same object name ({d.target}); no pointing in headers."
        elif sep is not None and sep * 60 < 30:
            note = f"Centre {sep * 60:.0f}′ away (headers)."
        else:
            note = f"Centre {sep:.1f}° away (headers): different framing?" if sep is not None else ""
        out.append(
            CandidateOut(
                dataset_id=d.pk,
                label=label(d),
                target=d.target,
                subs=d.sub_count,
                integration_s=d.integration_s,
                offset_arcmin=round(sep * 60, 1) if sep is not None else None,
                in_collection=d.collection.name if d.collection else None,
                note=note,
                overlap=cover,
                rotation_diff=rot,
            )
        )
    return sorted(
        out,
        key=lambda x: (x.overlap is None, -(x.overlap or 0), x.offset_arcmin is None, x.offset_arcmin or 0),
    )


@router.delete("/collections/{id}/datasets/{dataset_id}", response=CollectionCard)
def remove_dataset(request, id: int, dataset_id: int):  # noqa: A002
    col = get_object_or_404(Collection, pk=id)
    Dataset.objects.filter(pk=dataset_id, collection=col).update(collection=None)
    refresh_objects(col)
    return _card(col)


Mount = Literal["equatorial", "altaz", "tracker", "smart", ""]


class RigPatch(Schema):
    name: str | None = None
    calibration: Literal["masters", "flats", "none"] | None = None
    mount: Mount | None = None


class RigIn(Schema):
    name: str
    telescope: str = ""
    camera: str = ""
    focal_mm: float | None = None
    mount: Mount = ""


class RigMergeIn(Schema):
    into: int


class RigSuggestion(Schema):
    rig_id: int
    into: int
    why: str


def _norm(s: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]", "", s.casefold())


@router.post("/rigs/{id}/merge", response=RigOut)
@admin_required
def merge_rig(request, id: int, body: RigMergeIn):  # noqa: A002
    """Treat this rig's header names as the other rig's from now on, and regroup its subs (no file is touched)."""
    from apps.ingest.tasks.reresolve import reresolve_library
    from apps.libraries.models import InstallationSettings
    from substation.tasks import enqueue

    src = get_object_or_404(Rig, pk=id)
    dst = get_object_or_404(Rig, pk=body.into)
    if src.pk == dst.pk:
        raise ApiError(422, "invalid", "Choose a different rig to merge into.")
    s = InstallationSettings.load()
    p = dict(s.processing or {})
    eq = p.setdefault("equipment", {"camera": {}, "telescope": {}})
    pairs = eq.setdefault("rig", {})
    for k, v in list(pairs.items()):  # rigs already merged into this one follow it
        if v == [src.camera, src.telescope]:
            pairs[k] = [dst.camera, dst.telescope]
    pairs[f"{src.camera}|{src.telescope}"] = [dst.camera, dst.telescope]
    s.processing = p
    s.save(update_fields=["processing"])
    Dataset.objects.filter(rig=src).update(rig=dst)
    src.delete()
    enqueue(reresolve_library, None, dedupe_key="reresolve:None")
    return _rig_out(dst)


class MergeNamesIn(Schema):
    names: list[str]
    into: str


@router.post("/collections/{id}/merge-names", response=CollectionOut)
@admin_required
def merge_names(request, id: int, body: MergeNamesIn):  # noqa: A002
    """Treat other target names as `into` from now on (TestSoulNebula, IC 1848 - Soul Nebula → Soul Nebula), so
    their subs share datasets and stack together. Every filter follows. Nothing on disk changes."""
    from apps.ingest.tasks.reresolve import reresolve_targets
    from apps.libraries.models import InstallationSettings
    from substation.tasks import enqueue

    col = get_object_or_404(Collection, pk=id)
    have = set(col.datasets.values_list("target", flat=True))
    names = [n for n in dict.fromkeys(body.names) if n != body.into]
    if body.into not in have or not names or any(n not in have for n in names):
        raise ApiError(422, "invalid", "Use names from this collection's datasets.")
    s = InstallationSettings.load()
    p = dict(s.processing or {})
    eq = p.setdefault("equipment", {"camera": {}, "telescope": {}})
    alias = eq.setdefault("target", {})
    alias.pop(body.into, None)
    for k, v in list(alias.items()):  # names already merged into one of these follow them
        if v in names:
            alias[k] = body.into
    for n in names:
        alias[n] = body.into
    s.processing = p
    s.save(update_fields=["processing"])
    enqueue(reresolve_targets, names, dedupe_key=f"retarget:{'|'.join(sorted(names))}")
    return get_collection(request, id)


@router.get("/rigs/suggestions", response=list[RigSuggestion])
def rig_suggestions(request):
    """Rigs that are probably one: a camera name that contains the other's, and a telescope name that starts the
    same (header strings change between capture software versions)."""
    rigs = list(Rig.objects.all())
    out = []
    for a in rigs:
        for b in rigs:
            if a.pk >= b.pk:
                continue
            ca, cb, ta, tb = _norm(a.camera), _norm(b.camera), _norm(a.telescope), _norm(b.telescope)
            cam = ca and cb and (ca in cb or cb in ca)
            tel = ta and tb and (ta.startswith(tb) or tb.startswith(ta))
            if cam and tel:
                keep, drop = (a, b) if len(a.telescope) >= len(b.telescope) else (b, a)
                out.append(
                    RigSuggestion(
                        rig_id=drop.pk,
                        into=keep.pk,
                        why=f"“{drop.camera} on {drop.telescope}” looks like “{keep.camera} on {keep.telescope}”.",
                    )
                )
    return out


@router.get("/rigs", response=list[RigOut])
def list_rigs(request):
    for d in Dataset.objects.filter(rig__isnull=True):
        ensure_rig(d)
    return [_rig_out(r) for r in Rig.objects.order_by("name")]


@router.post("/rigs", response={201: RigOut})
@admin_required
def add_rig(request, body: RigIn):
    """A rig named before its first sub arrives (008-DR-09): headers that name its telescope and camera join it."""
    if not body.name.strip():
        raise ApiError(422, "invalid", "Give the rig a name.")
    key = (
        f"{body.telescope.strip()}|{body.camera.strip()}|{body.focal_mm or ''}"
        if (body.telescope or body.camera)
        else f"manual|{body.name.strip()}"
    )
    if Rig.objects.filter(key=key).exists():
        raise ApiError(409, "exists", "A rig with this telescope and camera already exists.")
    r = Rig.objects.create(
        key=key,
        name=body.name.strip(),
        telescope=body.telescope.strip(),
        camera=body.camera.strip(),
        focal_mm=body.focal_mm,
        mount=body.mount,
        renamed=True,
    )
    return Status(201, _rig_out(r))


@router.patch("/rigs/{id}", response=RigOut)
@admin_required
def rename_rig(request, id: int, body: RigPatch):  # noqa: A002
    r = get_object_or_404(Rig, pk=id)
    if body.name is not None:
        if not body.name.strip():
            raise ApiError(422, "invalid", "Give the rig a name.")
        r.name, r.renamed = body.name.strip(), True
        r.save(update_fields=["name", "renamed"])
    if body.mount is not None:
        r.mount = body.mount
        r.save(update_fields=["mount"])
    if body.calibration is not None and body.calibration != r.calibration:
        from apps.processing.tasks import rematch_lights
        from substation.tasks import enqueue

        r.calibration = body.calibration
        r.save(update_fields=["calibration"])
        enqueue(rematch_lights, dedupe_key="rematch")  # its lights wait for, or are freed from, other masters
    return _rig_out(r)


__all__ = ["datetime"]


class LibraryStatsOut(Schema):
    frames: int
    hours: float
    accepted_hours: float
    by_filter: dict[str, float]  # hours captured per filter
    by_rig: dict[str, float]
    graded: int
    success_rate: float | None  # accepted or down-weighted, of graded subs
    failure_rate: float | None  # rejected, of graded subs
    avg_sqm: float | None
    sqm_subs: int
    nights: int
    binned: int = 0  # of `frames`, in the bin or deleted (spec 011)


@router.get("/library/stats", response=LibraryStatsOut)
def library_stats(
    request,
    date_from: date | None = None,
    date_to: date | None = None,
    rig: str | None = None,
    q: str | None = None,
):
    """Totals for what the Library's filters show (006, owner 2026-10-10): lights taken, hours per filter and
    rig, how many were kept or rejected, and the average SQM where the capture recorded it."""
    from django.db.models import Q

    from apps.processing.api import COND, _num
    from apps.processing.effective import effective
    from apps.processing.models import MachineGrade

    from .models import Frame, FrameStatus, FrameType

    def scoped(qs, ds: str):  # noqa: ANN001, ANN202
        qs = qs.select_related(f"{ds}__rig", "night").prefetch_related("verdicts", "headers")
        if date_from:
            qs = qs.filter(night__date__gte=date_from)
        if date_to:
            qs = qs.filter(night__date__lte=date_to)
        if rig:
            qs = qs.filter(**{f"{ds}__rig__name": rig})
        if q:
            qs = qs.filter(
                Q(**{f"{ds}__target__icontains": q})
                | Q(**{f"{ds}__collection__name__icontains": q})
                | Q(**{f"{ds}__filter_norm__icontains": q})
                | Q(**{f"{ds}__rig__name__icontains": q})
            )
        return qs

    lights = Frame.objects.filter(frame_type=FrameType.LIGHT)
    live = scoped(lights.filter(status=FrameStatus.CATALOGUED, dataset__isnull=False), "dataset")
    # binned and deleted subs still count: history outlives the files (spec 011)
    gone = scoped(
        lights.filter(status__in=[FrameStatus.BINNED, FrameStatus.DELETED], binned_dataset__isnull=False),
        "binned_dataset",
    )
    frames = [*live, *gone]
    grades = {g.frame_id: g for g in MachineGrade.objects.filter(frame__in=[f.pk for f in frames])}
    by_filter: dict[str, float] = defaultdict(float)
    by_rig: dict[str, float] = defaultdict(float)
    n = graded = kept = rejected = 0
    hours = accepted = 0.0
    sqms: list[float] = []
    nights = set()
    binned = 0
    for f in frames:
        n += 1
        ds = f.dataset or f.binned_dataset
        binned += f.status != FrameStatus.CATALOGUED
        h = (f.exptime_s or 0) / 3600
        hours += h
        by_filter[ds.filter_norm or "?"] += h  # type: ignore[union-attr]
        by_rig[ds.rig.name if ds and ds.rig else "?"] += h
        nights.add(f.night_id)
        g = grades.get(f.pk)
        e = effective(f, list(f.verdicts.all()), g)
        if e.verdict in ("accept", "down", "reject"):
            graded += 1
            if e.verdict == "reject":
                rejected += 1
            else:
                kept += 1
                accepted += h
        snap = next(iter(f.headers.all()), None)
        kw = (
            {k: (x.get("value") if isinstance(x, dict) else x) for k, x in (snap.keywords or {}).items()}
            if snap
            else {}
        )
        if (v := _num(kw, COND["sqm"])) is not None and 10 < v < 23:
            sqms.append(v)
    return LibraryStatsOut(
        frames=n,
        hours=round(hours, 2),
        accepted_hours=round(accepted, 2),
        by_filter={k: round(v, 2) for k, v in sorted(by_filter.items(), key=lambda kv: -kv[1])},
        by_rig={k: round(v, 2) for k, v in sorted(by_rig.items(), key=lambda kv: -kv[1])},
        graded=graded,
        success_rate=round(kept / graded, 3) if graded else None,
        failure_rate=round(rejected / graded, 3) if graded else None,
        avg_sqm=round(sum(sqms) / len(sqms), 2) if sqms else None,
        sqm_subs=len(sqms),
        nights=len(nights - {None}),
        binned=binned,
    )
