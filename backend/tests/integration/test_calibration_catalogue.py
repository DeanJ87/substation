"""T092: calibration frames and masters (spec 001 US6)."""

from __future__ import annotations

import os
import shutil
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalogue.models import CalibrationSet, Frame, FrameStatus, FrameType, ReconciliationItem
from apps.catalogue.services.calibration_sets import assign_calibration_set, recount
from apps.ingest.sweep import sweep_library
from apps.libraries.discovery import discover_libraries
from substation.tasks.worker import WorkerProcess

FIX = Path(__file__).resolve().parents[1] / "fixtures/headers"
DARKS = FIX / "capture/2026-09-28/DARK"
FLATS = FIX / "capture/2026-09-28/FLAT"
LIGHT = FIX / "capture/2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf"
MASTER_DARK = FIX / "masters/Darks/-20c/MasterDark_ATR2600M_-20c_600s.xisf"

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def library(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"cal-{tmp_path.name}"
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def put(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    old = time.time() - 3600
    os.utime(dst, (old, old))


def run(root: Path) -> None:
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
    sweep_library(lib)
    WorkerProcess("w-test").run(max_tasks=200)


def test_flatwizard_darks_are_dark_flats_and_sets_form(library):
    for f in DARKS.glob("2026*.xisf"):
        put(f, library / "DARK" / f.name)
    for f in FLATS.glob("2026*.xisf"):
        put(f, library / "FLAT" / f.name)
    run(library)
    darks = Frame.objects.filter(copies__rel_path__startswith="DARK/")
    assert {d.frame_type for d in darks} == {FrameType.DARK_FLAT}
    assert all("FlatWizard" in d.classification_reason for d in darks)
    sets = {cs.type: cs for cs in CalibrationSet.objects.all()}
    assert sets[FrameType.DARK_FLAT].frame_count == 2
    assert sets[FrameType.DARK_FLAT].filter_blocks == {"Hα": 2}
    flat = sets[FrameType.FLAT]
    assert (flat.frame_count, flat.filter_norm, flat.exptime_s, flat.gain, flat.night.date.isoformat()) == (
        1,
        "Hα",
        2.0,
        120,
        "2026-09-28",
    )


def test_wbpp_master_uses_its_integration_image_and_asks_for_missing_values(library, admin_client):
    put(MASTER_DARK, library / "Masters/ATR2600M/Darks/-20c" / MASTER_DARK.name)
    run(library)
    put(LIGHT, library / "LIGHT" / LIGHT.name)  # a light with gain 120, catalogued after the master
    run(library)
    m = Frame.objects.get(copies__rel_path__startswith="Masters/")
    assert m.frame_type == FrameType.MASTER_DARK and m.integration_index == 0 and m.image_count == 3
    items = {i["field"]: i for i in admin_client.get("/api/v1/reconciliation?kind=master_metadata").json()}
    assert set(items) == {"gain", "offset", "set_temp"}
    assert items["set_temp"]["suggestion"]["value"] == "-20"  # from the -20c folder
    assert items["gain"]["suggestion"]["value"] == "120"  # from this camera's lights, filled in when listed
    assert m.calibration_set is None  # masters aren't raw sets


def test_multi_image_xisf_without_integration_is_ambiguous(library):
    data = bytearray(MASTER_DARK.read_bytes())
    i = data.find(b'id="integration"')
    assert i > 0
    data[i : i + 16] = b'id="integratiOn"'  # same length; no image is called integration now
    dst = library / "odd.xisf"
    dst.write_bytes(bytes(data))
    old = time.time() - 3600
    os.utime(dst, (old, old))
    run(library)
    item = ReconciliationItem.objects.get(kind="ambiguous_master")
    assert "none is named 'integration'" in item.reason


def make(sha: str, when: datetime, **kw) -> Frame:
    fields = {
        "status": FrameStatus.CATALOGUED,
        "frame_type": FrameType.FLAT,
        "filter_norm": "OIII",
        "exptime_s": 2.0,
        "gain": 120,
        "offset": 80,
        "xbin": 1,
        "ybin": 1,
        "camera": "ATR2600M",
        **kw,
    }
    f = Frame.objects.create(
        sha256=sha.ljust(64, "0"),
        size_bytes=1,
        format="xisf",
        first_seen_at=when,
        date_obs_utc=when,
        **fields,
    )
    old, new = assign_calibration_set(f)
    f.save()
    for cs in {c for c in (old, new) if c is not None}:
        recount(cs)
    return f


def test_sessions_split_at_two_hours_and_merge_when_bridged():
    t0 = datetime(2026, 9, 29, 3, 0, tzinfo=UTC)
    make("a", t0)
    make("b", t0 + timedelta(hours=1))
    make("c", t0 + timedelta(hours=5))
    assert CalibrationSet.objects.count() == 2
    make("d", t0 + timedelta(hours=3))  # within 2 h of both sessions: one session now
    assert CalibrationSet.objects.count() == 1
    cs = CalibrationSet.objects.get()
    assert cs.frame_count == 4 and cs.session_end_utc - cs.session_start_utc == timedelta(hours=5)
    make("e", t0 + timedelta(hours=1), filter_norm="SII")  # another filter: another set
    assert CalibrationSet.objects.count() == 2


def test_calibration_api(library, admin_client):
    for f in DARKS.glob("2026*.xisf"):
        put(f, library / "DARK" / f.name)
    put(MASTER_DARK, library / "Masters/-20c" / MASTER_DARK.name)
    run(library)
    sets = admin_client.get("/api/v1/calibration-sets").json()
    assert [(s["type"], s["frame_count"], s["exptime_s"]) for s in sets] == [("dark_flat", 2, 2.0)]
    assert admin_client.get("/api/v1/calibration-sets?type=flat").json() == []
    assert len(admin_client.get("/api/v1/calibration-sets?night=2026-09-28").json()) == 1
    masters = admin_client.get("/api/v1/masters").json()
    assert len(masters) == 1
    assert masters[0]["missing"] == ["gain", "offset", "temperature"]
    assert masters[0]["sources"]["exptime"] == "header EXPTIME"


def test_master_metadata_resolved_from_the_list(library, admin_client):
    put(MASTER_DARK, library / "Masters/-20c" / MASTER_DARK.name)
    run(library)
    items = {i["field"]: i for i in admin_client.get("/api/v1/reconciliation?kind=master_metadata").json()}
    r = admin_client.post(
        f"/api/v1/reconciliation/{items['set_temp']['id']}/resolve",
        {"accept_suggestion": True},
        content_type="application/json",
    )
    assert r.status_code == 200
    m = Frame.objects.get()
    assert m.set_temp_c == -20.0
    left = {i["field"] for i in admin_client.get("/api/v1/reconciliation?kind=master_metadata").json()}
    assert left == {"gain", "offset"}


def test_darks_saved_as_lights_are_darks_by_folder_and_name(library):
    """Owner 2026-10-11: a capture program left on Light while shooting darks. The folder (Darks) and the file
    name (Dark_…) agree, so they win over IMAGETYP; a light merely sitting in a Darks folder stays a light."""
    put(LIGHT, library / "_CalibrationFrames" / "A7III" / "Darks" / "180s" / "Dark_180s_20240528155033.xisf")
    other = next(f for f in LIGHT.parent.glob("*.xisf") if f != LIGHT)
    put(other, library / "Darks" / "M31_0001.xisf")
    run(library)
    dark = Frame.objects.get(copies__rel_path__endswith="Dark_180s_20240528155033.xisf")
    assert dark.frame_type == FrameType.DARK, (
        dark.classification_source,
        dark.classification_reason,
        list(dark.copies.values_list("rel_path", flat=True)),
    )
    assert "folder and file name say dark" in dark.classification_reason
    assert not ReconciliationItem.objects.filter(frame=dark, status="open", field="target").exists()
    assert Frame.objects.get(copies__rel_path="Darks/M31_0001.xisf").frame_type == FrameType.LIGHT
