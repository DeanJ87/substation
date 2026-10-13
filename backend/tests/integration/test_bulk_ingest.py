"""T083: a bulk backlog never delays live subs, and a restart mid-queue resumes without redoing work."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
from django.conf import settings

from apps.ingest.sweep import sweep_library
from apps.libraries.discovery import discover_libraries
from substation.events.models import Event
from substation.tasks import PRIORITY_BULK, PRIORITY_LIVE, enqueue
from substation.tasks.models import Task, TaskStatus, Worker
from substation.tasks.worker import WorkerProcess
from tests.integration.demo_tasks import record

FIX = Path(__file__).resolve().parents[1] / "fixtures/headers/capture/2026-09-28/LIGHT"
SUB = FIX / "2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf"

pytestmark = pytest.mark.django_db(transaction=True)


def test_live_subs_overtake_a_bulk_backlog():
    for i in range(400):
        enqueue(record, f"bulk-{i}", priority=PRIORITY_BULK)
    for i in range(5):
        enqueue(record, f"live-{i}", priority=PRIORITY_LIVE)
    WorkerProcess("w1").run(max_tasks=5)
    ran = list(Event.objects.filter(type="test.ran").order_by("id").values_list("payload__label", flat=True))
    assert ran == [f"live-{i}" for i in range(5)]


def test_restart_mid_queue_resumes_without_redoing_work(tmp_path):
    root = Path(settings.LIBRARY_ROOT) / f"bulk-{tmp_path.name}"
    root.mkdir(parents=True)
    try:
        old = time.time() - 3 * 24 * 3600  # a few days old: bulk, not live
        for i in range(30):
            dst = root / f"sub_{i:03}.xisf"
            shutil.copyfile(SUB, dst)
            os.utime(dst, (old, old))
        lib = next(lib for lib in discover_libraries() if Path(lib.mount_path) == root)
        assert sweep_library(lib).queued == 30
        assert set(Task.objects.values_list("priority", flat=True)) == {PRIORITY_BULK}
        WorkerProcess("w1").run(max_tasks=10)  # then the container stops
        done = Task.objects.filter(status=TaskStatus.SUCCEEDED).count()
        assert done == 10
        # Start-up: the watcher sweeps again; finished files are unchanged, waiting ones are not queued twice
        again = sweep_library(lib)
        assert again.queued + again.unchanged == 30
        hashes = Task.objects.filter(name__endswith="hash_file")
        assert hashes.count() == 30  # nothing re-queued
        WorkerProcess("w2").run(max_tasks=500)
        assert hashes.filter(status=TaskStatus.SUCCEEDED).count() == 30
        assert sweep_library(lib).unchanged == 30
        assert Task.objects.filter(name__endswith="hash_file").count() == 30  # no re-hashing
    finally:
        shutil.rmtree(root, ignore_errors=True)
        Worker.objects.all().delete()
