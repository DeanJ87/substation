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
