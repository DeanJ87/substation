"""Owner 2026-10-11: WBPP's calibrated (_c) and registered (_r) copies are not raw subs."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Frame, FrameStatus, FrameType, HeaderSnapshot
from apps.ingest.resolve import _already_processed

pytestmark = pytest.mark.django_db


def _light(sha: str, **header) -> Frame:
    f = Frame.objects.create(
        sha256=sha.ljust(64, "0"),
        size_bytes=1,
        format="xisf",
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
        first_seen_at=datetime(2026, 9, 25, tzinfo=UTC),
    )
    HeaderSnapshot.objects.create(frame=f, **header)
    return f


def test_a_pixinsight_calibrated_copy_is_processed_not_a_light():
    f = _light("a", properties={"PCL:Signature:Calibration": {"value": "x"}}, keywords={"IMAGETYP": "Light"})
    _already_processed(f)
    assert f.frame_type == FrameType.PROCESSED and "Calibration" in f.classification_reason


def test_fits_history_marks_a_registered_frame():
    f = _light("b", keywords={"HISTORY": "StarAlignment.referenceImage: ref.xisf"})
    _already_processed(f)
    assert f.frame_type == FrameType.PROCESSED


def test_a_raw_sub_stays_a_light():
    f = _light(
        "c", properties={"Instrument:Camera:Name": {"value": "ATR2600M"}}, keywords={"IMAGETYP": "Light"}
    )
    _already_processed(f)
    assert f.frame_type == FrameType.LIGHT


def test_a_seestar_running_stack_is_a_master_light_not_a_sub():
    """IC 4605, 2026-10-14: Stacked_153_….fit (STACKCNT 153) was graded and stacked as a sub."""
    from apps.ingest.resolve import _already_stacked

    stacked = _light("d", keywords={"IMAGETYP": {"value": "Light"}, "STACKCNT": {"value": 153}})
    _already_stacked(stacked)
    assert stacked.frame_type == FrameType.MASTER_LIGHT and "153 subs" in stacked.classification_reason
    one = _light("e", keywords={"IMAGETYP": {"value": "Light"}, "STACKCNT": {"value": 1}})
    _already_stacked(one)
    assert one.frame_type == FrameType.LIGHT
