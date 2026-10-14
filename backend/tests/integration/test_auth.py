"""T014: sign-in required; signup closed; admin-only endpoints (constitution VIII)."""

import json

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_api_requires_session():
    r = Client().get("/api/v1/openapi.json")
    assert r.status_code == 200  # the schema itself is public
    r = Client().get("/api/v1/queue/summary")
    assert r.status_code in (401, 404)  # 404 until the queue API exists (US4); never 200 without a session


def test_events_require_session():
    r = Client().get("/api/v1/events")
    assert r.status_code == 401
    assert r.json()["message"] == "Sign in to use SubStation."


def test_health_is_public():
    r = Client().get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["journal_mode"] in ("wal", "postgresql")  # SQLite in WAL mode, or PostgreSQL


def test_sign_in_and_out(admin_user):
    c = Client()
    r = c.post(
        "/_allauth/browser/v1/auth/login",
        data=json.dumps({"username": "admin", "password": "correct-horse-battery"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["data"]["user"]["username"] == "admin"
    r = c.get("/_allauth/browser/v1/auth/session")
    assert r.status_code == 200


def test_wrong_password_rejected(admin_user):
    r = Client().post(
        "/_allauth/browser/v1/auth/login",
        data=json.dumps({"username": "admin", "password": "wrong-password-123"}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_signup_is_closed():
    r = Client().post(
        "/_allauth/browser/v1/auth/signup",
        data=json.dumps({"username": "intruder", "password": "correct-horse-battery-2"}),
        content_type="application/json",
    )
    assert r.status_code == 403


def test_admin_guard(admin_user, standard_user):
    from apps.accounts.roles import is_admin

    assert is_admin(admin_user)
    assert not is_admin(standard_user)


def test_bootstrap_admin(monkeypatch, django_user_model):
    from django.core.management import call_command

    monkeypatch.setenv("SUBSTATION_ADMIN_USERNAME", "first")
    monkeypatch.setenv("SUBSTATION_ADMIN_PASSWORD", "correct-horse-battery")
    call_command("bootstrap_admin")
    user = django_user_model.objects.get(username="first")
    assert user.groups.filter(name="admin").exists()
    call_command("bootstrap_admin")  # idempotent once accounts exist
    assert django_user_model.objects.count() == 1
