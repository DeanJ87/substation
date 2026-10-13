"""T049: the watcher is a leased singleton; a sweep picks up new files; a rescan request triggers a sweep."""

from __future__ import annotations

import shutil
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.ingest.watcher import LEASE, Watcher
from apps.libraries.models import Library
from substation.tasks.lease import acquire
from substation.tasks.models import Lease, Task

FIX = Path(__file__).resolve().parents[1] / "fixtures/headers/capture/2026-09-28/LIGHT"
pytestmark = pytest.mark.django_db(transaction=True)


def test_lease_has_one_holder_and_can_be_taken_over():
    assert acquire("x", "a")
    assert not acquire("x", "b")
    assert acquire("x", "a")  # renew
    Lease.objects.filter(name="x").update(expires_at=timezone.now() - timedelta(seconds=1))
    assert acquire("x", "b")  # a lapsed: b takes over
    assert not acquire("x", "a")


@pytest.fixture
def lib_dir(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"watch-{tmp_path.name}"
    root.mkdir(parents=True)
    shutil.copyfile(FIX / "2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf", root / "a.xisf")
    yield root
    shutil.rmtree(root, ignore_errors=True)


def run_for(seconds: float) -> None:
    stop = threading.Event()
    t = threading.Thread(target=Watcher(stop).run, daemon=True)
    t.start()
    time.sleep(seconds)
    stop.set()
    t.join(timeout=10)


def test_watcher_sweeps_and_queues_new_files(lib_dir):
    run_for(2.5)
    assert Task.objects.filter(name__endswith="hash_file", args__1="a.xisf").exists()
    assert not Lease.objects.filter(name=LEASE).exists()  # released on stop


def test_second_watcher_waits_while_lease_is_held(lib_dir):
    assert acquire(LEASE, "someone-else", ttl_s=60)
    run_for(2.0)
    assert not Task.objects.exists()  # did nothing without the lease


def test_rescan_request_triggers_sweep(lib_dir):
    run_for(2.0)
    lib = Library.objects.get(mount_path=str(lib_dir))
    shutil.copyfile(FIX / "2026-09-28_20-50-41_Halpha_-20.00_600.00s_0031.xisf", lib_dir / "b.xisf")
    Library.objects.filter(pk=lib.pk).update(rescan_requested_at=timezone.now())
    run_for(2.0)
    assert Task.objects.filter(name__endswith="hash_file", args__1="b.xisf").exists()


def test_appledouble_files_are_skipped_and_watcher_survives(lib_dir):
    stop = threading.Event()
    t = threading.Thread(target=Watcher(stop).run, daemon=True)
    t.start()
    time.sleep(1.5)
    (lib_dir / "._b.xisf").write_bytes(b"\0" * 4096)  # macOS AppleDouble sidecar
    shutil.copyfile(lib_dir / "a.xisf", lib_dir / "c.xisf")
    time.sleep(2.0)
    alive = t.is_alive()
    stop.set()
    t.join(timeout=10)
    assert alive
    assert Task.objects.filter(name__endswith="hash_file", args__1="c.xisf").exists()
    assert not Task.objects.filter(args__1="._b.xisf").exists()


def test_empty_library_is_looked_at_again_soon(tmp_path):
    """A capture folder that is empty at start-up (or an unmounted share) is retried within seconds,
    not after the idle sweep interval."""
    from apps.ingest.watcher import UNREACHABLE_RETRY_S
    from apps.libraries.discovery import discover_libraries

    root = Path(settings.LIBRARY_ROOT) / f"empty-{tmp_path.name}"
    root.mkdir(parents=True)
    try:
        lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
        w = Watcher(threading.Event())
        w._due_sweeps([lib])
        assert w.next_sweep[lib.pk] - time.monotonic() <= UNREACHABLE_RETRY_S
        lib.refresh_from_db()
        shutil.copyfile(FIX / "2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf", root / "a.xisf")
        w.next_sweep.clear()
        w._due_sweeps([lib])
        assert Task.objects.filter(name__endswith="hash_file", args__1="a.xisf").exists()
        assert w.next_sweep[lib.pk] - time.monotonic() > UNREACHABLE_RETRY_S
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_sweep_that_queued_files_keeps_the_library_active(lib_dir):
    from apps.libraries.discovery import discover_libraries

    lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == lib_dir)
    lib.sweep_interval_active_s, lib.sweep_interval_idle_s = 60, 900
    w = Watcher(threading.Event())
    w._due_sweeps([lib])  # queues a.xisf; no Copy exists until it is hashed
    assert w.next_sweep[lib.pk] - time.monotonic() <= 60
