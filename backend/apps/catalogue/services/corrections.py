"""User corrections (T076): a value the user gives for a field, keyed by content so it applies to every copy
and to identical files found later. Frame type overrides go through here too (constitution VIII)."""

from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction

from substation.events.emit import emit

from ..models import ContentCorrection, Dataset, Frame, MetadataField, MetadataSource, MetadataValue
from .tracking import touch_dataset

INT_FIELDS = {"panel", "gain", "offset", "xbin", "ybin"}
LABELS = {
    "exptime": "Exposure",
    "ccd_temp": "Sensor temperature",
    "set_temp": "Set temperature",
    "xbin": "Binning",
    "ybin": "Binning",
    "site_lat": "Latitude",
    "site_lon": "Longitude",
    "date_obs": "Observation time",
}
FLOAT_FIELDS = {"exptime", "ccd_temp", "set_temp", "site_lat", "site_lon"}
EDITABLE = {f.value for f in MetadataField}


class CorrectionError(ValueError):
    """A value that can't be stored for that field, with a message for the user."""


def normalise(field: str, value: object) -> str | None:
    """Validate a user value; return its stored text (None removes the user value)."""
    if field not in EDITABLE:
        raise CorrectionError(f"“{field}” isn't a field that can be set.")
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip()
    try:
        if field in INT_FIELDS:
            return str(int(float(text)))
        if field in FLOAT_FIELDS:
            return repr(float(text))
    except ValueError:
        label = LABELS.get(field, field.replace("_", " ").capitalize())
        raise CorrectionError(f"{label} must be a number; “{text}” isn't one.") from None
    if field == "frame_type":
        from apps.ingest.classify import normalise_type

        t = normalise_type(text)
        if t is None:
            raise CorrectionError(
                f"“{text}” isn't a frame type. Use light, flat, dark, dark flat, bias or a master type."
            )
        return t.value
    if field == "date_obs":
        from apps.ingest.night import parse_date_obs

        when = parse_date_obs(text)
        if when is None:
            raise CorrectionError(f"“{text}” isn't a date and time. Use the form 2026-09-28T20:05:02 (UTC).")
        return when.isoformat()
    return text


def set_value(sha256s: Iterable[str], field: str, value: object, user) -> int:  # noqa: ANN001
    """Store the value for each frame's content, re-resolve and regroup. Returns frames updated."""
    from apps.ingest.resolve import resolve_frame

    text = normalise(field, value)
    touched: dict[int, Dataset] = {}
    n = 0
    for sha in dict.fromkeys(sha256s):
        frame = Frame.objects.filter(pk=sha).first()
        if frame is None:
            continue
        with transaction.atomic():
            # a fresh user row, so it carries this correction's time and author
            MetadataValue.objects.filter(frame=frame, field=field, source=MetadataSource.USER).delete()
            if text is None:
                ContentCorrection.objects.filter(sha256=sha, field=field).delete()
            else:
                ContentCorrection.objects.update_or_create(
                    sha256=sha, field=field, defaults={"value": text, "user": user}
                )
            old, new = resolve_frame(frame)
        for d in (old, new):
            if d is not None:
                touched[d.pk] = d
        emit("frame.updated", {"sha256": sha, "fields": [field]})
        n += 1
    for d in touched.values():
        touch_dataset(d)
    return n
