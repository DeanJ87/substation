"""005-DR-23: SubStation updates itself when a newer build exists, only once no stack is running."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.libraries.models import InstallationSettings
from substation import updates
from substation.tasks.models import Task, TaskStatus

pytestmark = pytest.mark.django_db
NEW = {"sha": "bbbbbbb1234", "title": "New", "built_at": "2026-10-14T09:00:00Z", "url": ""}


@pytest.fixture
def configured(monkeypatch, settings):
    settings.SUBSTATION_VERSION = "0.1.0 · poc-substation · aaaaaaa · 14 Oct 2026"
    monkeypatch.setenv("SUBSTATION_UPDATE_WEBHOOK", "https://portainer.example/api/stacks/webhooks/x")
    monkeypatch.setenv("SUBSTATION_UPDATE_REPO", "someone/substation")


def test_waits_for_stacks_then_redeploys_and_resumes(configured):
    posted = []
    heavy = Task.objects.create(
        name="integrate",
        slot="siril_heavy",
        status=TaskStatus.RUNNING,
        run_after=timezone.now(),
        enqueued_at=timezone.now(),
    )
    u = updates.tick(fetch=lambda r, b: NEW, post=posted.append)
    s = InstallationSettings.load()
    assert u["state"] == "draining" and s.queue_paused and "1 stack" in u["reason"] and not posted

    heavy.status = TaskStatus.SUCCEEDED
    heavy.save()
    u = updates.tick(fetch=lambda r, b: NEW, post=posted.append)
    assert u["state"] == "deploying" and posted == [
        "https://portainer.example/api/stacks/webhooks/x?SUBSTATION_TAG=bbbbbbb"
    ]

    # the new containers start with the new version: the queue resumes
    from django.conf import settings

    settings.SUBSTATION_VERSION = "0.1.0 · poc-substation · bbbbbbb · 14 Oct 2026"
    u = updates.tick(fetch=lambda r, b: NEW, post=posted.append)
    assert u["state"] == "" and u["last"]["sha"] == "bbbbbbb"
    assert not InstallationSettings.load().queue_paused


def test_a_queue_paused_by_hand_stays_paused(configured, settings):
    s = InstallationSettings.load()
    s.queue_paused = True
    s.save()
    updates.tick(fetch=lambda r, b: NEW, post=lambda url: None)
    settings.SUBSTATION_VERSION = "0.1.0 · poc-substation · bbbbbbb · 14 Oct 2026"
    updates.tick(fetch=lambda r, b: NEW, post=lambda url: None)
    assert InstallationSettings.load().queue_paused


def test_a_redeploy_that_never_arrives_fails_and_resumes(configured):
    now = timezone.now()
    updates.tick(now=now, fetch=lambda r, b: NEW, post=lambda url: None)
    u = updates.tick(now=now + timedelta(minutes=25), fetch=lambda r, b: NEW, post=lambda url: None)
    assert u["state"] == "failed" and "still running" in u["reason"]
    assert not InstallationSettings.load().queue_paused
    # and it doesn't try the same build again by itself
    assert updates.tick(now=now + timedelta(hours=1), fetch=lambda r, b: NEW)["state"] == "failed"


def test_off_without_a_webhook_and_idle_when_current(configured, monkeypatch):
    same = {**NEW, "sha": "aaaaaaa999"}
    assert updates.tick(fetch=lambda r, b: same, post=lambda url: None).get("state", "") == ""
    monkeypatch.delenv("SUBSTATION_UPDATE_WEBHOOK")
    assert updates.tick(fetch=lambda r, b: NEW, post=lambda url: None) == InstallationSettings.load().updates
    assert not InstallationSettings.load().queue_paused
