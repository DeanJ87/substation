"""Queue summary (T086): what is waiting, by priority class, what is running, recent failures, and an ETA
from recent throughput. Shared by GET /queue/summary and the throttled `queue.changed` event."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from . import PRIORITY_BULK, PRIORITY_LIVE
from .models import Task, TaskStatus

THROUGHPUT_WINDOW = timedelta(minutes=10)


def priority_class(priority: int) -> str:
    if priority >= PRIORITY_LIVE:
        return "live"
    return "bulk" if priority >= PRIORITY_BULK else "archive"


def queue_summary() -> dict:
    now = timezone.now()
    by_class = {"live": 0, "bulk": 0, "archive": 0}
    for priority, n in (
        Task.objects.filter(status=TaskStatus.READY).values_list("priority").annotate(n=Count("id"))
    ):
        by_class[priority_class(priority)] += n
    agg = Task.objects.aggregate(
        running=Count("id", filter=Q(status=TaskStatus.RUNNING)),
        failed=Count("id", filter=Q(status=TaskStatus.FAILED, finished_at__gte=now - timedelta(hours=1))),
        # failures nobody has retried or dismissed yet: what the header's "N failed" counts
        open=Count("id", filter=Q(status=TaskStatus.FAILED) & ~Q(progress_note="dismissed")),
        recent=Count("id", filter=Q(status=TaskStatus.SUCCEEDED, finished_at__gte=now - THROUGHPUT_WINDOW)),
    )
    waiting = sum(by_class.values()) + agg["running"]
    rate = agg["recent"] / THROUGHPUT_WINDOW.total_seconds()  # tasks per second
    eta = None if waiting and not rate else (round(waiting / rate) if waiting else 0)
    return {
        "ready_by_priority": by_class,
        "running": agg["running"],
        "failed_recent": agg["failed"],
        "failed_open": agg["open"],
        "eta_seconds": eta,
    }
