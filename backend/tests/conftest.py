"""Shared fixtures."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def admin_user(db, django_user_model):
    from django.contrib.auth.models import Group

    from apps.accounts.roles import ADMIN, ensure_groups

    ensure_groups()
    user = django_user_model.objects.create_user(username="admin", password="correct-horse-battery")
    user.groups.add(Group.objects.get(name=ADMIN))
    return user


@pytest.fixture
def standard_user(db, django_user_model):
    from django.contrib.auth.models import Group

    from apps.accounts.roles import STANDARD, ensure_groups

    ensure_groups()
    user = django_user_model.objects.create_user(username="observer", password="correct-horse-battery")
    user.groups.add(Group.objects.get(name=STANDARD))
    return user


def signed_in_client(username: str) -> Client:
    c = Client()
    r = c.post(
        "/_allauth/browser/v1/auth/login",
        data=json.dumps({"username": username, "password": "correct-horse-battery"}),
        content_type="application/json",
    )
    assert r.status_code == 200, r.content
    return c


@pytest.fixture
def admin_client(admin_user) -> Client:
    return signed_in_client(admin_user.username)


@pytest.fixture
def standard_client(standard_user) -> Client:
    return signed_in_client(standard_user.username)


def manage(*args: str, timeout: float = 60, **kwargs) -> subprocess.Popen:
    """Start `manage.py <args>` against the test database (for multi-process tests)."""
    env: dict[str, str] = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "substation.settings",
        "SUBSTATION_DB_PATH": str(settings.DATABASES["default"]["NAME"]),
    }
    return subprocess.Popen(
        [sys.executable, str(BACKEND / "manage.py"), *args], cwd=BACKEND, env=env, **kwargs
    )


@pytest.fixture(autouse=True)
def _no_login_rate_limit(settings):
    """allauth counts sign-ins in the cache across the whole run; the suite signs in far more than a person would."""
    settings.ACCOUNT_RATE_LIMITS = False
