"""005 T013: the Activity API — overview, pause, retry, cancel, bump, move, dismiss."""

from datetime import timedelta

import pytest
from django.utils import timezone

from substation.tasks.models import Task, TaskStatus

pytestmark = pytest.mark.django_db


def job(name="apps.processing.tasks.calibrate_measure", status=TaskStatus.READY, priority=40, ago=0, **kw):
    now = timezone.now() - timedelta(seconds=ago)
    return Task.objects.create(
        name=name, status=status, priority=priority, run_after=now, enqueued_at=now, **kw
    )


def post(client, url, body=None):
    import json

    return client.post(f"/api/v1/work{url}", data=json.dumps(body or {}), content_type="application/json")


def test_overview_lists_running_waiting_and_failed(admin_client):
    job(status=TaskStatus.RUNNING)
    job(ago=5)
    job(
        status=TaskStatus.FAILED,
        error="OSError: [Errno 28] No space left on device",
        attempts=3,
        max_attempts=3,
        finished_at=timezone.now(),
    )
    d = admin_client.get("/api/v1/work").json()
    assert {"running", "readouts", "workers", "queue_by_kind"} <= d.keys()
    assert len(d["running"]) == 1
    failed = [
        j
        for k, v in d.items()
        if isinstance(v, list)
        for j in v
        if isinstance(j, dict) and j.get("status") == "failed"
    ]
    assert failed and failed[0]["error"].startswith("Disk full")


def test_pause_is_admin_only(admin_client, standard_client):
    assert post(standard_client, "/pause", {"paused": True}).status_code == 403
    assert post(admin_client, "/pause", {"paused": True}).json() == {"paused": True}
    assert post(admin_client, "/pause", {"paused": False}).json() == {"paused": False}


def test_retry_cancel_and_dismiss(admin_client):
    f = job(status=TaskStatus.FAILED, error="boom", attempts=3, finished_at=timezone.now())
    w = job()
    assert post(admin_client, f"/jobs/{w.pk}/retry").status_code == 409  # not failed
    assert post(admin_client, f"/jobs/{f.pk}/dismiss").status_code == 200
    r = post(admin_client, f"/jobs/{f.pk}/retry")
    assert r.status_code == 200 and Task.objects.get(pk=f.pk).status == TaskStatus.READY
    assert post(admin_client, f"/jobs/{w.pk}/cancel").status_code == 200
    assert Task.objects.get(pk=w.pk).status == TaskStatus.CANCELLED
    run = job(status=TaskStatus.RUNNING)
    post(admin_client, f"/jobs/{run.pk}/cancel")
    assert Task.objects.get(pk=run.pk).cancel_requested


def test_bump_and_move_reorder_the_queue(admin_client):
    a, b, c = job(ago=30), job(ago=20), job(ago=10, priority=20)
    order = lambda: list(  # noqa: E731
        Task.objects.filter(status=TaskStatus.READY)
        .order_by("-priority", "enqueued_at")
        .values_list("pk", flat=True)
    )
    assert order() == [a.pk, b.pk, c.pk]
    post(admin_client, f"/jobs/{c.pk}/move", {"before": str(b.pk)})
    assert order() == [a.pk, c.pk, b.pk]
    post(admin_client, f"/jobs/{a.pk}/move", {"after": str(b.pk)})
    assert order() == [c.pk, b.pk, a.pk]
    post(admin_client, f"/jobs/{a.pk}/bump")
    assert order()[0] == a.pk
    assert post(admin_client, f"/jobs/{a.pk}/move", {}).status_code == 422
