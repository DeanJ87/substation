"""Calibration library queries (T093): sets by type and night with their filter blocks, and imported masters
with the values calibration matching needs."""

from __future__ import annotations

from datetime import date

from django.db.models import QuerySet

from ..models import MASTER_TYPES, CalibrationSet, Frame, FrameStatus, MetadataSource


def calibration_sets(type_: str | None = None, night: date | None = None) -> QuerySet[CalibrationSet]:
    qs = CalibrationSet.objects.select_related("night").order_by("-session_start_utc", "type", "filter_norm")
    if type_:
        qs = qs.filter(type=type_)
    if night:
        qs = qs.filter(night__date=night)
    return qs


def masters() -> QuerySet[Frame]:
    return (
        Frame.objects.filter(frame_type__in=MASTER_TYPES)
        .exclude(status=FrameStatus.IGNORED)
        .select_related("night")
        .prefetch_related("copies__library", "verdicts", "metadata")
        .order_by("frame_type", "filter_norm", "exptime_s")
    )


def value_sources(frame: Frame, fields: tuple[str, ...]) -> dict[str, str | None]:
    """field -> where the winning value came from (header keyword, pattern, user), None when missing."""
    out: dict[str, str | None] = dict.fromkeys(fields)
    for m in frame.metadata.all():
        if m.is_winner and m.field in out:
            out[m.field] = (
                f"header {m.source_detail}"
                if m.source == MetadataSource.HEADER
                else f"set by {m.user.get_username()}"
                if m.source == MetadataSource.USER and m.user
                else f"{m.source.replace('_', ' ')} {m.source_detail}".strip()
            )
    return out
