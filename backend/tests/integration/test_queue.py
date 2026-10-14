"""T024: queue behaviour (research R2): priority order, dedupe, retries, rescheduling, slots, dead-worker
recovery, and scaling workers up and down without losing or duplicating tasks."""

from __future__ import annotations

import signal
import time
from datetime import timedelta

import pytest
from django.utils import timezone

from substation.events.models import Event
from substation.tasks import enqueue
from substation.tasks.claim import claim
from substation.tasks.models import Task, TaskStatus, Worker
from substation.tasks.recovery import requeue_all_running, requeue_orphans
from substation.tasks.worker import WorkerProcess
from tests.conftest import manage

from . import demo_tasks as dt

pytestmark = pytest.mark.django_db(transaction=True)


def ran_labels() -> list[str]:
    return [e.payload["label"] for e in Event.objects.filter(type="test.ran").order_by("id")]


def test_priority_then_fifo():
    enqueue(dt.record, "bulk-1", priority=40)
    enqueue(dt.record, "archive", priority=10)
    enqueue(dt.record, "live", priority=80)
    enqueue(dt.record, "bulk-2", priority=40)
    WorkerProcess("w-test").run(max_tasks=10)
    assert ran_labels() == ["live", "bulk-1", "bulk-2", "archive"]


def test_dedupe_key_returns_existing_task():
    a = enqueue(dt.record, "x", dedupe_key="hash:lib:a.fits:1")
    b = enqueue(dt.record, "x", dedupe_key="hash:lib:a.fits:1")
    assert a.id == b.id
    assert Task.objects.count() == 1
    WorkerProcess("w-test").run(max_tasks=5)
    c = enqueue(dt.record, "x", dedupe_key="hash:lib:a.fits:1")  # finished: key is free again
    assert c.id != a.id


def test_retry_with_backoff_then_success(monkeypatch):
    monkeypatch.setattr("substation.tasks.worker.BACKOFF_BASE_S", 0)
    r = enqueue(dt.flaky, "f1", 2)
    w = WorkerProcess("w-test")
    for _ in range(3):
        w.run(max_tasks=1)
    row = Task.objects.get(pk=r.id)
    assert row.status == TaskStatus.SUCCEEDED
    assert row.attempts == 3


def test_failure_after_max_attempts(monkeypatch):
    monkeypatch.setattr("substation.tasks.worker.BACKOFF_BASE_S", 0)
    r = enqueue(dt.flaky, "f2", 99)
    w = WorkerProcess("w-test")
    for _ in range(5):
        w.run(max_tasks=1)
    row = Task.objects.get(pk=r.id)
    assert row.status == TaskStatus.FAILED
    assert row.attempts == 3
    assert "failure 3" in row.error


def test_backoff_delays_retry():
    r = enqueue(dt.flaky, "f3", 1)
    WorkerProcess("w-test").run(max_tasks=1)
    row = Task.objects.get(pk=r.id)
    assert row.status == TaskStatus.READY
    assert row.run_after > timezone.now()
    assert claim("w-test") is None  # not due yet


def test_reschedule_does_not_count_an_attempt():
    r = enqueue(dt.reschedule_once, "r1")
    w = WorkerProcess("w-test")
    w.run(max_tasks=1)
    row = Task.objects.get(pk=r.id)
    assert row.status == TaskStatus.READY and row.attempts == 0
    assert row.progress_note == "file still being written"
    w.run(max_tasks=1)
    assert Task.objects.get(pk=r.id).status == TaskStatus.SUCCEEDED


def test_siril_heavy_slot_limit():
    for wid in ("w1", "w2"):
        Worker.objects.create(id=wid, pid=1, started_at=timezone.now(), heartbeat_at=timezone.now())
    enqueue(dt.heavy, "h1", 0)
    enqueue(dt.heavy, "h2", 0)
    first = claim("w1", heavy_slots=1)
    assert first is not None
    assert claim("w2", heavy_slots=1) is None  # slot full
    assert claim("w2", heavy_slots=2) is not None


def test_orphaned_task_is_requeued():
    r = enqueue(dt.record, "orphan")
    Worker.objects.create(id="dead", pid=1, started_at=timezone.now(), heartbeat_at=timezone.now())
    row = claim("dead")
    assert row is not None and str(row.pk) == r.id
    Task.objects.filter(pk=row.pk).update(heartbeat_at=timezone.now() - timedelta(minutes=5))
    assert requeue_orphans() == 1
    assert Task.objects.get(pk=row.pk).status == TaskStatus.READY


def test_a_starting_container_leaves_another_containers_tasks_alone():
    # two worker containers (owner 2026-10-12): container B starting must not requeue what A is running
    a, b = enqueue(dt.record, "a"), enqueue(dt.record, "b")
    for wid in ("hostA-worker-0", "hostB-worker-0"):
        Worker.objects.create(id=wid, pid=1, started_at=timezone.now(), heartbeat_at=timezone.now())
    ra, rb = claim("hostA-worker-0"), claim("hostB-worker-0")
    assert ra is not None and rb is not None
    Task.objects.filter(pk__in=[ra.pk, rb.pk]).update(heartbeat_at=timezone.now())
    assert requeue_all_running("hostB") == 1  # only B's own task, from before B's restart
    assert Task.objects.get(pk=ra.pk).status == TaskStatus.RUNNING
    assert Task.objects.get(pk=rb.pk).status == TaskStatus.READY
    assert {a.id, b.id} == {str(ra.pk), str(rb.pk)}


def test_a_redeploys_stopped_single_attempt_task_is_requeued_not_failed():
    # a master build (one attempt) on a container a redeploy replaced: the new container sees it as an orphan
    r = enqueue(dt.record, "build")
    Worker.objects.create(
        id="oldhost-worker-0", pid=1, started_at=timezone.now(), heartbeat_at=timezone.now()
    )
    row = claim("oldhost-worker-0")
    assert row is not None
    Task.objects.filter(pk=row.pk).update(heartbeat_at=timezone.now() - timedelta(minutes=5), max_attempts=1)
    requeue_orphans(lenient=True)
    assert Task.objects.get(pk=r.id).status == TaskStatus.READY


def test_a_finisher_takes_only_its_queue_and_the_others_skip_it():
    # spec 010: post-processing runs on a finisher container; the main workers leave it alone
    for wid in ("main", "finisher", "finisher-2"):
        Worker.objects.create(id=wid, pid=1, started_at=timezone.now(), heartbeat_at=timezone.now())
    r = enqueue(dt.record, "finish-me")
    Task.objects.filter(pk=r.id).update(queue="finish")
    assert claim("main", skip=["finish"]) is None
    row = claim("finisher", only=["finish"])
    assert row is not None and str(row.pk) == r.id
    enqueue(dt.record, "ordinary")
    assert claim("finisher-2", only=["finish"]) is None


@pytest.mark.slow
def test_scaling_loses_and_duplicates_nothing():
    """Supervisor with 2 → 4 → 1 workers while 60 tasks run: every task runs exactly once."""
    from apps.libraries.models import InstallationSettings

    for i in range(60):
        enqueue(dt.slow, f"t{i}", 0.3)
    s = InstallationSettings.load()
    s.worker_count = 2
    s.save()
    sup = manage("supervise", "--no-web", "--no-watcher")
    try:
        time.sleep(6)
        InstallationSettings.objects.filter(pk=1).update(worker_count=4)
        time.sleep(6)
        InstallationSettings.objects.filter(pk=1).update(worker_count=1)
        deadline = time.time() + 120
        while time.time() < deadline and Task.objects.exclude(status=TaskStatus.SUCCEEDED).exists():
            time.sleep(1)
    finally:
        sup.send_signal(signal.SIGTERM)
        sup.wait(timeout=60)
    labels = ran_labels()
    assert sorted(labels) == sorted(f"t{i}" for i in range(60))
    assert len(labels) == len(set(labels))
    pids = {e.payload["pid"] for e in Event.objects.filter(type="test.ran")}
    assert len(pids) >= 3  # ran on several worker processes


def test_a_running_task_can_be_cancelled():
    """Cancel on a running job (spec 005 FR-005, 004-DR-02): it stops at its next progress check and ends as
    cancelled, not failed, and is not retried."""
    r = enqueue(dt.asks_to_stop, "c1")
    WorkerProcess("w-test").run(max_tasks=2)
    row = Task.objects.get(pk=r.id)
    assert row.status == TaskStatus.CANCELLED and row.attempts == 1 and row.return_value is None


def test_a_stopping_worker_puts_its_task_back(monkeypatch):
    """005-DR-25: a redeploy stops the worker; its task goes back in the queue without using an attempt."""
    from substation.tasks import shutting_down

    r = enqueue(dt.stopped_by_redeploy, "s1")
    try:
        WorkerProcess("w-test").run(max_tasks=1)
    finally:
        shutting_down.clear()
    row = Task.objects.get(pk=r.id)
    assert row.status == TaskStatus.READY and row.attempts == 0 and row.worker_id is None
    assert "back in the queue" in row.progress_note
