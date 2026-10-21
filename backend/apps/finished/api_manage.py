"""Finished projects and API tokens, for the owner (spec 020): list, link, file roles, processing, rescan,
project.json; create and revoke render tokens. Session routes like the rest of the app; changes are admin-only.
No `from __future__ import annotations` here: see substation.api."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.catalogue.models import Project
from apps.libraries.models import InstallationSettings
from substation.api import ApiError, Router, Schema, Status, admin_required

from .models import ApiToken, FileRole, FinishedFile, FinishedProject, TokenScope
from .render import build, changed_at, file_key, offered
from .scan import IMAGE_EXTS, completed_libraries, guess_roles, scan_all

router = Router(tags=["finished"])
tokens_router = Router(tags=["tokens"])


class FileOut(Schema):
    id: int
    rel_path: str
    section: str
    size_bytes: int
    missing: bool
    servable: bool
    role: str
    role_filter: str
    role_order: int | None
    key: str | None


class LinkOut(Schema):
    project_id: int
    project_name: str
    collection_id: int
    collection_name: str


class FinishedOut(Schema):
    id: int
    library: str
    rel_path: str
    kind: str
    subject: str
    name: str
    missing: bool
    offered: bool
    reason: str
    links: list[LinkOut]
    processing: list[str]
    files: list[FileOut]
    changed_at: datetime
    can_write_project_json: bool
    project_json_reason: str


class FinishedListOut(Schema):
    projects: list[FinishedOut]
    libraries: list[str]
    not_projects: list[list[str]]


def _write_state(p: FinishedProject) -> tuple[bool, str]:
    from apps.libraries.access import is_writable, read_only_reason

    if is_writable(p.library):
        return True, ""
    return False, read_only_reason(p.library) or "This library is mounted read-only."


def _out(p: FinishedProject) -> FinishedOut:
    ok, reason = offered(p)
    w_ok, w_reason = _write_state(p)
    return FinishedOut(
        id=p.pk,
        library=p.library.name,
        rel_path=p.rel_path,
        kind=p.kind,
        subject=p.subject,
        name=p.name,
        missing=p.missing,
        offered=ok,
        reason=reason,
        links=[
            LinkOut(
                project_id=lp.pk,
                project_name=lp.name,
                collection_id=lp.collection_id,
                collection_name=lp.collection.name,
            )
            for lp in p.linked_projects.select_related("collection")
        ],
        processing=list(p.processing or []),
        files=[
            FileOut(
                id=f.pk,
                rel_path=f.rel_path,
                section=f.section,
                size_bytes=f.size_bytes,
                missing=f.missing,
                servable=f.ext in IMAGE_EXTS and f.section != "project",
                role=f.role,
                role_filter=f.role_filter,
                role_order=f.role_order,
                key=file_key(f) if f.role else None,
            )
            for f in p.files.all()
        ],
        changed_at=changed_at(p),
        can_write_project_json=w_ok,
        project_json_reason=w_reason,
    )


@router.get("", response=FinishedListOut)
def list_finished(request: HttpRequest, rescan: bool = False) -> FinishedListOut:
    results = scan_all(max_age_s=None if rescan else 300)
    not_projects = [[path, reason] for r in results.values() for path, reason in r.not_projects]
    qs = FinishedProject.objects.select_related("library").prefetch_related(
        "files", "linked_projects__collection"
    )
    return FinishedListOut(
        projects=[_out(p) for p in qs],
        libraries=[lib.name for lib in completed_libraries()],
        not_projects=not_projects,
    )


class DefaultsIn(Schema):
    steps: list[str]


@router.put("/defaults/processing", response=list[str])
@admin_required
def set_default_processing(request: HttpRequest, body: DefaultsIn) -> list[str]:
    s = InstallationSettings.load()
    s.default_processing = [x.strip()[:60] for x in body.steps if x.strip()][:30]
    s.save(update_fields=["default_processing"])
    return s.default_processing


@router.get("/{id}", response=FinishedOut)
def get_finished(request: HttpRequest, id: int) -> FinishedOut:
    return _out(get_object_or_404(FinishedProject, pk=id))


class SuggestionOut(Schema):
    project_id: int
    project_name: str
    collection_id: int
    collection_name: str
    score: float
    reasons: list[str]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _catalogue_ids(s: str) -> set[str]:
    """'IC 1805', 'ic1805', 'NGC7000' → {'ic1805'}; also Sh2-129 and M 42."""
    return {
        (m.group(1) + m.group(2)).lower()
        for m in re.finditer(r"\b(ngc|ic|m|sh2-?|vdb|ldn|lbn|b|c|abell|arp)\s*-?\s*(\d+)\b", s, re.I)
    }


@router.get("/{id}/suggestions", response=list[SuggestionOut])
def suggestions(request: HttpRequest, id: int) -> list[SuggestionOut]:
    """Ranked SubStation projects to link (020-FR-004): catalogue numbers and names in common.
    TODO(020 T018): add plate-solve field overlap once finished images are solved."""
    p = get_object_or_404(FinishedProject, pk=id)
    words = f"{p.subject} {p.name}"
    ids, norm = _catalogue_ids(words), _norm(words)
    out: list[SuggestionOut] = []
    for proj in Project.objects.select_related("collection"):
        col = proj.collection
        text = f"{col.name} {col.objects_text} {proj.name}"
        score, reasons = 0.0, []
        common = ids & _catalogue_ids(text)
        if common:
            score += 2
            reasons.append("same target (" + ", ".join(sorted(c.upper() for c in common)) + ")")
        n = _norm(col.name)
        if n and (n in norm or norm in n):
            score += 1
            reasons.append("same name")
        years = set(re.findall(r"\b(20\d\d)\b", p.name))
        if years and any(y in proj.name for y in years):
            score += 0.5
            reasons.append("same year")
        if score:
            out.append(
                SuggestionOut(
                    project_id=proj.pk,
                    project_name=proj.name,
                    collection_id=col.pk,
                    collection_name=col.name,
                    score=score,
                    reasons=reasons,
                )
            )
    out.sort(key=lambda s: -s.score)
    return out[:10]


class LinkIn(Schema):
    project_ids: list[int]


@router.put("/{id}/links", response=FinishedOut)
@admin_required
def set_links(request: HttpRequest, id: int, body: LinkIn) -> FinishedOut:
    p = get_object_or_404(FinishedProject, pk=id)
    projects = list(Project.objects.filter(pk__in=body.project_ids))
    if len(projects) != len(set(body.project_ids)):
        raise ApiError(400, "unknown_project", "One of those SubStation projects doesn't exist.")
    p.linked_projects.set(projects)
    p.save(update_fields=["updated_at"])
    return _out(p)


class RoleIn(Schema):
    file_id: int
    role: str  # "", final, starless, stars, per_filter, progressive
    role_filter: str = ""
    role_order: int | None = None


class RolesIn(Schema):
    roles: list[RoleIn]


@router.put("/{id}/roles", response=FinishedOut)
@admin_required
def set_roles(request: HttpRequest, id: int, body: RolesIn) -> FinishedOut:
    p = get_object_or_404(FinishedProject, pk=id)
    valid = {c.value for c in FileRole}
    with transaction.atomic():
        for r in body.roles:
            if r.role not in valid:
                raise ApiError(400, "bad_role", f"“{r.role}” isn't a file role.")
            if r.role == FileRole.PER_FILTER and not r.role_filter:
                raise ApiError(400, "needs_filter", "A single-filter image needs its filter.")
            if r.role == FileRole.PROGRESSIVE and not r.role_order:
                raise ApiError(400, "needs_order", "A progressive stack needs its position (1, 2, 3 …).")
            if r.role == FileRole.PROGRESSIVE and r.role_order is not None and r.role_order < 1:
                raise ApiError(400, "needs_order", "A progressive stack's position starts at 1.")
            f = get_object_or_404(FinishedFile, pk=r.file_id, project=p)
            if r.role and (f.missing or f.section == "project" or f.ext not in IMAGE_EXTS):
                raise ApiError(
                    400,
                    "not_servable",
                    f"{f.rel_path} can't have a role: only PNG, JPEG or TIFF outputs can.",
                )
            if r.role in (FileRole.FINAL, FileRole.STARLESS, FileRole.STARS):  # one file per single role
                p.files.filter(role=r.role).exclude(pk=f.pk).update(role="")
            f.role = r.role
            f.role_filter = r.role_filter if r.role == FileRole.PER_FILTER else ""
            f.role_order = r.role_order if r.role == FileRole.PROGRESSIVE else None
            f.role_set_by_owner = True
            f.save(update_fields=["role", "role_filter", "role_order", "role_set_by_owner"])
        p.save(update_fields=["updated_at"])
    return _out(p)


@router.post("/{id}/roles/guess", response=FinishedOut)
@admin_required
def reguess_roles(request: HttpRequest, id: int) -> FinishedOut:
    p = get_object_or_404(FinishedProject, pk=id)
    p.files.update(role_set_by_owner=False)
    guess_roles(p)
    p.save(update_fields=["updated_at"])
    return _out(p)


class ProcessingIn(Schema):
    steps: list[str]


@router.put("/{id}/processing", response=FinishedOut)
@admin_required
def set_processing(request: HttpRequest, id: int, body: ProcessingIn) -> FinishedOut:
    p = get_object_or_404(FinishedProject, pk=id)
    p.processing = [s.strip()[:60] for s in body.steps if s.strip()][:30]
    p.save(update_fields=["processing", "updated_at"])
    return _out(p)


@router.get("/{id}/render-data", response=dict)
def render_data_preview(request: HttpRequest, id: int) -> dict:
    """What the renderer would get, for checking in the app."""
    p = get_object_or_404(FinishedProject, pk=id)
    if not p.linked_projects.exists():
        raise ApiError(409, "not_linked", "Link this project to a SubStation project first.")
    return build(p)


@router.post("/{id}/project-json", response=FinishedOut)
@admin_required
def write_project_json(request: HttpRequest, id: int) -> FinishedOut:
    """020-FR-014: only in a read-write library; never over a project.json SubStation didn't write."""
    p = get_object_or_404(FinishedProject, pk=id)
    ok, reason = _write_state(p)
    if not ok:
        raise ApiError(409, "read_only", reason or "This library is mounted read-only.")
    if not p.linked_projects.exists():
        raise ApiError(409, "not_linked", "Link this project to a SubStation project first.")
    target = Path(p.library.mount_path) / p.rel_path / "project.json"
    if target.exists():
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        if current != p.wrote_project_json_sha256:
            raise ApiError(
                409,
                "not_ours",
                "There's a project.json here that SubStation didn't write; it won't overwrite it.",
            )
    data = build(p)
    body = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    target.write_bytes(body)  # only project.json is ever written there (020-FR-014)
    p.wrote_project_json_sha256 = hashlib.sha256(body).hexdigest()
    p.save(update_fields=["wrote_project_json_sha256", "updated_at"])
    return _out(p)


# -- API tokens (020-FR-011) -------------------------------------------------------------------------------


class TokenOut(Schema):
    id: int
    name: str
    scope: str
    hint: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    active: bool


class TokenIn(Schema):
    name: str
    expires_at: datetime | None = None


class TokenCreatedOut(Schema):
    token: TokenOut
    secret: str  # shown once


def _tok(t: ApiToken) -> TokenOut:
    return TokenOut(
        id=t.pk,
        name=t.name,
        scope=t.scope,
        hint=t.hint,
        created_at=t.created_at,
        expires_at=t.expires_at,
        last_used_at=t.last_used_at,
        revoked_at=t.revoked_at,
        active=t.active,
    )


@tokens_router.get("", response=list[TokenOut])
@admin_required
def list_tokens(request: HttpRequest) -> list[TokenOut]:
    return [_tok(t) for t in ApiToken.objects.all()]


@tokens_router.post("", response={201: TokenCreatedOut})
@admin_required
def create_token(request: HttpRequest, body: TokenIn) -> Status:
    name = body.name.strip()
    if not name:
        raise ApiError(400, "needs_name", "Give the token a name, e.g. “dean0 render”.")
    expires = body.expires_at
    if expires is not None and timezone.is_naive(expires):
        expires = expires.replace(tzinfo=UTC)
    if expires and expires <= timezone.now():
        raise ApiError(400, "expired", "The expiry date is in the past.")
    tok, raw = ApiToken.issue(name[:100], TokenScope.RENDER, request.user, expires)
    return Status(201, TokenCreatedOut(token=_tok(tok), secret=raw))


@tokens_router.post("/{id}/revoke", response=TokenOut)
@admin_required
def revoke_token(request: HttpRequest, id: int) -> TokenOut:
    t = get_object_or_404(ApiToken, pk=id)
    if t.revoked_at is None:
        t.revoked_at = timezone.now()
        t.save(update_fields=["revoked_at"])
    return _tok(t)
