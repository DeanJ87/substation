"""Notifications (spec 008 T15): only chosen events are sent, to ntfy and a webhook; a failed send is reported, not
raised; the settings validate addresses."""

from __future__ import annotations

import json

import pytest

from substation import notify

pytestmark = pytest.mark.django_db


def test_send_respects_events_and_reports_failures(monkeypatch):
    sent = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout):
        sent.append((req.full_url, req.data, dict(req.header_items())))
        if "bad" in req.full_url:
            raise OSError("connection refused")
        return Resp()

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake)
    cfg = {
        "ntfy": "https://ntfy.sh/my-scope",
        "webhook": "https://bad.example/hook",
        "events": ["master_finished"],
    }
    assert notify.send("job_failed", "x", "y", cfg=cfg) == []  # not chosen: nothing sent
    failed = notify.send("master_finished", "Master v2 is ready", "Soul Nebula · Hα: 45 subs.", cfg=cfg)
    assert [u for u, _, _ in sent] == ["https://ntfy.sh/my-scope", "https://bad.example/hook"]
    assert (
        sent[0][1] == "Soul Nebula · Hα: 45 subs.".encode()
        and json.loads(sent[1][1])["event"] == "master_finished"
    )
    assert failed == ["webhook: connection refused"]


def test_settings_validate_and_test_needs_a_channel(admin_client):
    r = admin_client.post("/api/v1/settings/notifications/test")
    assert r.status_code == 422 and "ntfy topic or webhook" in r.json()["message"]
    bad = admin_client.patch(
        "/api/v1/settings",
        {"processing": {"notifications": {"ntfy": "ntfy.sh/x"}}},
        content_type="application/json",
    )
    assert bad.status_code == 422 and "http" in bad.json()["message"]
    ok = admin_client.patch(
        "/api/v1/settings",
        {"processing": {"notifications": {"ntfy": "https://ntfy.sh/x"}}},
        content_type="application/json",
    )
    assert ok.json()["processing"]["notifications"]["ntfy"] == "https://ntfy.sh/x"
