"""T084: GET /queue/summary and the throttled queue.changed event."""

from __future__ import annotations

import pytest

from substation.events.models import Event
from substation.tasks import PRIORITY_ARCHIVE, PRIORITY_BULK, PRIORITY_LIVE, enqueue
from substation.tasks.summary import priority_class
from substation.tasks.worker import WorkerProcess
from tests.integration.demo_tasks import record

pytestmark = pytest.mark.django_db(transaction=True)


def test_summary_counts_by_class(admin_client):
    for p, n in ((PRIORITY_LIVE, 2), (PRIORITY_LIVE + 1, 1), (PRIORITY_BULK, 3), (PRIORITY_ARCHIVE, 4)):
        for i in range(n):
            enqueue(record, f"{p}-{i}", priority=p)
    r = admin_client.get("/api/v1/queue/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["ready_by_priority"] == {"live": 3, "bulk": 3, "archive": 4}
    assert body["running"] == 0 and body["failed_recent"] == 0
    assert body["eta_seconds"] is None  # nothing finished recently, so no rate yet
    WorkerProcess("w1").run(max_tasks=4)
    body = admin_client.get("/api/v1/queue/summary").json()
    assert sum(body["ready_by_priority"].values()) == 6
    assert body["eta_seconds"] is not None and body["eta_seconds"] > 0


def test_summary_needs_a_session(client):
    assert client.get("/api/v1/queue/summary").status_code == 401


def test_queue_changed_is_throttled():
    for i in range(50):
        enqueue(record, f"t-{i}")
    WorkerProcess("w1").run(max_tasks=100)
    events = Event.objects.filter(type="queue.changed")
    # one when work starts, at most one per 2 s while working, one when the queue drains
    assert 1 <= events.count() <= 4
    last = events.order_by("id").last()
    assert last.payload["ready_by_priority"] == {"live": 0, "bulk": 0, "archive": 0}


def test_priority_classes():
    assert [priority_class(p) for p in (81, 80, 41, 40, 11, 10)] == [
        "live",
        "live",
        "bulk",
        "bulk",
        "archive",
        "archive",
    ]
