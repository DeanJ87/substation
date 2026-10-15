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


def still_failing(tasks) -> list[Task]:  # noqa: ANN001
    """Failures that still matter (2026-10-15): one whose job later ran again and succeeded, or whose master has
    since been built or deleted, has nothing left to do and clears itself."""
    from apps.processing.models import Master, MasterState

    out = []
    for t in tasks:
        later = Task.objects.filter(
            name=t.name, args=t.args, status=TaskStatus.SUCCEEDED, finished_at__gt=t.finished_at
        ).exists()
        if later:
            continue
        if t.name.endswith((".integrate", ".postprocess_master")) and t.args:
            m = Master.objects.filter(pk=t.args[0]).values_list("state", flat=True).first()
            if m is None or (t.name.endswith(".integrate") and m != MasterState.FAILED):
                continue
        out.append(t)
    return out


def open_failures() -> list[Task]:
    """Failures from the last two days nobody has dismissed and that still matter: Activity's list and the header's
    count agree."""
    recent = (
        Task.objects.filter(status=TaskStatus.FAILED, finished_at__gte=timezone.now() - timedelta(days=2))
        .exclude(progress_note="dismissed")
        .order_by("-finished_at")[:60]
    )
    return still_failing(recent)


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
        recent=Count("id", filter=Q(status=TaskStatus.SUCCEEDED, finished_at__gte=now - THROUGHPUT_WINDOW)),
    )
    waiting = sum(by_class.values()) + agg["running"]
    rate = agg["recent"] / THROUGHPUT_WINDOW.total_seconds()  # tasks per second
    eta = None if waiting and not rate else (round(waiting / rate) if waiting else 0)
    return {
        "ready_by_priority": by_class,
        "running": agg["running"],
        "failed_recent": agg["failed"],
        "failed_open": len(open_failures()),
        "eta_seconds": eta,
    }
