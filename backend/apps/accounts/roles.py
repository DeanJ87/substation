"""Roles: Django groups `admin` and `standard` (constitution VIII). Admins manage accounts, libraries,
patterns, ignore rules and workers; standard users review and decide."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser, Group

ADMIN = "admin"
STANDARD = "standard"
VIEWER = "viewer"  # can review, can't override (spec 008, 008-DR-07)
ROLES = (ADMIN, STANDARD, VIEWER)


def ensure_groups() -> None:
    for name in ROLES:
        Group.objects.get_or_create(name=name)


def is_admin(user: AbstractBaseUser | AnonymousUser) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name=ADMIN).exists()  # type: ignore[union-attr]


def is_viewer(user: AbstractBaseUser | AnonymousUser) -> bool:
    return (
        bool(getattr(user, "is_authenticated", False))
        and not is_admin(user)
        and user.groups.filter(name=VIEWER).exists()  # type: ignore[union-attr]
    )


def role_of(user: AbstractBaseUser) -> str:
    if is_admin(user):
        return ADMIN
    return VIEWER if is_viewer(user) else STANDARD
