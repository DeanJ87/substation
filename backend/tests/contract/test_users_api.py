"""Users (spec 008 T16): admins list, add and change roles; a viewer can review but not override."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Frame, FrameStatus, FrameType
from tests.conftest import signed_in_client

pytestmark = pytest.mark.django_db


def test_admin_manages_users_and_viewers_cannot_override(admin_client, standard_client):
    assert standard_client.get("/api/v1/users").status_code == 403
    r = admin_client.post(
        "/api/v1/users",
        {"username": "guest", "password": "short", "role": "viewer"},
        content_type="application/json",
    )
    assert r.status_code == 422 and "10 characters" in r.json()["message"]
    r = admin_client.post(
        "/api/v1/users",
        {"username": "guest", "password": "correct-horse-battery", "role": "viewer"},
        content_type="application/json",
    )
    assert r.status_code == 201 and r.json()["role"] == "viewer"
    roles = {u["username"]: u["role"] for u in admin_client.get("/api/v1/users").json()}
    assert roles["guest"] == "viewer"
    f = Frame.objects.create(
        sha256="v" * 64,
        size_bytes=1,
        format="fits",
        first_seen_at=datetime.now(UTC),
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
    )
    guest = signed_in_client("guest")
    r = guest.post(
        "/api/v1/frames/verdict",
        {"sha256s": [f.sha256], "verdict": "reject"},
        content_type="application/json",
    )
    assert r.status_code == 403 and "can't change verdicts" in r.json()["message"]
    uid = next(u["id"] for u in admin_client.get("/api/v1/users").json() if u["username"] == "guest")
    assert (
        admin_client.patch(
            f"/api/v1/users/{uid}", {"role": "standard"}, content_type="application/json"
        ).json()["role"]
        == "standard"
    )
    assert (
        guest.post(
            "/api/v1/frames/verdict",
            {"sha256s": [f.sha256], "verdict": "reject"},
            content_type="application/json",
        ).status_code
        == 200
    )
