"""Read endpoints for datasets and frames (T056; contracts/openapi.yaml). No `from __future__ import
annotations` here: see substation.api."""

from datetime import date, datetime

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404

from substation.api import Query, Router, Schema, decode_cursor, encode_cursor

from .models import Copy, Dataset, Frame, FrameType, Verdict
from .scope import Scope, apply, text_q, without
from .services.library import label

router = Router(tags=["catalogue"])


# ---- schemas ----------------------------------------------------------------------------------------------
class DatasetOut(Schema):
    id: int
    display_name: str
    target: str
    panel: int | None
    filter: str
    camera: str
    telescope: str
    binning: str
    gain: int | None
    offset: int | None
    state: str
    state_reason: str | None
    sub_count: int
    user_rejected_count: int
    integration_s: float
    nights: int
    first_utc: datetime | None
    last_utc: datetime | None
    last_night: date | None
    last_night_subs: int
    label: str
    rig: str | None
    collection_id: int | None
    collection: str | None
    accepted_count: int
    down_count: int
    rejected_count: int
    awaiting_count: int
    manual_count: int
    accepted_integration_s: float


class DatasetPage(Schema):
    items: list[DatasetOut]
    next_cursor: str | None


class FrameSummaryOut(Schema):
    sha256: str
    frame_type: str
    status: str
    target: str | None
    panel: int | None
    filter: str | None
    exptime_s: float | None
    ccd_temp_c: float | None
    date_obs_utc: datetime | None
    night: date | None
    dataset_id: int | None
    user_verdict: str | None
    primary_path: str
    copies: int


class FramePage(Schema):
    items: list[FrameSummaryOut]
    next_cursor: str | None


class MetadataFieldOut(Schema):
    field: str
    value: str | None
    raw: str | None
    source: str
    source_detail: str | None
    is_winner: bool
    set_by: str | None
    at: datetime


class CopyOut(Schema):
    library: str
    path: str
    present: bool
    is_bad_prefixed: bool
    first_seen_at: datetime
    last_seen_at: datetime


class HistoryOut(Schema):
    kind: str
    details: dict
    at: datetime


class VerdictOut(Schema):
    verdict: str
    source: str
    by: str | None
    at: datetime


class HeaderOut(Schema):
    image_index: int
    image_id: str
    geometry: str
    sample_format: str
    keywords: dict
    properties: dict


class ConflictOut(Schema):
    field: str
    values: dict[str, str | None]


class FrameOut(FrameSummaryOut):
    classification_reason: str
    classification_source: str
    error: str | None
    size_bytes: int
    format: str
    image_count: int
    integration_index: int | None
    metadata: list[MetadataFieldOut]
    conflicts: list[ConflictOut]
    copy_list: list[CopyOut]
    history: list[HistoryOut]
    verdicts: list[VerdictOut]
    headers: list[HeaderOut]
    site_lat: float | None = None  # where it was shot, for the map (spec 012)
    site_lon: float | None = None


# ---- helpers ----------------------------------------------------------------------------------------------
def dataset_out(d: Dataset) -> DatasetOut:
    last = d.nights.select_related("night").order_by("-night__date").first()
    return DatasetOut(
        id=d.pk,
        display_name=d.display_name,
        target=d.target,
        panel=d.panel,
        filter=d.filter_norm,
        camera=d.camera,
        telescope=d.telescope,
        binning=f"{d.xbin}x{d.ybin}",
        gain=d.gain,
        offset=d.offset,
        state=d.state,
        state_reason=d.state_reason or None,
        sub_count=d.sub_count,
        user_rejected_count=d.user_rejected_count,
        integration_s=d.integration_s,
        nights=d.nights.count(),
        first_utc=d.first_utc,
        last_utc=d.last_utc,
        last_night=last.night.date if last else None,
        last_night_subs=last.sub_count if last else 0,
        label=label(d),
        rig=d.rig.name if d.rig_id and d.rig else None,
        collection_id=d.collection_id,
        collection=d.collection.name if d.collection_id and d.collection else None,
        accepted_count=d.accepted_count,
        down_count=d.down_count,
        rejected_count=d.rejected_count,
        awaiting_count=d.awaiting_count,
        manual_count=d.manual_count,
        accepted_integration_s=d.accepted_integration_s,
    )


def primary_copy(f: Frame) -> Copy | None:
    """The copy a frame is shown by: a present, unprefixed one if there is one (copies prefetched)."""
    return next((c for c in f.copies.all() if c.present and not c.is_bad_prefixed), None) or next(
        iter(f.copies.all()), None
    )


def _primary_path(f: Frame) -> str:
    c = primary_copy(f)
    return f"{c.library.name}/{c.rel_path}" if c else ""


def _user_verdict(f: Frame) -> str | None:
    v = max(f.verdicts.all(), key=lambda v: v.created_at, default=None)
    return v.verdict if v else None


def frame_summary(f: Frame) -> FrameSummaryOut:
    return FrameSummaryOut(
        sha256=f.sha256,
        frame_type=f.frame_type,
        status=f.status,
        target=f.target,
        panel=f.panel,
        filter=f.filter_norm,
        exptime_s=f.exptime_s,
        ccd_temp_c=f.ccd_temp_c,
        date_obs_utc=f.date_obs_utc,
        night=f.night.date if f.night else None,
        dataset_id=f.dataset_id,
        user_verdict=_user_verdict(f),
        primary_path=_primary_path(f),
        copies=len(f.copies.all()),
    )


# ---- datasets ---------------------------------------------------------------------------------------------
@router.get("/datasets", response=DatasetPage)
def list_datasets(
    request,
    scope: Query[Scope],
    state: str | None = None,
    cursor: str | None = None,
    limit: int = Query(100, le=1000, ge=1),
):
    """Datasets in the shared scope (spec 018). `target` here keeps its older meaning, part of the name (FR-005):
    every exact match is also a partial one, so a scope carried from another page still finds its target."""
    qs = apply(Dataset.objects.filter(sub_count__gt=0), without(scope, "target"), "dataset")
    if state:
        qs = qs.filter(state=state)
    if scope.target:
        qs = qs.filter(target__icontains=scope.target.strip())
    qs = qs.order_by("-last_utc", "-id")
    c = decode_cursor(cursor)
    if c:
        qs = qs.filter(Q(last_utc__lt=c["t"]) | Q(last_utc=c["t"], id__lt=c["id"]) | Q(last_utc=None))
    rows = list(qs[: limit + 1])
    nxt = (
        encode_cursor({"t": rows[limit - 1].last_utc, "id": rows[limit - 1].pk})
        if len(rows) > limit
        else None
    )
    return DatasetPage(items=[dataset_out(d) for d in rows[:limit]], next_cursor=nxt)


@router.get("/datasets/{id}", response=DatasetOut)
def get_dataset(request, id: int):  # noqa: A002 (contract path parameter name)
    return dataset_out(get_object_or_404(Dataset, pk=id))


# ---- frames -----------------------------------------------------------------------------------------------
@router.get("/frames", response=FramePage)
def list_frames(
    request,
    scope: Query[Scope],
    night: date | None = None,
    type: str | None = None,  # noqa: A002
    status: str | None = None,
    cursor: str | None = None,
    limit: int = Query(100, le=1000, ge=1),
):
    """Frames in the shared scope (spec 018); `night` is the older name for `date` (FR-005). Free text also finds
    a frame by its OBJECT header or its file's path."""
    qs = apply(Frame.objects.all(), without(scope, "q"), "frame")
    if night is not None:
        qs = qs.filter(night__date=night)
    if type:
        qs = qs.filter(frame_type=type)
    if status:
        qs = qs.filter(status=status)
    if q := (scope.q or "").strip():
        qs = qs.filter(
            text_q(q, "frame") | Q(object__icontains=q) | Q(copies__rel_path__icontains=q)
        ).distinct()
    qs = qs.order_by("date_obs_utc", "sha256")
    c = decode_cursor(cursor)
    if c:
        if c.get("t") is None:
            qs = qs.filter(date_obs_utc=None, sha256__gt=c["s"])
        else:
            qs = qs.filter(Q(date_obs_utc__gt=c["t"]) | Q(date_obs_utc=c["t"], sha256__gt=c["s"]))
    rows = list(qs.select_related("night").prefetch_related("copies__library", "verdicts")[: limit + 1])
    nxt = None
    if len(rows) > limit:
        last = rows[limit - 1]
        nxt = encode_cursor(
            {"t": last.date_obs_utc.isoformat() if last.date_obs_utc else None, "s": last.sha256}
        )
    return FramePage(items=[frame_summary(f) for f in rows[:limit]], next_cursor=nxt)


@router.get("/frames/{sha256:sha256}", response=FrameOut)
def get_frame(request, sha256: str):
    f = get_object_or_404(
        Frame.objects.select_related("night").prefetch_related("copies__library", "verdicts__user"), pk=sha256
    )
    base = frame_summary(f).dict()
    meta = [
        MetadataFieldOut(
            field=m.field,
            value=m.value,
            raw=m.raw,
            source=m.source,
            source_detail=m.source_detail or None,
            is_winner=m.is_winner,
            set_by=m.user.get_username() if m.user else None,
            at=m.created_at,
        )
        for m in f.metadata.select_related("user").order_by("field", "-is_winner", "source")
    ]
    return FrameOut(
        **base,
        classification_reason=f.classification_reason,
        classification_source=f.classification_source,
        error=f.error,
        size_bytes=f.size_bytes,
        format=f.format,
        image_count=f.image_count,
        integration_index=f.integration_index,
        site_lat=f.site_lat,
        site_lon=f.site_lon,
        metadata=meta,
        conflicts=[ConflictOut(field=c.field, values=c.values) for c in f.conflicts.all()],
        copy_list=[
            CopyOut(
                library=c.library.name,
                path=c.rel_path,
                present=c.present,
                is_bad_prefixed=c.is_bad_prefixed,
                first_seen_at=c.first_seen_at,
                last_seen_at=c.last_seen_at,
            )
            for c in f.copies.all()
        ],
        history=[
            HistoryOut(kind=e.kind, details=e.details, at=e.created_at)
            for e in f.history.order_by("created_at")
        ],
        verdicts=[
            VerdictOut(
                verdict=v.verdict,
                source=v.source,
                by=v.user.get_username() if v.user else None,
                at=v.created_at,
            )
            for v in f.verdicts.order_by("created_at")
        ],
        headers=[
            HeaderOut(
                image_index=h.image_index,
                image_id=h.image_id,
                geometry=h.geometry,
                sample_format=h.sample_format,
                keywords=h.keywords,
                properties=h.properties,
            )
            for h in f.headers.order_by("image_index")
        ],
    )


__all__ = ["router", "Copy", "Count", "FrameType", "Verdict"]
