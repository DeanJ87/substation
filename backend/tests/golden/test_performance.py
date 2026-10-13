"""T104: performance targets (marked slow; run with `uv run pytest -m slow`).

SC-001: a sub is catalogued within 10 s of its file being complete (watcher + workers running).
SC-005: a 400-file drop is processed within 15 minutes, with live subs still within 10 s.
SC-006: a rescan of an unchanged 10,000-frame library queues nothing and takes under 2 minutes.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalogue.models import Copy, Frame, FrameStatus
from apps.ingest.sweep import sweep_library
from apps.ingest.watcher import Watcher
from apps.libraries.discovery import discover_libraries
from apps.libraries.models import Library
from substation.tasks.models import Task, TaskStatus
from substation.tasks.worker import WorkerProcess

FIX = Path(__file__).resolve().parents[1] / "fixtures/headers/capture"
LIGHT = FIX / "2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf"
OTHER = FIX / "2026-10-07/LIGHT/2026-10-07_20-27-58_OIII_-20.00_600.00s_0000.xisf"

pytestmark = [pytest.mark.slow, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def root(tmp_path):
    r = Path(settings.LIBRARY_ROOT) / f"perf-{tmp_path.name}"
    r.mkdir(parents=True)
    yield r
    shutil.rmtree(r, ignore_errors=True)


def library_for(root: Path) -> Library:
    return next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)


def test_sc006_unchanged_rescan_of_10000_frames(root):
    lib = library_for(root)
    now = datetime.now(UTC)
    frames, copies = [], []
    for i in range(10_000):
        p = root / f"night{i // 500:02}" / f"sub_{i:05}.fits"
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(b"x")
        st = p.stat()
        sha = f"{i:064x}"
        frames.append(
            Frame(sha256=sha, size_bytes=1, format="fits", first_seen_at=now, status=FrameStatus.CATALOGUED)
        )
        copies.append(
            Copy(
                frame_id=sha,
                library=lib,
                rel_path=str(p.relative_to(root)),
                st_dev=st.st_dev,
                st_ino=st.st_ino,
                st_size=st.st_size,
                st_mtime_ns=st.st_mtime_ns,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    Frame.objects.bulk_create(frames, batch_size=2000)
    Copy.objects.bulk_create(copies, batch_size=2000)
    t = time.monotonic()
    result = sweep_library(lib)
    took = time.monotonic() - t
    assert (result.files, result.unchanged, result.queued, result.missing) == (10_000, 10_000, 0, 0)
    assert not Task.objects.exists()
    assert took < 120, f"rescan took {took:.1f} s"
    print(f"SC-006: 10,000-frame unchanged rescan in {took:.1f} s")


def test_sc005_400_file_drop_with_live_subs(root):
    old = time.time() - 3 * 24 * 3600
    for i in range(400):
        dst = root / "holiday" / f"sub_{i:03}.xisf"
        dst.parent.mkdir(exist_ok=True)
        shutil.copyfile(LIGHT, dst)
        os.utime(dst, (old, old))
    lib = library_for(root)
    t0 = time.monotonic()
    sweep_library(lib)
    workers = [WorkerProcess(f"p{i}") for i in range(4)]
    threads = [threading.Thread(target=w.run) for w in workers]
    for th in threads:
        th.start()
    time.sleep(0.5)
    live = root / "live" / OTHER.name
    live.parent.mkdir()
    shutil.copyfile(OTHER, live)
    os.utime(live, (time.time() - 5, time.time() - 5))  # just finished writing
    t_live = time.monotonic()
    sweep_library(lib)  # what the watcher does on an event
    live_done = None
    while time.monotonic() - t0 < 900:
        if (
            live_done is None
            and Frame.objects.filter(copies__rel_path__startswith="live/", status="catalogued").exists()
        ):
            live_done = time.monotonic() - t_live
        if not Task.objects.exclude(status__in=[TaskStatus.SUCCEEDED, TaskStatus.FAILED]).exists():
            break
        time.sleep(0.2)
    bulk = time.monotonic() - t0
    for w in workers:
        w.stopping.set()
    for th in threads:
        th.join(timeout=10)
    assert Copy.objects.filter(rel_path__startswith="holiday/").count() == 400
    assert live_done is not None and live_done < 10, f"live sub took {live_done}"
    assert bulk < 900
    print(f"SC-005: 400 files in {bulk:.1f} s; live sub catalogued {live_done:.1f} s after it landed")


def test_sc001_live_sub_with_watcher(root):
    stop = threading.Event()
    watcher = threading.Thread(target=Watcher(stop).run, daemon=True)
    worker = WorkerProcess("live")
    wt = threading.Thread(target=worker.run, daemon=True)
    watcher.start()
    wt.start()
    time.sleep(2)  # watcher takes the lease and sweeps
    dst = root / LIGHT.name
    tmp = root / ".partial"
    shutil.copyfile(LIGHT, tmp)
    os.rename(tmp, dst)  # complete file appears at once, as NINA's final rename does
    t = time.monotonic()
    took = None
    while time.monotonic() - t < 30:
        if Frame.objects.filter(status="catalogued").exists():
            took = time.monotonic() - t
            break
        time.sleep(0.1)
    stop.set()
    worker.stopping.set()
    watcher.join(timeout=10)
    wt.join(timeout=10)
    assert took is not None and took < 10, f"took {took}"
    print(f"SC-001: catalogued {took:.1f} s after the file appeared")
