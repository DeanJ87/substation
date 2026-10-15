"""Metadata endpoints (T077; contracts/openapi.yaml): path patterns, user corrections, classification overrides
and the reconciliation list. No `from __future__ import annotations` here: see substation.api."""

import os
from datetime import date, datetime
from typing import Any, Literal

from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.ingest.patterns import PatternError, compile_pattern, match
from apps.libraries.models import InstallationSettings, Library
from substation.api import ApiError, Schema, Status, admin_required
from substation.tasks import enqueue

from .api import (  # same "" prefix: Ninja keeps one router per prefix
    FrameSummaryOut,
    frame_summary,
    primary_copy,
    router,
)
from .models import (
    Copy,
    Frame,
    FrameStatus,
    HeaderSnapshot,
    MetadataField,
    PathPattern,
    ReconciliationItem,
    ReconciliationKind,
    ReconciliationStatus,
)
from .services.corrections import CorrectionError, set_value
from .services.ignore import PathRules
from .services.tracking import touch_dataset

RESOLVED_FIELD = {  # field -> Frame attribute shown as its current value
    "object": "object",
    "target": "target",
    "panel": "panel",
    "filter": "filter_raw",
    "exptime": "exptime_s",
    "ccd_temp": "ccd_temp_c",
    "set_temp": "set_temp_c",
    "gain": "gain",
    "offset": "offset",
    "xbin": "xbin",
    "ybin": "ybin",
    "camera": "camera",
    "telescope": "telescope",
    "date_obs": "date_obs_utc",
    "frame_type": "frame_type",
}


# ---- schemas ----------------------------------------------------------------------------------------------
class PathPatternIn(Schema):
    library_id: int | None = None
    scope_glob: str = "**"
    kind: Literal["folder", "filename"]
    pattern: str
    prefer_over_header: list[str] = []
    priority: int = 0
    enabled: bool = True


class PathPatternPatch(Schema):
    library_id: int | None = None
    scope_glob: str | None = None
    kind: Literal["folder", "filename"] | None = None
    pattern: str | None = None
    prefer_over_header: list[str] | None = None
    priority: int | None = None
    enabled: bool | None = None


class PathPatternOut(PathPatternIn):
    id: int
    fields: list[str]
    error: str | None


class PreviewIn(Schema):
    pattern: PathPatternIn
    sample_paths: list[str] = []


class PreviewSample(Schema):
    path: str
    matched: bool
    values: dict[str, Any]


class PreviewChange(Schema):
    field: str
    current: str | None
    new: str


class PreviewFrame(Schema):
    sha256: str
    path: str
    changes: list[PreviewChange]


class PreviewOut(Schema):
    fields: list[str]
    samples: list[PreviewSample]
    matching_files: int
    would_change: list[PreviewFrame]


class MetadataIn(Schema):
    sha256s: list[str]
    field: str
    value: str | float | int | None


class ClassificationIn(Schema):
    sha256s: list[str]
    frame_type: str


class UpdatedOut(Schema):
    updated: int


class ReconExampleOut(Schema):
    """What a group's files are, shown by one of them (owner 2026-10-11)."""

    sha256: str
    frame_type: str
    library_id: int | None
    library: str | None
    folder: str  # inside the library, no trailing slash; "" for its top
    file_name: str
    camera: str | None
    telescope: str | None
    exptime_s: float | None
    filter: str | None
    gain: int | None
    offset: int | None
    set_temp_c: float | None
    ccd_temp_c: float | None
    date_obs_utc: datetime | None
    night: date | None
    xbin: int | None
    ybin: int | None
    width: int | None
    height: int | None
    needs: list[str]  # every field this file still waits for, across its open items
    first_night: date | None  # across the group's files
    last_night: date | None


class ReconciliationOut(Schema):
    id: int
    kind: str
    reason: str
    field: str | None
    frame: FrameSummaryOut | None
    dataset_id: int | None
    suggestion: dict | None
    status: str
    created_at: datetime
    group: str = ""  # kind, field, library and folder: one answer fixes the lot
    example: ReconExampleOut | None = None  # on the first item of each group only


class ResolveIn(Schema):
    accept_suggestion: bool = False
    value: str | float | int | None = None
    apply_to_similar: bool = False


class ResolvedOut(Schema):
    resolved: int


# ---- path patterns ----------------------------------------------------------------------------------------
def _validate(data: dict) -> list[str]:
    try:
        compiled = compile_pattern(data["pattern"], data["kind"])
    except PatternError as e:
        raise ApiError(422, "invalid_pattern", str(e)) from None
    bad = [f for f in data.get("prefer_over_header") or [] if f not in MetadataField.values]
    if bad:
        raise ApiError(422, "invalid_pattern", f"“{bad[0]}” isn't a field a pattern can fill.")
    if data.get("library_id") is not None and not Library.objects.filter(pk=data["library_id"]).exists():
        raise ApiError(422, "invalid_pattern", "That library doesn't exist.")
    return sorted(compiled.fields())


def _pattern_out(p: PathPattern) -> PathPatternOut:
    try:
        fields, error = sorted(compile_pattern(p.pattern, p.kind).fields()), None
    except PatternError as e:
        fields, error = [], str(e)
    return PathPatternOut(
        id=p.pk,
        library_id=p.library_id,
        scope_glob=p.scope_glob,
        kind=p.kind,  # type: ignore[arg-type]
        pattern=p.pattern,
        prefer_over_header=p.prefer_over_header or [],
        priority=p.priority,
        enabled=p.enabled,
        fields=fields,
        error=error,
    )


def _reresolve(library_id: int | None) -> None:
    from apps.ingest.tasks.reresolve import reresolve_library

    enqueue(reresolve_library, library_id, dedupe_key=f"reresolve:{library_id}")


@router.get("/path-patterns", response=list[PathPatternOut])
def list_patterns(request):
    return [_pattern_out(p) for p in PathPattern.objects.all()]


@router.post("/path-patterns", response={201: PathPatternOut})
@admin_required
def create_pattern(request, body: PathPatternIn):
    data = body.dict()
    _validate(data)
    p = PathPattern.objects.create(created_by=request.user, **data)
    _reresolve(p.library_id)
    return Status(201, _pattern_out(p))


def _preview_diff(frame, got: dict, prefer: set[str]) -> list[PreviewChange]:  # noqa: ANN001
    """What a pattern's values would change on one frame: a field its header already gives is left alone
    unless the pattern is preferred over the header for it (a target or panel still comes from the path when
    the header names no OBJECT), and a value equal to the current one (as text, or as the same number) is no
    change."""
    diff = []
    header = set(frame.metadata.filter(source="header").exclude(value=None).values_list("field", flat=True))
    for f, v in got.items():
        if f in header and f not in prefer and not (f in ("target", "panel") and "object" not in header):
            continue  # the header keeps this value
        attr = RESOLVED_FIELD.get(f)
        cur = getattr(frame, attr) if attr else None
        new = v.isoformat() if isinstance(v, datetime) else str(v)
        curs = cur.isoformat() if isinstance(cur, datetime) else (None if cur is None else str(cur))
        if curs != new and not (cur is not None and _same_number(cur, v)):
            diff.append(PreviewChange(field=f, current=curs, new=new))
    return diff


@router.post("/path-patterns/preview", response=PreviewOut)
def preview_pattern(request, body: PreviewIn):
    data = body.pattern.dict()
    fields = _validate(data)
    compiled = compile_pattern(data["pattern"], data["kind"])
    lon = InstallationSettings.load().site_lon
    copies = Copy.objects.filter(present=True).select_related("frame", "library")
    if data.get("library_id") is not None:
        copies = copies.filter(library_id=data["library_id"])
    probe = PathPattern(library_id=data.get("library_id"), scope_glob=data.get("scope_glob") or "**")
    from apps.ingest.resolve import _in_scope

    samples_in = body.sample_paths
    matching = 0
    changes: list[PreviewFrame] = []
    for c in copies.iterator(chunk_size=2000):
        if not _in_scope(probe, c):
            continue
        got = match(compiled, c.rel_path, site_lon=c.frame.site_lon if c.frame.site_lon is not None else lon)
        if not got:
            continue
        matching += 1
        if len(changes) < 50 and matching <= 500:  # bounded work per keystroke
            diff = _preview_diff(c.frame, got, set(data.get("prefer_over_header") or []))
            if diff:
                changes.append(
                    PreviewFrame(sha256=c.frame_id, path=f"{c.library.name}/{c.rel_path}", changes=diff)
                )
    if not samples_in:  # no samples given: show some real paths from the scope
        samples_in = [c.rel_path for c in copies.order_by("-pk")[:200] if _in_scope(probe, c)][:12]
    samples = []
    for path in samples_in:
        got = match(compiled, path, site_lon=lon)
        samples.append(
            PreviewSample(
                path=path,
                matched=got is not None,
                values={k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in (got or {}).items()},
            )
        )
    return PreviewOut(fields=fields, samples=samples, matching_files=matching, would_change=changes)


@router.patch("/path-patterns/{id}", response=PathPatternOut)
@admin_required
def patch_pattern(request, id: int, body: PathPatternPatch):  # noqa: A002
    p = get_object_or_404(PathPattern, pk=id)
    old_lib = p.library_id
    changes = body.dict(exclude_unset=True)
    for k, v in changes.items():
        if v is not None or k == "library_id":
            setattr(p, k, v)
    _validate(
        {
            "pattern": p.pattern,
            "kind": p.kind,
            "prefer_over_header": p.prefer_over_header,
            "library_id": p.library_id,
        }
    )
    p.save()
    _reresolve(p.library_id if p.library_id == old_lib else None)
    return _pattern_out(p)


@router.delete("/path-patterns/{id}", response={204: None})
@admin_required
def delete_pattern(request, id: int):  # noqa: A002
    p = get_object_or_404(PathPattern, pk=id)
    lib = p.library_id
    p.delete()
    _reresolve(lib)
    return Status(204, None)


def _same_number(a: object, b: object) -> bool:
    try:
        return float(a) == float(b)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


# ---- corrections ------------------------------------------------------------------------------------------
@router.post("/frames/metadata", response=UpdatedOut)
def set_metadata(request, body: MetadataIn):
    if len(body.sha256s) > 10000:
        raise ApiError(422, "too_many", "Up to 10,000 files at a time.")
    try:
        n = set_value(body.sha256s, body.field, body.value, request.user)
    except CorrectionError as e:
        raise ApiError(422, "invalid_value", str(e)) from None
    return UpdatedOut(updated=n)


@router.post("/frames/classification", response=UpdatedOut)
def set_classification(request, body: ClassificationIn):
    try:
        n = set_value(body.sha256s, "frame_type", body.frame_type, request.user)
    except CorrectionError as e:
        raise ApiError(422, "invalid_value", str(e)) from None
    return UpdatedOut(updated=n)


# ---- reconciliation ---------------------------------------------------------------------------------------
def _item_out(i: ReconciliationItem) -> ReconciliationOut:
    if i.kind == ReconciliationKind.MASTER_METADATA and i.suggestion is None and i.frame is not None:
        # lights catalogued after the master can now suggest a value
        from apps.ingest.resolve import _master_suggestion

        i.suggestion = _master_suggestion(i.frame, i.field, list(i.frame.copies.filter(present=True)))
        if i.suggestion is not None:
            ReconciliationItem.objects.filter(pk=i.pk).update(suggestion=i.suggestion)
    return ReconciliationOut(
        id=i.pk,
        kind=i.kind,
        reason=i.reason,
        field=i.field or None,
        frame=frame_summary(i.frame) if i.frame is not None else None,
        dataset_id=i.dataset_id if i.dataset_id is not None else (i.frame.dataset_id if i.frame else None),
        suggestion=i.suggestion,
        status=i.status,
        created_at=i.created_at,
    )


def _path_ignored(f: Frame, rules: PathRules) -> bool:
    """Covered by a folder or glob rule already, before the worker has marked it ignored (copies prefetched)."""
    present = [c for c in f.copies.all() if c.present]
    return bool(present) and all(rules.matches(c.library_id, c.rel_path) for c in present)


def _group_key(i: ReconciliationItem) -> str:
    c = primary_copy(i.frame) if i.frame is not None else None
    where = f"{c.library_id}|{os.path.dirname(c.rel_path)}" if c else "|"
    return f"{i.kind}|{i.field}|{where}"


def _examples(groups: dict[str, list[ReconciliationItem]]) -> dict[str, ReconExampleOut]:
    """One file's values per group. Two queries for all of them: open fields and image sizes."""
    firsts = {k: next((i for i in its if i.frame is not None), None) for k, its in groups.items()}
    shas = [i.frame_id for i in firsts.values() if i is not None]
    needs: dict[str, set[str]] = {}
    for sha, field in (
        ReconciliationItem.objects.filter(status=ReconciliationStatus.OPEN, frame_id__in=shas)
        .exclude(field="")
        .values_list("frame_id", "field")
    ):
        needs.setdefault(sha, set()).add(field)
    sizes: dict[str, tuple[int, int]] = {}
    for sha, geometry in (
        HeaderSnapshot.objects.filter(frame_id__in=shas)
        .order_by("-image_index")  # the first image wins
        .values_list("frame_id", "geometry")
    ):
        dims = [int(p) for p in geometry.split(":") if p.isdigit()]
        if len(dims) >= 2:
            sizes[sha] = (dims[0], dims[1])
    out = {}
    for key, i in firsts.items():
        if i is None or i.frame is None:
            continue
        f = i.frame
        c = primary_copy(f)
        nights = [
            x.frame.night.date for x in groups[key] if x.frame is not None and x.frame.night is not None
        ]
        w, h = sizes.get(f.sha256, (None, None))
        out[key] = ReconExampleOut(
            sha256=f.sha256,
            frame_type=f.frame_type,
            library_id=c.library_id if c else None,
            library=c.library.name if c else None,
            folder=os.path.dirname(c.rel_path) if c else "",
            file_name=os.path.basename(c.rel_path) if c else f.sha256[:12],
            camera=f.camera,
            telescope=f.telescope,
            exptime_s=f.exptime_s,
            filter=f.filter_norm or f.filter_raw,
            gain=f.gain,
            offset=f.offset,
            set_temp_c=f.set_temp_c,
            ccd_temp_c=f.ccd_temp_c,
            date_obs_utc=f.date_obs_utc,
            night=f.night.date if f.night else None,
            xbin=f.xbin,
            ybin=f.ybin,
            width=w,
            height=h,
            needs=sorted(needs.get(f.sha256, ())),
            first_night=min(nights, default=None),
            last_night=max(nights, default=None),
        )
    return out


@router.get("/reconciliation", response=list[ReconciliationOut])
def list_reconciliation(
    request, status: Literal["open", "resolved", "dismissed"] = "open", kind: str | None = None
):
    """Items with the group each belongs to; the first of each group carries an example file's values."""
    qs = (
        ReconciliationItem.objects.filter(status=status)
        .exclude(frame__status=FrameStatus.IGNORED)
        .select_related("frame__night")
        .prefetch_related("frame__copies__library", "frame__verdicts")
    )
    if kind:
        qs = qs.filter(kind=kind)
    rows = list(qs.order_by("kind", "field", "-created_at")[:2000])
    rules = PathRules.load()
    if rules.rules:  # a rule just added: its files leave the list before the worker gets to them
        rows = [i for i in rows if i.frame is None or not _path_ignored(i.frame, rules)]
    groups: dict[str, list[ReconciliationItem]] = {}
    for i in rows:
        groups.setdefault(_group_key(i), []).append(i)
    examples = _examples(groups)
    out = []
    for key, items in groups.items():
        for n, i in enumerate(items):
            o = _item_out(i)
            o.group = key
            o.example = examples.get(key) if n == 0 else None
            out.append(o)
    return out


@router.get("/reconciliation/counts", response=dict[str, int])
def reconciliation_counts(request):
    return dict(
        ReconciliationItem.objects.filter(status=ReconciliationStatus.OPEN)
        .exclude(frame__status=FrameStatus.IGNORED)
        .values_list("kind")
        .annotate(n=Count("id"))
    )


def _folder(item: ReconciliationItem) -> tuple[int, str] | None:
    c = item.frame.copies.filter(present=True).first() if item.frame else None
    return (c.library_id, os.path.dirname(c.rel_path)) if c else None


def _similar(item: ReconciliationItem) -> list[ReconciliationItem]:
    """Open items of the same kind and field for files in the same folder."""
    where = _folder(item)
    if where is None:
        return [item]
    lib, folder = where
    prefix = f"{folder}/" if folder else ""
    out = []
    for other in ReconciliationItem.objects.filter(
        status=ReconciliationStatus.OPEN,
        kind=item.kind,
        field=item.field,
        frame__copies__library_id=lib,
        frame__copies__rel_path__startswith=prefix,
    ).distinct():
        if _folder(other) == where:
            out.append(other)
    return out or [item]


@router.post("/reconciliation/{id}/resolve", response=ResolvedOut)
def resolve_item(request, id: int, body: ResolveIn):  # noqa: A002
    item = get_object_or_404(ReconciliationItem, pk=id)
    if item.status != ReconciliationStatus.OPEN:
        raise ApiError(409, "not_open", "This item has already been dealt with.")
    items = _similar(item) if body.apply_to_similar else [item]
    now = timezone.now()
    if item.kind in (
        ReconciliationKind.MISSING_FIELD,
        ReconciliationKind.CLASSIFICATION_UNKNOWN,
        ReconciliationKind.MASTER_METADATA,
    ):
        value = (item.suggestion or {}).get("value") if body.accept_suggestion else body.value
        if value in (None, ""):
            raise ApiError(422, "invalid_value", "Give a value, or accept the suggestion.")
        field = item.field or "frame_type"
        try:
            set_value([i.frame_id for i in items if i.frame_id], field, value, request.user)
        except CorrectionError as e:
            raise ApiError(422, "invalid_value", str(e)) from None
        resolution = {"by": "user", "value": value}
    else:  # informational, or missing files: acknowledged
        resolution = {"by": "user", "acknowledged": True}
    ids = [i.pk for i in items]
    ReconciliationItem.objects.filter(pk__in=ids).update(
        status=ReconciliationStatus.RESOLVED, resolved_by=request.user, resolved_at=now, resolution=resolution
    )
    _touch(items)
    return ResolvedOut(resolved=len(ids))


@router.post("/reconciliation/{id}/dismiss", response=ResolvedOut)
def dismiss_item(request, id: int):  # noqa: A002
    item = get_object_or_404(ReconciliationItem, pk=id)
    ReconciliationItem.objects.filter(pk=item.pk).update(
        status=ReconciliationStatus.DISMISSED, resolved_by=request.user, resolved_at=timezone.now()
    )
    _touch([item])
    return ResolvedOut(resolved=1)


def _touch(items: list[ReconciliationItem]) -> None:
    seen = set()
    for i in items:
        frame = Frame.objects.filter(pk=i.frame_id).select_related("dataset").first() if i.frame_id else None
        ds = frame.dataset if frame else None
        if ds is not None and ds.pk not in seen:
            seen.add(ds.pk)
            touch_dataset(ds)
