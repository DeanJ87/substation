"""G3: the whole on-arrival pipeline with real Siril: catalogue → match → calibrate → measure → grade.
Marked `siril`: scripts/test-in-worker.sh."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalogue.models import Frame, FrameType
from apps.ingest.sweep import sweep_library
from apps.libraries.discovery import discover_libraries
from apps.processing.models import CalibrationMatch, MachineGrade, SubMeasurement
from substation.tasks.models import Task, TaskStatus
from substation.tasks.worker import WorkerProcess
from tests.engine.synthetic import dark_field, flat_field, star_field

pytestmark = [pytest.mark.siril, pytest.mark.django_db(transaction=True)]

COMMON = {
    "INSTRUME": "TESTCAM",
    "TELESCOP": "Test 71",
    "GAIN": 120,
    "OFFSET": 80,
    "XBINNING": 1,
    "YBINNING": 1,
    "XPIXSZ": 3.76,
    "FOCALLEN": 490.0,
    "SITELAT": 55.0,
    "SITELONG": -1.66,
}


def light_header(i: int) -> dict:
    return COMMON | {
        "IMAGETYP": "LIGHT",
        "OBJECT": "Test Nebula",
        "FILTER": "Ha",
        "EXPTIME": 300.0,
        "CCD-TEMP": -20.0,
        "SET-TEMP": -20.0,
        "DATE-OBS": f"2026-09-28T21:{10 + i * 6:02d}:00",
    }


def test_lights_are_calibrated_measured_and_graded(tmp_path, settings_overrides=None):
    settings.PROCESSING_ENABLED = True
    settings.WORK_DIR = tmp_path / "work"
    settings.PREVIEWS_DIR = tmp_path / "previews"
    root = Path(settings.LIBRARY_ROOT) / f"pipe-{tmp_path.name}"
    (root / "LIGHT").mkdir(parents=True)
    (root / "Masters").mkdir()
    for i in range(6):  # 5 good subs and one cloudy one with few stars
        star_field(
            root / "LIGHT" / f"sub_{i}.fits",
            n=40 if i == 5 else 150,
            seed=10 + i,
            field_seed=7,
            shift=(i * 1.5, -i * 0.7),
            header=light_header(i),
        )
    from astropy.io import fits

    dark = dark_field(root / "Masters" / "dark.fits")
    with fits.open(dark, mode="update") as hl:
        hl[0].header.update(COMMON | {"IMAGETYP": "Master Dark", "EXPTIME": 300.0, "SET-TEMP": -20.0})
    flat = flat_field(root / "Masters" / "flat.fits")
    with fits.open(flat, mode="update") as hl:
        hl[0].header.update(
            COMMON
            | {"IMAGETYP": "Master Flat", "EXPTIME": 2.0, "FILTER": "Ha", "DATE-OBS": "2026-09-27T04:00:00"}
        )
    old = time.time() - 3600
    for p in root.rglob("*.fits"):
        os.utime(p, (old, old))
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
    sweep_library(lib)
    WorkerProcess("w-pipe").run(max_tasks=200)
    failed = list(Task.objects.filter(status=TaskStatus.FAILED).values_list("name", "error"))
    assert failed == []
    lights = Frame.objects.filter(frame_type=FrameType.LIGHT)
    assert lights.count() == 6
    assert CalibrationMatch.objects.filter(state="matched").count() == 6
    ms = {m.frame.copies.first().rel_path: m for m in SubMeasurement.objects.select_related("frame")}
    good = ms["LIGHT/sub_0.fits"]
    assert good.state == "done", good.error
    assert 100 < good.stars < 200 and 2.0 < good.fwhm_px < 4.5
    assert good.fwhm_arcsec == pytest.approx(good.fwhm_px * 206.265 * 3.76 / 490, rel=1e-3)
    assert Path(good.calibrated_path).exists() and Path(good.preview_path).exists()
    grades = {g.frame.copies.first().rel_path: g for g in MachineGrade.objects.select_related("frame")}
    assert grades["LIGHT/sub_5.fits"].verdict == "reject"
    assert "Star count" in grades["LIGHT/sub_5.fits"].reason
    assert grades["LIGHT/sub_0.fits"].verdict == "accept"
    assert not grades["LIGHT/sub_0.fits"].provisional
    # Spec 004: integrate the graded subs into Master v1 with the default rule
    from apps.catalogue.models import Dataset
    from apps.processing.masters import preview as stack_preview
    from apps.processing.masters import start as stack_start
    from apps.processing.models import Master

    ds = Dataset.objects.get()
    pv = stack_preview(ds, None, "default")
    assert pv["subs"] == 5 and pv["excluded"] == 1  # the cloudy sub is left out
    Path(good.calibrated_path).unlink()  # pruned from the cache: integration calibrates it again
    m = stack_start(ds, None, "default")
    WorkerProcess("w-stack", heavy_slots=1).run(max_tasks=10)
    m = Master.objects.get(pk=m.pk)
    assert m.state == "current", m.error
    assert Path(m.output_path).exists() and m.report["stars"] > 50
    from astropy.io import fits as _fits

    h = _fits.getheader(m.output_path)  # FR-009: the master carries its provenance
    assert h["CREATOR"] == "SubStation" and h["NCOMBINE"] == m.sub_count and h["SST-MSTR"] == f"v{m.version}"
    assert h["DATE-BEG"] <= h["DATE-END"] and h["TOTEXP"] > 0
    # FR-004: "most stars" pins the reference sub and registers in one pass
    m2 = stack_start(ds, None, "default", options={"reference": "most_stars"})
    WorkerProcess("w-stack2", heavy_slots=1).run(max_tasks=10)
    m2 = Master.objects.get(pk=m2.pk)
    assert m2.state == "current", m2.error
    assert any("most stars" in n for n in m2.report["notes"]), m2.report["notes"]
    assert m.sub_count == 5 and m.version == 1
    every = stack_start(ds, None, "everything")
    WorkerProcess("w-stack2", heavy_slots=1).run(max_tasks=10)
    every.refresh_from_db()
    m.refresh_from_db()
    assert every.state == "current" and every.sub_count == 6 and m.state == "superseded"


def test_seestar_subs_need_no_masters_and_are_debayered(tmp_path):
    """A smart telescope calibrates in the device: its colour subs are only debayered, then measured and graded."""
    settings.PROCESSING_ENABLED = True
    settings.WORK_DIR = tmp_path / "work"
    settings.PREVIEWS_DIR = tmp_path / "previews"
    root = Path(settings.LIBRARY_ROOT) / f"seestar-{tmp_path.name}"
    root.mkdir(parents=True)
    hdr = {
        "CREATOR": "ZWO Seestar S30 Pro",
        "TELESCOP": "S30 Pro_db50a4a4",
        "IMAGETYP": "Light",
        "OBJECT": "M 31",
        "FILTER": "IRCUT",
        "BAYERPAT": "GRBG",
        "GAIN": 200,
        "EXPTIME": 10.0,
        "XPIXSZ": 2.9,
        "FOCALLEN": 160.0,
        "SITELONG": 119.9,
        "SITELAT": -8.5,
    }
    for i in range(5):
        star_field(
            root / f"Light_M 31_10.0s_IRCUT_{i}.fit",
            n=120,
            seed=30 + i,
            field_seed=9,
            shift=(i, -i),
            header=hdr | {"DATE-OBS": f"2026-09-12T16:{30 + i:02d}:00"},
        )
    old = time.time() - 3600
    for p in root.glob("*.fit"):
        os.utime(p, (old, old))
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
    sweep_library(lib)
    WorkerProcess("w-see").run(max_tasks=100)
    assert list(Task.objects.filter(status=TaskStatus.FAILED).values_list("error", flat=True)) == []
    cm = CalibrationMatch.objects.filter(frame__copies__library=lib).first()
    assert cm.state == "matched" and cm.dark is None and cm.dark_note == "Calibrated in the camera"
    ms = SubMeasurement.objects.filter(frame__copies__library=lib)
    from apps.engine import siril as eng_mod

    if any(m.state != "done" for m in ms) and eng_mod._engine is not None:
        print("SIRILOUT\n" + "\n".join(eng_mod._engine._stdout[-40:]))
    assert ms.count() == 5 and all(m.state == "done" and m.stars for m in ms), [
        (m.state, m.error, m.stars) for m in ms
    ]
    assert MachineGrade.objects.filter(frame__copies__library=lib).count() == 5


def test_masters_are_built_from_raw_calibration_frames(tmp_path):
    """Spec 002 US2, US3: raw bias, darks and flats become masters; a truncated flat is rejected by QA; the
    flats are calibrated by the bias; a dust mote is found; and the lights then match the built masters."""
    import numpy as np
    from astropy.io import fits

    from apps.processing.api_calibration import build_missing
    from apps.processing.models import BuiltMaster, CalibrationQA

    settings.PROCESSING_ENABLED = True
    settings.WORK_DIR = tmp_path / "work"
    settings.PREVIEWS_DIR = tmp_path / "previews"
    settings.MASTERS_DIR = tmp_path / "masters"
    root = Path(settings.LIBRARY_ROOT) / f"raw-{tmp_path.name}"
    for d in ("LIGHT", "BIAS", "DARK", "FLAT"):
        (root / d).mkdir(parents=True)
    for i in range(4):
        star_field(
            root / "LIGHT" / f"sub_{i}.fits",
            seed=10 + i,
            field_seed=7,
            shift=(i * 1.5, -i * 0.7),
            header=light_header(i),
        )
    for i in range(5):
        p = dark_field(root / "BIAS" / f"bias_{i}.fits", level=250.0, seed=40 + i)
        with fits.open(p, mode="update") as hl:
            hl[0].header.update(
                COMMON
                | {
                    "IMAGETYP": "BIAS",
                    "EXPTIME": 3.125e-05,
                    "SET-TEMP": -20.0,
                    "DATE-OBS": f"2026-09-27T03:{i:02d}:00",
                }
            )
        p = dark_field(root / "DARK" / f"dark_{i}.fits", seed=50 + i)
        with fits.open(p, mode="update") as hl:
            hl[0].header.update(
                COMMON
                | {
                    "IMAGETYP": "DARK",
                    "EXPTIME": 300.0,
                    "SET-TEMP": -20.0,
                    "CCD-TEMP": -20.0,
                    "DATE-OBS": f"2026-09-29T02:{i * 6:02d}:00",
                }
            )
        p = flat_field(root / "FLAT" / f"flat_{i}.fits", seed=60 + i)
        with fits.open(p, mode="update") as hl:
            data = hl[0].data.astype(np.float32)
            yy, xx = np.indices(data.shape)
            data[(yy - 300) ** 2 + (xx - 200) ** 2 < 15**2] *= 0.95  # a dust mote
            if i == 4:
                data[:200] = 0  # a truncated readout
            hl[0].data = data.astype(np.uint16)
            hl[0].header.update(
                COMMON
                | {
                    "IMAGETYP": "FLAT",
                    "EXPTIME": 2.0,
                    "FILTER": "Ha",
                    "DATE-OBS": f"2026-09-27T04:{i:02d}:00",
                }
            )
        # near-dark "flats": a test exposure at the bias level, filed as a flat
        p = dark_field(root / "FLAT" / f"test_{i}.fits", level=255.0, seed=70 + i)
        with fits.open(p, mode="update") as hl:
            hl[0].header.update(
                COMMON
                | {
                    "IMAGETYP": "FLAT",
                    "EXPTIME": 0.001,
                    "FILTER": "OIII",
                    "DATE-OBS": f"2026-09-27T05:{i:02d}:00",
                }
            )
    old = time.time() - 3600
    for p in root.rglob("*.fits"):
        os.utime(p, (old, old))
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
    sweep_library(lib)
    WorkerProcess("w-raw").run(max_tasks=200)
    assert build_missing(None).queued == 4
    WorkerProcess("w-build", heavy_slots=1).run(max_tasks=50)
    failed = list(Task.objects.filter(status=TaskStatus.FAILED).values_list("name", "error"))
    assert failed == []
    dark_flats = BuiltMaster.objects.get(calibration_set__filter_norm="OIII")
    assert (
        dark_flats.state == "blocked" and "almost dark" in dark_flats.reason and dark_flats.frame is None
    ), (dark_flats.method, dark_flats.report.get("stats"), dark_flats.reason)
    built = {
        b.calibration_set.type: b
        for b in BuiltMaster.objects.select_related("calibration_set").exclude(
            calibration_set__filter_norm="OIII"
        )
    }
    assert {t: b.state for t, b in built.items()} == {"bias": "done", "dark": "done", "flat": "done"}, {
        t: (b.reason, b.error, b.frames_excluded) for t, b in built.items()
    }
    flat = built["flat"]
    assert flat.frames_used == 4 and len(flat.frames_excluded) == 1
    assert "Truncated" in flat.frames_excluded[0]["reason"]
    assert flat.calibrated_with is not None and flat.calibrated_with.frame_type == FrameType.MASTER_BIAS
    motes = flat.report["dust_motes"]
    assert any(abs(m["x"] - 200) < 12 and abs(m["y"] - 300) < 12 for m in motes), motes
    assert (
        flat.frame.frame_type == FrameType.MASTER_FLAT
        and built["dark"].frame.frame_type == FrameType.MASTER_DARK
    )
    assert CalibrationQA.objects.filter(verdict="reject").count() == 1
    WorkerProcess("w-after").run(max_tasks=200)
    m = CalibrationMatch.objects.filter(frame__frame_type=FrameType.LIGHT)
    assert m.count() == 4 and all(x.state == "matched" for x in m)
    assert {x.flat_id for x in m} == {flat.frame_id}
    # FR-007: rebuilding the flats compares the new master with the one it replaces
    from apps.processing.calibration import request_build

    again = request_build(flat.calibration_set)
    WorkerProcess("w-rebuild", heavy_slots=1).run(max_tasks=20)
    again.refresh_from_db()
    assert again.state == "done", again.error
    cmp = again.report["comparison"]
    assert cmp["against"] == flat.frame_id and cmp["kind"] == "ratio" and abs(cmp["level_change"]) < 0.01
    flat.frame.refresh_from_db()  # identical inputs give a byte-identical master: the same frame, still in use
    assert flat.frame.status == ("catalogued" if again.frame_id == flat.frame_id else "ignored")
