"""T046: files appearing in a library are catalogued; partial files wait; AppleDouble and .DS_Store are
skipped (spec 001 US1)."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalogue.models import Copy, Dataset, DatasetNight, Frame, FrameType
from apps.ingest.sweep import sweep_library
from apps.libraries.discovery import discover_libraries
from substation.tasks.models import Task, TaskStatus
from substation.tasks.worker import WorkerProcess

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "headers"
LIGHTS_0928 = FIX / "capture/2026-09-28/LIGHT"
LIGHTS_1007 = FIX / "capture/2026-10-07/LIGHT"

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def library(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"capture-{tmp_path.name}"
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def copy_old(src: Path, dst: Path) -> None:
    """Copy as an already-finished file (mtime in the past, so no stability wait)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    old = time.time() - 3600
    os.utime(dst, (old, old))


def ingest(lib_root: Path) -> None:
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == lib_root)
    sweep_library(lib)
    WorkerProcess("w-test").run(max_tasks=200)


def test_lights_are_catalogued_with_header_values(library):
    for f in ("2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf",):
        copy_old(LIGHTS_0928 / f, library / "2026-09-28/LIGHT" / f)
    ingest(library)
    frame = Frame.objects.get()
    assert frame.frame_type == FrameType.LIGHT
    assert (frame.target, frame.panel, frame.filter_norm, frame.filter_raw) == ("NGC 7000", 2, "Hα", "Halpha")
    assert frame.exptime_s == 600.0 and frame.gain == 120 and frame.offset == 80
    assert frame.ccd_temp_c == -20.0 and frame.camera == "ATR2600M" and frame.telescope == "Askar 71F"
    assert frame.night.date.isoformat() == "2026-09-28"
    ds = Dataset.objects.get()
    assert ds.display_name == "NGC 7000 · Panel 2 · Hα"
    assert ds.sub_count == 1 and ds.integration_s == 600.0
    assert DatasetNight.objects.get().sub_count == 1
    assert frame.metadata.filter(field="filter", is_winner=True, source="header").exists()
    assert frame.headers.get().keywords["OBJECT"]["value"] == "NGC 7000 Panel 2"


def test_after_midnight_lights_share_the_night(library):
    for f in (
        "2026-10-07_20-27-58_OIII_-20.00_600.00s_0000.xisf",
        "2026-10-08_00-03-30_OIII_-20.00_600.00s_0011.xisf",
    ):
        copy_old(LIGHTS_1007 / f, library / f)
    ingest(library)
    assert {f.night.date.isoformat() for f in Frame.objects.all()} == {"2026-10-07"}


def test_appledouble_and_dsstore_are_ignored(library):
    copy_old(LIGHTS_0928 / "._2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf", library / "._a.xisf")
    (library / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    (library / "notes.txt").write_text("not an image")
    copy_old(LIGHTS_0928 / "2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf", library / "keep.xisf")
    ingest(library)
    assert [c.rel_path for c in Copy.objects.all()] == ["keep.xisf"]
    assert not Task.objects.filter(status=TaskStatus.FAILED).exists()


def test_partial_file_waits_until_complete(library):
    src = (LIGHTS_0928 / "2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf").read_bytes()
    target = library / "growing.xisf"
    target.write_bytes(src[: len(src) // 2])  # half written, modified just now
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == library)
    sweep_library(lib)
    WorkerProcess("w-test").run(max_tasks=5)
    assert not Frame.objects.exists()  # never catalogued half a file
    task = Task.objects.get(name__endswith="hash_file")
    assert task.status == TaskStatus.READY and "being written" in task.progress_note
    target.write_bytes(src)  # writer finishes
    old = time.time() - 60
    os.utime(target, (old, old))
    Task.objects.filter(pk=task.pk).update(run_after=task.enqueued_at)  # due now
    WorkerProcess("w-test").run(max_tasks=10)
    assert Frame.objects.count() == 1


def test_rescan_of_unchanged_files_enqueues_nothing(library):
    copy_old(LIGHTS_0928 / "2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf", library / "a.xisf")
    ingest(library)
    before = Task.objects.count()
    ingest(library)
    assert Task.objects.count() == before


def test_unparseable_file_is_catalogued_as_error(library):
    bad = library / "broken.xisf"
    bad.write_bytes(b"XISF0100 this is not a real header")
    old = time.time() - 3600
    os.utime(bad, (old, old))
    ingest(library)
    f = Frame.objects.get()
    assert f.status == "error" and "XISF" in f.error


def test_same_path_with_new_content_leaves_no_ghost_sub(library):
    """A sub first hashed while half-written, then complete: one sub in the dataset, the partial marked
    missing with a `replaced` event."""
    from apps.catalogue.models import CopyEvent, CopyEventKind, FrameStatus

    name = "2026-10-07_20-27-58_OIII_-20.00_600.00s_0000.xisf"
    dst = library / name
    copy_old(LIGHTS_1007 / name, dst)
    with dst.open("ab") as f:
        f.write(b"\0" * 1000)  # the "partial" version differs in content
    old = time.time() - 3600
    os.utime(dst, (old, old))
    ingest(library)
    partial = Frame.objects.get()
    copy_old(LIGHTS_1007 / name, dst)
    os.utime(dst, (old + 60, old + 60))
    ingest(library)
    assert Frame.objects.count() == 2
    partial.refresh_from_db()
    assert partial.status == FrameStatus.MISSING
    assert CopyEvent.objects.filter(frame=partial, kind=CopyEventKind.REPLACED).exists()
    assert Dataset.objects.get().sub_count == 1


def test_truncated_old_file_is_catalogued_as_an_error(library, settings):
    settings.INGEST_VERIFY_COMPLETE = True  # the fixture is header-only, so it reads as truncated
    name = "2026-10-07_20-27-58_OIII_-20.00_600.00s_0000.xisf"
    copy_old(LIGHTS_1007 / name, library / name)
    ingest(library)
    frame = Frame.objects.get()
    assert frame.status == "error" and "truncated" in frame.error
    assert not Dataset.objects.filter(sub_count__gt=0).exists()
