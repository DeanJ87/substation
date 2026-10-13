"""T069: resolution precedence (user > preferred pattern > header > pattern > inferred > settings) and
conflict recording."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import (
    ContentCorrection,
    Copy,
    Frame,
    HeaderConflict,
    MetadataSource,
    MetadataValue,
    PathPattern,
    ReconciliationItem,
)
from apps.ingest.resolve import resolve_frame
from apps.libraries.models import Library

pytestmark = pytest.mark.django_db


@pytest.fixture
def frame(tmp_path):
    lib = Library.objects.create(name="cap", mount_path=str(tmp_path))
    f = Frame.objects.create(
        sha256="a" * 64, size_bytes=1, format="xisf", first_seen_at=datetime.now(UTC), status="catalogued"
    )
    Copy.objects.create(
        frame=f,
        library=lib,
        rel_path="NGC 7000/LIGHT/2026-09-28_20-05-02_Ha_-20.00_600.00s_0001.xisf",
        st_dev=1,
        st_ino=1,
        st_size=1,
        st_mtime_ns=1,
        first_seen_at=f.first_seen_at,
        last_seen_at=f.first_seen_at,
    )
    for field, value, kw in [
        ("object", "M 31", "OBJECT"),
        ("filter", "OIII", "FILTER"),
        ("exptime", "300.0", "EXPTIME"),
        ("frame_type", "LIGHT", "IMAGETYP"),
        ("date_obs", "2026-09-28T19:05:02+00:00", "DATE-OBS"),
        ("site_lon", "-1.66", "SITELONG"),
        ("site_lat", "55.0", "SITELAT"),
    ]:
        MetadataValue.objects.create(
            frame=f, field=field, value=value, raw=value, source=MetadataSource.HEADER, source_detail=kw
        )
    return f


def winner(f: Frame, field: str) -> MetadataValue:
    return f.metadata.get(field=field, is_winner=True)


def test_header_wins_over_ordinary_pattern_and_conflict_is_recorded(frame):
    PathPattern.objects.create(kind="filename", pattern="{date}_{time}_{filter}_{temp}_{exposure}s_{seq}")
    resolve_frame(frame)
    assert winner(frame, "filter").source == MetadataSource.HEADER and frame.filter_norm == "OIII"
    assert winner(frame, "ccd_temp").source == MetadataSource.FILENAME_PATTERN  # only the pattern has it
    assert frame.ccd_temp_c == -20.0
    c = HeaderConflict.objects.get(frame=frame, field="filter")
    assert set(c.values.values()) == {"OIII", "Ha"}
    assert HeaderConflict.objects.filter(frame=frame, field="exptime").exists()  # 300 vs 600


def test_preferred_pattern_beats_header(frame):
    p = PathPattern.objects.create(kind="folder", pattern="{target}/{type}/", prefer_over_header=["target"])
    resolve_frame(frame)
    assert winner(frame, "target").source_detail == f"pattern #{p.pk}"
    assert frame.target == "NGC 7000"
    assert winner(frame, "frame_type").source == MetadataSource.HEADER  # not preferred for type


def test_user_value_beats_everything(frame):
    PathPattern.objects.create(
        kind="filename",
        pattern="{date}_{time}_{filter}_{temp}_{exposure}s_{seq}",
        prefer_over_header=["filter"],
    )
    ContentCorrection.objects.create(sha256=frame.sha256, field="filter", value="SII")
    resolve_frame(frame)
    assert winner(frame, "filter").source == MetadataSource.USER and frame.filter_norm == "SII"


def test_more_specific_pattern_first(frame):
    PathPattern.objects.create(
        kind="folder", pattern="{target}/{type}/", priority=5, prefer_over_header=["target"]
    )
    specific = PathPattern.objects.create(
        kind="folder",
        pattern="{*}/{type}/",
        scope_glob="NGC 7000/**",
        library=Library.objects.get(),
        prefer_over_header=["frame_type"],
    )
    resolve_frame(frame)
    assert winner(frame, "frame_type").source_detail == f"pattern #{specific.pk}"


def test_missing_required_fields_open_items_and_close_when_resolved(frame):
    frame.metadata.filter(field__in=["filter", "exptime"]).delete()
    resolve_frame(frame)
    items = ReconciliationItem.objects.filter(frame=frame, kind="missing_field", status="open")
    assert set(items.values_list("field", flat=True)) == {"filter", "exptime"}
    assert frame.dataset is None  # no filter, no dataset
    PathPattern.objects.create(kind="filename", pattern="{date}_{time}_{filter}_{temp}_{exposure}s_{seq}")
    resolve_frame(frame)
    assert not ReconciliationItem.objects.filter(frame=frame, status="open").exists()
    assert frame.exptime_s == 600.0 and frame.dataset is not None


def test_rig_merge_maps_the_exact_camera_and_telescope_pair(frame):
    """Merging ToupTek ATR2600M on "Askar 71F 490@F\\6.9" into ATR2600M on "Askar 71F" leaves the same telescope name
    used with another camera (an A7 III) alone (spec 006 FR-001)."""
    from apps.libraries.models import InstallationSettings

    for field, value in [("camera", "ToupTek ATR2600M"), ("telescope", "Askar 71F 490@F\\6.9")]:
        MetadataValue.objects.create(
            frame=frame,
            field=field,
            value=value,
            raw=value,
            source=MetadataSource.HEADER,
            source_detail=field.upper(),
        )
    s = InstallationSettings.load()
    s.processing = {
        "equipment": {
            "rig": {
                "ToupTek ATR2600M|Askar 71F 490@F\\6.9": ["ATR2600M", "Askar 71F"],
                "Sony A7 III|TTArtisan Schmega": ["Sony A7 III", "TTArtisan ED"],
            }
        }
    }
    s.save()
    resolve_frame(frame)
    assert (frame.camera, frame.telescope) == ("ATR2600M", "Askar 71F")
    MetadataValue.objects.filter(frame=frame, field="camera").update(value="Sony A7 III", raw="Sony A7 III")
    resolve_frame(frame)
    assert (frame.camera, frame.telescope) == ("Sony A7 III", "Askar 71F 490@F\\6.9")
