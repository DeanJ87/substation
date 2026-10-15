"""Calibration sets (T095): raw flats, darks, dark flats and bias grouped by type, camera, filter (flats),
exposure, gain, offset and binning, then by session. Frames more than 2 hours apart start a new session; a
frame that bridges two sessions merges them. Maintained incrementally as frames are catalogued."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.db import transaction
from django.db.models import Max, Min

from ..models import CALIBRATION_TYPES, CalibrationSet, Frame, FrameStatus, FrameType

SESSION_GAP = timedelta(hours=2)


def _key(frame: Frame) -> dict:
    return {
        "type": frame.frame_type,
        "camera": frame.camera or "",
        "filter_norm": frame.filter_norm if frame.frame_type == FrameType.FLAT else None,
        "exptime_s": frame.exptime_s,
        "gain": frame.gain,
        "offset": frame.offset,
        "xbin": frame.xbin or 1,
        "ybin": frame.ybin or frame.xbin or 1,
    }


FLAT_EXPOSURE_TOLERANCE = (
    0.05  # NINA's flat wizard varies a flat's exposure a little run to run (0.00654 / 0.00655 s)
)


def _matching(key: dict):  # noqa: ANN202
    qs = CalibrationSet.objects.all()
    for k, v in key.items():
        if k == "exptime_s" and v and key.get("type") == FrameType.FLAT:
            # flats of one filter and session are one set when their exposures are within 5% (002-DR-24); darks and
            # bias stay exact, since a dark must match its light's exposure
            qs = qs.filter(
                exptime_s__gte=v * (1 - FLAT_EXPOSURE_TOLERANCE),
                exptime_s__lte=v * (1 + FLAT_EXPOSURE_TOLERANCE),
            )
        else:
            qs = qs.filter(**{f"{k}__isnull": True}) if v is None else qs.filter(**{k: v})
    return qs


def recount(cs: CalibrationSet) -> bool:
    """Recompute a set from its members; delete it when empty. Returns False if deleted."""
    members = Frame.objects.filter(calibration_set=cs, status=FrameStatus.CATALOGUED)
    agg = members.aggregate(first=Min("date_obs_utc"), last=Max("date_obs_utc"))
    if agg["first"] is None:
        Frame.objects.filter(calibration_set=cs).update(calibration_set=None)
        cs.delete()
        return False
    cs.frame_count = members.count()
    cs.session_start_utc, cs.session_end_utc = agg["first"], agg["last"]
    first = members.order_by("date_obs_utc").first()
    cs.night = first.night if first else None
    temps = [t for t in members.values_list("set_temp_c", flat=True) if t is not None]
    cs.set_temp_c = Counter(temps).most_common(1)[0][0] if temps else None
    if cs.type in (FrameType.DARK, FrameType.DARK_FLAT, FrameType.BIAS):
        labels = Counter(f or "none" for f in members.values_list("filter_norm", flat=True))
        cs.filter_blocks = dict(labels)
    cs.save()
    return True


def assign_calibration_set(frame: Frame) -> tuple[CalibrationSet | None, CalibrationSet | None]:
    """Place a calibration frame in its set (creating or merging sets as needed). Sets frame.calibration_set
    (not saved). Returns (old set, new set) so both can be recounted after the frame is saved."""
    # looked up, not followed: during a long re-read another frame can merge this frame's set away, and following
    # the stale link failed the whole re-read at 90% (2026-10-14)
    old = (
        CalibrationSet.objects.filter(pk=frame.calibration_set_id).first()
        if frame.calibration_set_id
        else None
    )
    if old is None and frame.calibration_set_id:
        frame.calibration_set = None
    t = frame.date_obs_utc
    eligible = (
        frame.frame_type in CALIBRATION_TYPES
        and frame.status == FrameStatus.CATALOGUED
        and frame.exptime_s is not None
    )
    if not eligible or t is None:
        frame.calibration_set = None
        return old, None
    key = _key(frame)
    near = list(
        _matching(key)
        .filter(session_start_utc__lte=t + SESSION_GAP, session_end_utc__gte=t - SESSION_GAP)
        .order_by("session_start_utc")
    )
    with transaction.atomic():
        if old is not None and old in near:
            target = old
        elif near:
            target = near[0]
        else:
            target = CalibrationSet.objects.create(
                **key, session_start_utc=t, session_end_utc=t, night=frame.night, frame_count=0
            )
        for other in near:  # this frame bridges sessions: merge them into one
            if other.pk != target.pk:
                Frame.objects.filter(calibration_set=other).update(calibration_set=target)
                other.delete()
        if t < target.session_start_utc or t > target.session_end_utc:
            target.session_start_utc = min(target.session_start_utc, t)
            target.session_end_utc = max(target.session_end_utc, t)
            target.save(update_fields=["session_start_utc", "session_end_utc"])
    frame.calibration_set = target
    return old, target


def flat_set_for_dark(frame: Frame) -> CalibrationSet | None:
    """A flat set on the same night with this dark's exposure, gain, offset and binning: the dark is then a
    dark flat (NINA's flat wizard takes them right after the flats)."""
    if frame.night_id is None or frame.exptime_s is None:
        return None
    qs = CalibrationSet.objects.filter(
        type=FrameType.FLAT,
        night_id=frame.night_id,
        exptime_s=frame.exptime_s,
        xbin=frame.xbin or 1,
        ybin=frame.ybin or frame.xbin or 1,
        camera=frame.camera or "",
    )
    qs = qs.filter(gain__isnull=True) if frame.gain is None else qs.filter(gain=frame.gain)
    qs = qs.filter(offset__isnull=True) if frame.offset is None else qs.filter(offset=frame.offset)
    return qs.order_by("-frame_count").first()


def recheck_darks_for(flat_set: CalibrationSet) -> int:
    """After a flat set is created or grows, darks that match it become dark flats (unless the user set their
    type). Returns the number of darks re-resolved."""
    from apps.ingest.resolve import resolve_frame

    if flat_set.night_id is None:
        return 0
    darks = Frame.objects.filter(
        frame_type=FrameType.DARK,
        status=FrameStatus.CATALOGUED,
        night_id=flat_set.night_id,
        exptime_s=flat_set.exptime_s,
    ).exclude(classification_source="user")
    if flat_set.camera:
        darks = darks.filter(camera=flat_set.camera)
    n = 0
    touched: set[int] = set()
    for d in darks:
        old_set = d.calibration_set_id
        resolve_frame(d)
        if old_set:
            touched.add(old_set)
        n += 1
    for cs in CalibrationSet.objects.filter(pk__in=touched):
        recount(cs)
    return n
