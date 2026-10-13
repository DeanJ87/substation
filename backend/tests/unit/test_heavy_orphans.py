"""A stack is only taken back after a long silence: a disk stall that held the database for minutes made a running
stack look dead, and a second one started beside it (2026-10-13)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from substation.tasks.models import Task, TaskStatus
from substation.tasks.recovery import requeue_orphans

pytestmark = pytest.mark.django_db


def running(slot: str, silent_s: int) -> Task:
    now = timezone.now()
    return Task.objects.create(
        name=f"x.{slot}",
        queue="stack" if slot == "siril_heavy" else "process",
        slot=slot,
        status=TaskStatus.RUNNING,
        run_after=now,
        enqueued_at=now,
        started_at=now,
        heartbeat_at=now - timedelta(seconds=silent_s),
        attempts=1,
        max_attempts=2,
    )


def test_a_quiet_stack_is_left_running_a_quiet_light_job_is_taken_back():
    stack, light, gone = running("siril_heavy", 300), running("light", 300), running("siril_heavy", 1200)
    requeue_orphans()
    assert Task.objects.get(pk=stack.pk).status == TaskStatus.RUNNING
    assert Task.objects.get(pk=light.pk).status == TaskStatus.READY
    assert Task.objects.get(pk=gone.pk).status == TaskStatus.READY
