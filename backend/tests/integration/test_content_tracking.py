"""T060, T061: files are known by content wherever they go (spec 001 US2)."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalogue.models import (
    Copy,
    CopyEvent,
    CopyEventKind,
    Dataset,
    DatasetState,
    Frame,
    FrameStatus,
    ReconciliationItem,
    ReconciliationKind,
    UserVerdict,
    Verdict,
    VerdictSource,
)
from apps.ingest.sweep import sweep_library
from apps.libraries.discovery import discover_libraries
from substation.tasks.models import Task
from substation.tasks.worker import WorkerProcess

FIX = Path(__file__).resolve().parents[1] / "fixtures/headers/capture"
L0928 = FIX / "2026-09-28/LIGHT"
L1007 = FIX / "2026-10-07/LIGHT"
TWIN = "2026-09-28_20-50-41_Halpha_-20.00_600.00s_0031.xisf"
TWINLESS = "BAD_2026-09-29_01-29-50_Halpha_-19.90_600.00s_0031.xisf"
SUB = "2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf"

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def library(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"lib-{tmp_path.name}"
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def put(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    old = time.time() - 3600
    os.utime(dst, (old, old))


def ingest(root: Path) -> None:
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
    sweep_library(lib)
    WorkerProcess("w-test").run(max_tasks=200)


def test_bad_twin_folds_into_one_rejected_frame(library):
    put(L0928 / TWIN, library / TWIN)
    put(L0928 / f"BAD_{TWIN}", library / f"BAD_{TWIN}")
    put(L0928 / SUB, library / SUB)
    ingest(library)
    frame = Frame.objects.get(copies__rel_path=TWIN)
    assert frame.copies.count() == 2
    v = UserVerdict.objects.get(frame=frame)
    assert (v.verdict, v.source) == (Verdict.REJECT, VerdictSource.NINA_BAD_PREFIX)
    ds = Dataset.objects.get()
    assert (ds.sub_count, ds.user_rejected_count) == (2, 1)
    assert not ReconciliationItem.objects.filter(status="open").exists()
    ingest(library)  # idempotent
    assert UserVerdict.objects.count() == 1


def test_twinless_bad_is_rejected_with_an_informational_item(library):
    put(L0928 / TWINLESS, library / TWINLESS)
    ingest(library)
    frame = Frame.objects.get()
    assert frame.verdicts.get().verdict == Verdict.REJECT
    item = ReconciliationItem.objects.get()
    assert item.kind == ReconciliationKind.BAD_WITHOUT_TWIN
    assert Dataset.objects.get().state == DatasetState.OK  # informational only


def test_plain_duplicate_is_one_frame_two_copies(library):
    put(L0928 / SUB, library / "a" / SUB)
    put(L0928 / SUB, library / "b" / SUB)
    ingest(library)
    assert Frame.objects.count() == 1 and Copy.objects.count() == 2
    assert CopyEvent.objects.filter(kind=CopyEventKind.COPIED).count() == 1


def test_move_and_rename_update_copies_without_hashing(library):
    put(L0928 / SUB, library / "night1" / SUB)
    put(L0928 / TWIN, library / "night1" / TWIN)
    ingest(library)
    hashes = Task.objects.filter(name__endswith="hash_file").count()
    os.rename(library / "night1", library / "moved")
    os.rename(library / "moved" / TWIN, library / "moved" / f"BAD_{TWIN}")  # NINA thumbs-down
    ingest(library)
    assert Task.objects.filter(name__endswith="hash_file").count() == hashes  # nothing re-hashed
    assert Frame.objects.count() == 2
    assert set(Copy.objects.values_list("rel_path", flat=True)) == {f"moved/{SUB}", f"moved/BAD_{TWIN}"}
    assert CopyEvent.objects.filter(kind__in=[CopyEventKind.MOVED, CopyEventKind.RENAMED]).count() == 2
    assert Frame.objects.get(copies__rel_path=f"moved/BAD_{TWIN}").verdicts.get().verdict == Verdict.REJECT
    assert not ReconciliationItem.objects.exclude(kind=ReconciliationKind.BAD_WITHOUT_TWIN).exists()
    assert Dataset.objects.get().user_rejected_count == 1


def test_deleted_frame_is_missing_after_one_more_sweep_and_comes_back(library):
    put(L0928 / SUB, library / SUB)
    put(L0928 / TWIN, library / TWIN)
    ingest(library)
    gone = Frame.objects.get(copies__rel_path=SUB)
    (library / SUB).unlink()
    ingest(library)
    gone.refresh_from_db()
    assert gone.status == FrameStatus.CATALOGUED  # copy missing, frame not yet
    assert not Copy.objects.get(frame=gone).present
    ingest(library)
    gone.refresh_from_db()
    assert gone.status == FrameStatus.MISSING
    assert ReconciliationItem.objects.get(kind=ReconciliationKind.FRAME_MISSING, status="open").frame == gone
    ds = Dataset.objects.get()
    assert ds.state == DatasetState.NEEDS_RECONCILIATION
    assert ds.state_reason == "1 file is missing from disk. Review before stacking."
    assert ds.sub_count == 1

    put(L0928 / SUB, library / SUB)
    ingest(library)
    gone.refresh_from_db()
    assert gone.status == FrameStatus.CATALOGUED
    assert not ReconciliationItem.objects.filter(status="open").exists()
    ds.refresh_from_db()
    assert (ds.state, ds.sub_count) == (DatasetState.OK, 2)
    assert CopyEvent.objects.filter(kind=CopyEventKind.REAPPEARED).exists()


def test_same_path_new_content_is_a_new_frame(library):
    put(L0928 / SUB, library / "x.xisf")
    ingest(library)
    first = Frame.objects.get()
    put(L1007 / "2026-10-07_20-27-58_OIII_-20.00_600.00s_0000.xisf", library / "x.xisf")
    os.utime(library / "x.xisf", (time.time() - 1800, time.time() - 1800))
    ingest(library)
    assert Frame.objects.count() == 2
    assert CopyEvent.objects.filter(kind=CopyEventKind.REPLACED, frame=first).exists()
    assert not first.copies.exists()


def test_unreachable_library_marks_nothing_missing(library):
    put(L0928 / SUB, library / SUB)
    ingest(library)
    (library / SUB).unlink()  # the library is now empty: it looks like an unmounted share
    ingest(library)
    ingest(library)
    assert Copy.objects.get().present
    assert Frame.objects.get().status == FrameStatus.CATALOGUED


def test_rescan_of_unchanged_library_queues_nothing(library):
    """T061"""
    for name in (SUB, TWIN):
        put(L0928 / name, library / name)
    ingest(library)
    before = Task.objects.count()
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == library)
    result = sweep_library(lib)
    assert result.unchanged == 2 and result.queued == 0
    assert Task.objects.count() == before


def test_move_found_by_hashing_before_the_old_path_is_missed(library):
    """Filesystems that renumber inodes on rename: the new path is hashed and logged as a copy before the
    sweep notices the old path has gone. The sweep then turns it into a move and drops the stale copy."""
    from apps.catalogue.services.tracking import mark_copies_missing

    put(L0928 / SUB, library / "a" / SUB)
    ingest(library)
    old = Copy.objects.get()
    put(L0928 / SUB, library / "b" / SUB)  # new inode, as if renumbered
    (library / "a" / SUB).unlink()
    from apps.ingest.tasks.hash import hash_file

    lib = old.library
    hash_file.call(lib.pk, f"b/{SUB}", time.time())
    assert CopyEvent.objects.filter(kind=CopyEventKind.COPIED).exists()
    mark_copies_missing([Copy.objects.get(pk=old.pk)])
    assert list(Copy.objects.values_list("rel_path", flat=True)) == [f"b/{SUB}"]
    ev = CopyEvent.objects.get(kind=CopyEventKind.MOVED)
    assert ev.details == {"from": f"{lib.name}/a/{SUB}", "to": f"b/{SUB}"}
    assert not CopyEvent.objects.filter(kind__in=[CopyEventKind.COPIED, CopyEventKind.MISSING]).exists()


def test_a_new_device_number_alone_is_not_a_change(library):
    """A remount or container restart (Docker Desktop) changes st_dev; that must not re-read every file."""
    put(L0928 / SUB, library / SUB)
    ingest(library)
    Copy.objects.update(st_dev=999999)
    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == library)
    assert sweep_library(lib).unchanged == 1
