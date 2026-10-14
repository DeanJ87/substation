"""002-DR-25: a master built while every light is being re-matched gets a re-match of its own. That run had already
read the masters, so a request then queues another run after it instead of joining it (14 Oct 2026: a 60 s dark
built mid-run unlocked nothing)."""

from __future__ import annotations

import pytest

from apps.processing.tasks import rematch_lights
from substation.tasks import enqueue
from substation.tasks.models import Task, TaskStatus

pytestmark = pytest.mark.django_db


def test_a_waiting_rematch_is_joined_and_a_running_one_gets_a_follow_up():
    first = enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True)
    assert (
        enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True).id == first.id
    )  # still waiting: joined
    Task.objects.filter(pk=first.id).update(status=TaskStatus.RUNNING)
    second = enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True)
    assert second.id != first.id
    assert enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True).id == second.id
    assert Task.objects.filter(name__endswith="rematch_lights").count() == 2


def test_without_fresh_a_running_task_is_still_joined():
    first = enqueue(rematch_lights, dedupe_key="other")
    Task.objects.filter(pk=first.id).update(status=TaskStatus.RUNNING)
    assert enqueue(rematch_lights, dedupe_key="other").id == first.id


def test_a_later_rematch_waits_for_one_already_running():
    from datetime import timedelta

    from django.utils import timezone

    from apps.processing.tasks import _wait_for_earlier_rematch
    from substation.tasks import Reschedule, current_task_id

    now = timezone.now()
    first = enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True)
    Task.objects.filter(pk=first.id).update(status=TaskStatus.RUNNING, started_at=now - timedelta(minutes=3))
    second = enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True)
    Task.objects.filter(pk=second.id).update(status=TaskStatus.RUNNING, started_at=now)
    token = current_task_id.set(str(second.id))
    try:
        with pytest.raises(Reschedule):
            _wait_for_earlier_rematch()
    finally:
        current_task_id.reset(token)
    token = current_task_id.set(str(first.id))
    try:
        _wait_for_earlier_rematch()  # the earlier one carries on
    finally:
        current_task_id.reset(token)
