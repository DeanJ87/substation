"""Processed copies (found on the owner's archive 2026-10-10): PixInsight writes 32-bit float XISF next to the raw
16-bit captures, with the same DATE-OBS and camera. Treated as lights they are calibrated a second time (their
backgrounds go negative) and counted twice. A float light with a raw twin is set aside by an ignore rule on its
content, noted "Processed copy of <raw file>", so it shows in Settings → Ignored and can be undone.

8-bit captures (owner 2026-10-13): early Sony A7 III files saved as 8-bit RGB, already processed by the camera.
They can't be calibrated or stacked with raw data, so every one (light, flat or dark) is set aside the same way,
noted as 8-bit, for the owner to delete later."""

from __future__ import annotations

from apps.catalogue.models import Copy, Frame, FrameStatus, FrameType, IgnoreKind, IgnoreRule


def _is_float(f: Frame) -> bool:
    h = next(iter(f.headers.all()), None)
    fmt = (h.sample_format if h else "") or ""
    return "Float" in fmt or "BITPIX=-32" in fmt or "BITPIX=-64" in fmt


EIGHT_BIT_NOTE = "8-bit capture: camera-processed data, not raw"


def is_eight_bit(f: Frame) -> bool:
    return any(
        (h.sample_format or "").replace(" ", "").upper() in ("BITPIX=8", "UINT8") for h in f.headers.all()
    )


def raw_twin(f: Frame) -> Frame | None:
    """The raw (integer) light this float light was made from, if SubStation has it."""
    if f.frame_type != FrameType.LIGHT or f.date_obs_utc is None or not _is_float(f):
        return None
    twins = (
        Frame.objects.filter(frame_type=FrameType.LIGHT, date_obs_utc=f.date_obs_utc, camera=f.camera)
        .exclude(pk=f.pk)
        .exclude(status=FrameStatus.IGNORED)
        .prefetch_related("headers")
    )
    return next((t for t in twins if not _is_float(t)), None)


def set_aside(f: Frame) -> bool:
    """Ignore `f` if it is an 8-bit capture or a processed copy of a raw light. Returns True when a rule was made."""
    if IgnoreRule.objects.filter(active=True, kind=IgnoreKind.CONTENT, value=f.sha256).exists():
        return False
    if is_eight_bit(f):
        note = EIGHT_BIT_NOTE
    else:
        twin = raw_twin(f)
        if twin is None:
            return False
        copy = Copy.objects.filter(frame=twin, present=True).first()
        note = f"Processed copy of {copy.rel_path.rsplit('/', 1)[-1] if copy else twin.sha256[:12]}"
    IgnoreRule.objects.create(kind=IgnoreKind.CONTENT, value=f.sha256, note=note)
    return True


def set_aside_all() -> list[str]:
    """Every catalogued 8-bit capture and float light with a raw twin; returns the hashes set aside."""
    out = []
    for f in Frame.objects.filter(status=FrameStatus.CATALOGUED).prefetch_related("headers"):
        if set_aside(f):
            out.append(f.sha256)
    return out
