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
