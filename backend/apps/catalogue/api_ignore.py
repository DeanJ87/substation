"""Ignore rule endpoints (T091; contracts/openapi.yaml). Any signed-in user may ignore: it is their call about
their data, like a verdict. No `from __future__ import annotations` here: see substation.api."""

import re
from datetime import datetime
from typing import Literal

from django.shortcuts import get_object_or_404

from apps.libraries.models import Library
from substation.api import ApiError, Schema, Status
from substation.tasks import enqueue

from .api import router
from .models import Frame, IgnoreKind, IgnoreRule
from .services.ignore import frames_for_rule, matching_files

SHA = re.compile(r"^[0-9a-f]{64}$")


class IgnoreRuleIn(Schema):
    kind: Literal["folder", "glob", "content"]
    library_id: int | None = None
    value: str
    note: str | None = None


class IgnoreRuleOut(IgnoreRuleIn):
    id: int
    active: bool
    created_by: str | None
    created_at: datetime
    matches: int


def _out(r: IgnoreRule) -> IgnoreRuleOut:
    return IgnoreRuleOut(
        id=r.pk,
        kind=r.kind,  # type: ignore[arg-type]
        library_id=r.library_id,
        value=r.value,
        note=r.note,
        active=r.active,  # type: ignore[arg-type]
        created_by=r.created_by.get_username() if r.created_by else None,
        created_at=r.created_at,
        matches=matching_files(r),
    )


def _apply(rule: IgnoreRule, undone: bool) -> None:
    from apps.ingest.tasks.ignore import apply_ignore

    shas = [f.sha256 for f in frames_for_rule(rule)]
    enqueue(apply_ignore, shas, rule.kind, rule.library_id, undone)


@router.get("/ignore-rules", response=list[IgnoreRuleOut])
def list_ignore_rules(
    request, limit: int = 0, offset: int = 0, sort: Literal["newest", "kind", "files"] = "newest"
):
    """Active rules, a page at a time when `limit` is given; counting a rule's files is the slow part, so only the
    page's rules are counted (except when sorting by files)."""
    qs = IgnoreRule.objects.filter(active=True).select_related("created_by")
    if sort == "files":
        rows = sorted((_out(r) for r in qs), key=lambda r: -r.matches)
        return rows[offset : offset + limit] if limit else rows[offset:]
    qs = qs.order_by("kind", "-created_at") if sort == "kind" else qs.order_by("-created_at")
    page = qs[offset : offset + limit] if limit else qs[offset:]
    return [_out(r) for r in page]


@router.post("/ignore-rules", response={201: IgnoreRuleOut})
def create_ignore_rule(request, body: IgnoreRuleIn):
    value = body.value.strip()
    if body.kind == IgnoreKind.CONTENT:
        if not SHA.match(value):
            raise ApiError(422, "invalid", "Give the sub's SHA-256.")
        if not Frame.objects.filter(pk=value).exists():
            raise ApiError(422, "invalid", "No sub with that hash.")
    else:
        value = value.strip("/") if body.kind == IgnoreKind.FOLDER else value
        if not value:
            raise ApiError(
                422, "invalid", "Give a folder or file name. To ignore a whole library, turn it off."
            )
    if body.library_id is not None and not Library.objects.filter(pk=body.library_id).exists():
        raise ApiError(422, "invalid", "That library doesn't exist.")
    same = IgnoreRule.objects.filter(active=True, kind=body.kind, value=value)
    same = (
        same.filter(library__isnull=True)
        if body.library_id is None
        else same.filter(library_id=body.library_id)
    )
    existing = same.first()
    if existing is not None:
        return Status(201, _out(existing))
    rule = IgnoreRule.objects.create(
        kind=body.kind, value=value, library_id=body.library_id, note=body.note, created_by=request.user
    )
    _apply(rule, undone=False)
    if (
        body.kind == IgnoreKind.CONTENT
        and Frame.objects.filter(pk=value, frame_type__startswith="master_").exists()
    ):
        # a retired master (002 C13): lights that used it find another, or wait with the reason
        from apps.processing.tasks import rematch_lights

        enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True)
    return Status(201, _out(rule))


@router.delete("/ignore-rules/{id}", response={204: None})
def delete_ignore_rule(request, id: int):  # noqa: A002
    rule = get_object_or_404(IgnoreRule, pk=id)
    frames_before = frames_for_rule(rule)
    rule.delete()
    from apps.ingest.tasks.ignore import apply_ignore

    enqueue(apply_ignore, [f.sha256 for f in frames_before], rule.kind, rule.library_id, True)
    if any(
        f.frame_type.startswith("master_") for f in frames_before
    ):  # an un-retired master is matched again
        from apps.processing.tasks import rematch_lights

        enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True)
    return Status(204, None)
