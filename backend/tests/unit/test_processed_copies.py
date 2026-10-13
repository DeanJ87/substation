"""PixInsight copies (32-bit float, same DATE-OBS and camera as a raw 16-bit light) are set aside, not graded twice."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Frame, FrameStatus, FrameType, HeaderSnapshot, IgnoreRule
from apps.ingest.processed import EIGHT_BIT_NOTE, raw_twin, set_aside_all

pytestmark = pytest.mark.django_db
T = datetime(2026, 3, 7, 19, 39, 52, tzinfo=UTC)


def light(sha: str, fmt: str, when=T, kind=FrameType.LIGHT) -> Frame:
    f = Frame.objects.create(
        sha256=sha.ljust(64, "0"),
        size_bytes=1,
        format="xisf",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=kind,
        camera="ATR2600M",
        date_obs_utc=when,
    )
    HeaderSnapshot.objects.create(frame=f, geometry="6248:4176", sample_format=fmt)
    return f


def test_a_float_copy_of_a_raw_sub_is_set_aside():
    raw, copy = light("a", "BITPIX=16"), light("b", "Float32")
    lone = light("c", "Float32", datetime(2026, 3, 8, 1, tzinfo=UTC))  # no raw twin: a sub in its own right
    assert raw_twin(copy) == raw and raw_twin(raw) is None and raw_twin(lone) is None
    assert set_aside_all() == [copy.sha256]
    assert IgnoreRule.objects.get(value=copy.sha256).note.startswith("Processed copy of")
    assert set_aside_all() == []  # once only


def test_8_bit_captures_of_any_kind_are_set_aside():
    """Owner 2026-10-13: the A7 III's early 8-bit files aren't raw data; exclude every one, flats and darks too."""
    raw = light("d", "BITPIX=16")
    sub = light("e", "BITPIX=8", datetime(2025, 9, 25, 22, tzinfo=UTC))
    flat = light("f", "UInt8", datetime(2025, 10, 21, 5, tzinfo=UTC), kind=FrameType.FLAT)
    assert sorted(set_aside_all()) == sorted([sub.sha256, flat.sha256])
    assert IgnoreRule.objects.get(value=sub.sha256).note == EIGHT_BIT_NOTE
    assert not IgnoreRule.objects.filter(value=raw.sha256).exists()
