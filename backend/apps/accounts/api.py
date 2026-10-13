"""Users (spec 008 T16, 008-DR-07): accounts with their role and last sign-in; admins add users and change roles.
No `from __future__ import annotations` here: see substation.api."""

from datetime import datetime
from typing import Literal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404

from substation.api import ApiError, Router, Schema, Status, admin_required

from .roles import ADMIN, ROLES, ensure_groups, role_of

router = Router(tags=["users"])
Role = Literal["admin", "standard", "viewer"]


class UserOut(Schema):
    id: int
    username: str
    role: str
    last_login: datetime | None
    date_joined: datetime


class UserIn(Schema):
    username: str
    password: str
    role: Role = "standard"


class UserPatch(Schema):
    role: Role


def _out(u) -> UserOut:  # noqa: ANN001
    return UserOut(
        id=u.pk,
        username=u.get_username(),
        role=role_of(u),
        last_login=u.last_login,
        date_joined=u.date_joined,
    )


def _set_role(u, role: str) -> None:  # noqa: ANN001
    ensure_groups()
    u.groups.remove(*Group.objects.filter(name__in=ROLES))
    u.groups.add(Group.objects.get(name=role))


class PreferencesIO(Schema):
    theme: Literal["dark", "light", "night", ""] = ""


@router.get("/me/preferences", response=PreferencesIO)
def my_preferences(request):
    from .models import UserPreference

    p = UserPreference.objects.filter(user=request.user).first()
    return PreferencesIO(theme=p.theme if p else "")  # type: ignore[arg-type]


@router.put("/me/preferences", response=PreferencesIO)
def set_my_preferences(request, body: PreferencesIO):
    """Any signed-in user, viewers too: it changes only how the app looks to them."""
    from .models import UserPreference

    UserPreference.objects.update_or_create(user=request.user, defaults={"theme": body.theme})
    return body


@router.get("", response=list[UserOut])
@admin_required
def list_users(request):
    return [_out(u) for u in get_user_model().objects.order_by("username")]


@router.post("", response={201: UserOut})
@admin_required
def add_user(request, body: UserIn):
    User = get_user_model()  # noqa: N806
    name = body.username.strip()
    if not name:
        raise ApiError(422, "invalid", "Give the account a username.")
    if User.objects.filter(username__iexact=name).exists():
        raise ApiError(409, "exists", f"There's already an account called {name}.")
    if len(body.password) < 10:
        raise ApiError(422, "invalid", "Use a password of at least 10 characters.")
    u = User.objects.create_user(username=name, password=body.password)
    _set_role(u, body.role)
    return Status(201, _out(u))


@router.patch("/{id}", response=UserOut)
@admin_required
def change_role(request, id: int, body: UserPatch):  # noqa: A002
    u = get_object_or_404(get_user_model(), pk=id)
    if u.pk == request.user.pk and body.role != ADMIN:
        raise ApiError(409, "self", "You can't remove your own admin role.")
    if u.is_superuser and body.role != ADMIN:
        raise ApiError(409, "superuser", "Superuser accounts stay admin.")
    _set_role(u, body.role)
    return _out(u)
