"""Your recent changes, and undoing them (spec 016)."""

from __future__ import annotations

from datetime import datetime

from django.shortcuts import get_object_or_404

from apps.accounts.roles import is_admin
from apps.catalogue.api import router
from apps.catalogue.models import Change
from apps.catalogue.services.changes import UNDO_FOR_DAYS, CantUndo, undo
from substation.api import ApiError, Schema


class ChangeOut(Schema):
    id: int
    kind: str
    summary: str
    count: int
    created_at: datetime
    undone_at: datetime | None
    by: str
    can_undo: bool


class UndoneOut(Schema):
    note: str
    change: ChangeOut


def _out(c: Change, request) -> ChangeOut:  # noqa: ANN001
    from django.utils import timezone

    mine = c.user_id == request.user.pk or is_admin(request.user)
    fresh = (timezone.now() - c.created_at).days <= UNDO_FOR_DAYS
    return ChangeOut(
        id=c.pk,
        kind=c.kind,
        summary=c.summary,
        count=c.count,
        created_at=c.created_at,
        undone_at=c.undone_at,
        by=c.user.get_username() if c.user else "",
        can_undo=mine and fresh and c.undone_at is None,
    )


@router.get("/changes", response=list[ChangeOut])
def list_changes(request, everyone: bool = False, limit: int = 20):
    """Your latest changes, newest first (everyone's, for an admin who asks)."""
    qs = Change.objects.select_related("user").order_by("-created_at", "-pk")
    if not (everyone and is_admin(request.user)):
        qs = qs.filter(user=request.user)
    return [_out(c, request) for c in qs[: max(1, min(limit, 100))]]


@router.post("/changes/{id}/undo", response=UndoneOut)
def undo_change(request, id: int):  # noqa: A002
    c = get_object_or_404(Change, pk=id)
    if c.user_id != request.user.pk and not is_admin(request.user):
        raise ApiError(403, "forbidden", "Only the person who made a change, or an admin, can undo it.")
    try:
        note = undo(c)
    except CantUndo as e:
        raise ApiError(409, "cant_undo", str(e)) from None
    c.refresh_from_db()
    return UndoneOut(note=note, change=_out(c, request))
