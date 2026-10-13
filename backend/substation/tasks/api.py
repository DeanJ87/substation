"""GET /api/v1/queue/summary (T086). No `from __future__ import annotations` here: see substation.api."""

from substation.api import Router, Schema

from .summary import queue_summary

router = Router(tags=["queue"])


class QueueSummaryOut(Schema):
    ready_by_priority: dict[str, int]
    running: int
    failed_recent: int
    failed_open: int
    eta_seconds: float | None


@router.get("/summary", response=QueueSummaryOut)
def summary(request):
    return queue_summary()
