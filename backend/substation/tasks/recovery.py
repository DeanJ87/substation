"""Recovery and housekeeping, run by the supervisor every few seconds (research R2)."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from .models import ResourceSample, Task, TaskStatus, Worker, WorkerState

log = logging.getLogger(__name__)

STALE_HEARTBEAT_S = 120  # a disk stall (QLC NVMe under two builds, 2026-10-12) can delay heartbeats a minute
# a stack or master build is an hour of work: only take it back after a long silence. A disk stall that locked the
# database for 4 minutes made a running stack look dead; it was requeued while still running and a second stack
# started beside it (2026-10-13)
STALE_HEAVY_S = 900
SAMPLE_RETENTION = timedelta(hours=1)  # the plan keeps an hour; Activity draws the last 15 minutes
FINISHED_RETENTION = timedelta(days=7)


def requeue_orphans(lenient: bool = False) -> int:
    """Tasks still `running` whose heartbeat stopped (worker died or the container restarted) go back to
    `ready`. Their attempt stays counted, so a task that crashes its worker repeatedly ends up failed.

    `lenient` (a supervisor's first minutes): a redeploy replaces every container at once, and the new ones have
    new names, so the old containers' tasks only show up here, as orphans. They were stopped, not crashed: put
    them all back rather than fail the single-attempt ones (master builds) (2026-10-12)."""
    from django.db.models import Q

    now = timezone.now()
    cutoff = now - timedelta(seconds=STALE_HEARTBEAT_S)
    heavy_cutoff = now - timedelta(seconds=STALE_HEAVY_S)
    stale = Task.objects.filter(status=TaskStatus.RUNNING).filter(
        Q(heartbeat_at__lt=heavy_cutoff) | (Q(heartbeat_at__lt=cutoff) & ~Q(slot="siril_heavy"))
    )
    over = stale.filter(attempts__gte=F("max_attempts")) if not lenient else stale.none()
    n_failed = over.update(
        status=TaskStatus.FAILED,
        finished_at=timezone.now(),
        error="Worker stopped responding too many times.",
    )
    n = stale.update(status=TaskStatus.READY, worker=None, run_after=timezone.now())
    Worker.objects.filter(heartbeat_at__lt=cutoff).exclude(state=WorkerState.STOPPED).update(
        state=WorkerState.STOPPED, current_task=None
    )
    if n or n_failed:
        log.warning("Requeued %s orphaned task(s); %s failed after too many attempts.", n, n_failed)
    return n


def requeue_all_running(host: str = "") -> int:
    """On supervisor start, this container's own workers can't be running anything yet: their tasks are from
    before the restart. Another container's tasks are left alone while its heartbeats are fresh (owner
    2026-10-12: two worker containers; the second one starting used to requeue the first one's builds, so they
    ran twice). A container that died without stopping is caught by `requeue_orphans` once its heartbeat is stale."""
    from django.db.models import Q

    cutoff = timezone.now() - timedelta(seconds=STALE_HEARTBEAT_S)
    mine = Q(worker__id__startswith=f"{host}-") if host else Q()
    q = Task.objects.filter(status=TaskStatus.RUNNING).filter(
        mine | Q(heartbeat_at__lt=cutoff) | Q(heartbeat_at=None) | Q(worker=None)
    )
    n = q.update(status=TaskStatus.READY, worker=None, run_after=timezone.now())
    workers = Worker.objects.exclude(state=WorkerState.STOPPED)
    workers.filter((Q(id__startswith=f"{host}-") if host else Q()) | Q(heartbeat_at__lt=cutoff)).update(
        state=WorkerState.STOPPED, current_task=None
    )
    return n


def prune() -> None:
    now = timezone.now()
    ResourceSample.objects.filter(at__lt=now - SAMPLE_RETENTION).delete()
    Task.objects.filter(
        status__in=[TaskStatus.SUCCEEDED, TaskStatus.CANCELLED], finished_at__lt=now - FINISHED_RETENTION
    ).delete()
    from substation.events.models import Event

    Event.objects.filter(created_at__lt=now - timedelta(hours=24)).delete()
