"""T028: installation settings endpoint (admin-only writes, user recorded)."""

import json

import pytest

pytestmark = pytest.mark.django_db


def test_read_and_update_settings(admin_client, standard_client):
    r = standard_client.get("/api/v1/settings")
    assert r.status_code == 200 and r.json()["site_lat"] is None
    body = json.dumps(
        {"site_name": "Home", "site_lat": 54.99, "site_lon": -1.66, "filter_aliases": {" HA ": "Hα"}}
    )
    r = standard_client.patch("/api/v1/settings", data=body, content_type="application/json")
    assert r.status_code == 403
    r = admin_client.patch("/api/v1/settings", data=body, content_type="application/json")
    assert r.status_code == 200, r.content
    out = r.json()
    assert out["site_lon"] == -1.66 and out["filter_aliases"] == {"ha": "Hα"} and out["updated_by"] == "admin"


def test_invalid_longitude(admin_client):
    r = admin_client.patch(
        "/api/v1/settings", data=json.dumps({"site_lon": 200}), content_type="application/json"
    )
    assert r.status_code == 422
    assert "Longitude" in r.json()["message"]


def test_seed_from_environment(monkeypatch):
    from apps.libraries.discovery import seed_installation_settings

    monkeypatch.setenv("SUBSTATION_SITE_LAT", "54.99")
    monkeypatch.setenv("SUBSTATION_SITE_LON", "-1.66")
    s = seed_installation_settings()
    assert s.site_lat == 54.99 and s.site_lon == -1.66


def test_workers_and_stacking_slots_are_set_from_settings(admin_client):
    """005 T001: worker count 1–16; stacking slots 1 to min(4, workers)."""

    def patch(body):
        return admin_client.patch("/api/v1/settings", data=json.dumps(body), content_type="application/json")

    r = patch({"worker_count": 3, "siril_heavy_slots": 2})
    assert r.status_code == 200 and r.json()["worker_count"] == 3 and r.json()["siril_heavy_slots"] == 2
    assert patch({"worker_count": 0}).status_code == 422
    assert patch({"siril_heavy_slots": 4}).status_code == 422  # more than the 3 workers
    assert patch({"worker_count": 1, "siril_heavy_slots": 1}).status_code == 200


def test_work_budget_is_set_and_the_work_folder_measured(admin_client, settings, tmp_path):
    """005 T004: the stacking work budget is a setting; the supervisor measures the work folder for Activity."""
    from apps.libraries.models import InstallationSettings
    from substation.tasks.management.commands.supervise import measure_work

    r = admin_client.patch(
        "/api/v1/settings", data=json.dumps({"work_budget_gb": 300}), content_type="application/json"
    )
    assert r.status_code == 200 and r.json()["work_budget_gb"] == 300
    assert (
        admin_client.patch(
            "/api/v1/settings", data=json.dumps({"work_budget_gb": 1}), content_type="application/json"
        ).status_code
        == 422
    )
    settings.WORK_DIR = tmp_path
    (tmp_path / "calibrated").mkdir()
    (tmp_path / "calibrated" / "a.fit").write_bytes(b"x" * 1000)
    (tmp_path / "other.bin").write_bytes(b"x" * 10)
    used = measure_work()
    assert used["calibrated"] == 1000 and used["other"] == 10 and used["total"] == 1010
    assert InstallationSettings.load().work_used["total"] == 1010
    act = admin_client.get("/api/v1/work").json()["readouts"]
    assert act["work_used"]["calibrated"] == 1000 and act["work_budget_bytes"] == 300e9


def test_siril_memory_is_shared_among_the_workers(admin_client):
    """005 T003: by default each Siril gets 90% of free memory divided by the workers alive; a setting overrides."""
    from django.utils import timezone

    from apps.engine.siril import limits
    from substation.tasks.models import Worker

    for i in range(8):
        Worker.objects.create(
            id=f"w{i}",
            pid=i,
            kind="worker",
            state="idle",
            started_at=timezone.now(),
            heartbeat_at=timezone.now(),
        )
    assert limits()[1] == 0.11
    r = admin_client.patch(
        "/api/v1/settings",
        data=json.dumps({"siril_mem_ratio": 0.3, "siril_threads": 2}),
        content_type="application/json",
    )
    assert r.status_code == 200 and r.json()["siril_mem_effective"] == 0.3
    assert limits() == (2, 0.3)
    assert (
        admin_client.patch(
            "/api/v1/settings", data=json.dumps({"siril_mem_ratio": 0.95}), content_type="application/json"
        ).status_code
        == 422
    )


def test_theme_follows_the_user(admin_client, standard_client):
    """007-DR-06: each user's theme is kept for them (night vision on one browser follows them to another)."""
    assert admin_client.get("/api/v1/users/me/preferences").json() == {"theme": ""}
    r = admin_client.put(
        "/api/v1/users/me/preferences", data=json.dumps({"theme": "night"}), content_type="application/json"
    )
    assert r.status_code == 200
    assert admin_client.get("/api/v1/users/me/preferences").json() == {"theme": "night"}
    assert standard_client.get("/api/v1/users/me/preferences").json() == {"theme": ""}


def test_sources_in_use_lists_winning_keywords(admin_client):
    """008 T19: which header keyword or pattern each value came from, with counts."""
    from datetime import UTC, datetime

    from apps.catalogue.models import Frame, FrameStatus, MetadataValue

    t = datetime(2026, 9, 1, tzinfo=UTC)
    for i, kw in enumerate(("FILTER", "FILTER", "FILT")):
        f = Frame.objects.create(
            sha256=f"src{i}".ljust(64, "0"),
            size_bytes=1,
            format="fits",
            first_seen_at=t,
            status=FrameStatus.CATALOGUED,
        )
        MetadataValue.objects.create(
            frame=f, field="filter", value="Hα", source="header", source_detail=kw, is_winner=True
        )
    rows = admin_client.get("/api/v1/settings/sources").json()
    assert rows[0] == {"field": "filter", "source": "header", "detail": "FILTER", "frames": 2}


def test_priority_mode(admin_client):
    """008 T9: new subs first, or everything in order."""
    from django.utils import timezone

    from apps.catalogue.models import Frame
    from apps.processing.tasks import priority_for
    from substation.tasks import PRIORITY_BULK, PRIORITY_LIVE

    f = Frame(sha256="p" * 64, size_bytes=1, format="fits", first_seen_at=timezone.now())
    assert priority_for(f) == PRIORITY_LIVE - 2
    r = admin_client.patch(
        "/api/v1/settings",
        data=json.dumps({"processing": {"queue": {"priority_mode": "in_order"}}}),
        content_type="application/json",
    )
    assert r.status_code == 200 and r.json()["processing"]["queue"]["priority_mode"] == "in_order"
    assert priority_for(f) == PRIORITY_BULK - 2
    bad = admin_client.patch(
        "/api/v1/settings",
        data=json.dumps({"processing": {"queue": {"priority_mode": "random"}}}),
        content_type="application/json",
    )
    assert bad.status_code == 422
