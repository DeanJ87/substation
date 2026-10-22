"""Finished projects and API tokens, for the owner (spec 020): list, link, file roles and step labels, distance,
rescan; create and revoke render tokens. SubStation never writes into a Completed library (020-DR-12). Session routes like the rest of the app; changes are admin-only.
No `from __future__ import annotations` here: see substation.api."""

import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from django.db import transaction
from django.http import FileResponse, HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.catalogue.models import Project
from substation.api import ApiError, Router, Schema, Status, admin_required

from .models import (
    ApiToken,
    FileRole,
    FinishedFile,
    FinishedProject,
    Progression,
    ProgressionState,
    TokenScope,
)
from .progression import availability as progression_availability
from .progression import reconcile_progressions
from .progression import start as start_progression
from .render import build, changed_at, file_key, offered
from .scan import IMAGE_EXTS, completed_libraries, guess_roles, scan_all

log = logging.getLogger("substation.finished")
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
    role_label: str
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
    files: list[FileOut]
    changed_at: datetime
    distance_ly: float | None
    distance_source: str
    path: str  # where the folder is, as the library's own path shows it
    change_id: int | None = None  # set when this answer made an undoable change (links)
    warnings: list[str] = []


class FinishedListOut(Schema):
    projects: list[FinishedOut]
    libraries: list[str]
    not_projects: list[list[str]]


def _out(p: FinishedProject) -> FinishedOut:
    ok, reason = offered(p)
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
                role_label=f.role_label,
                key=file_key(f) if f.role else None,
            )
            for f in p.files.all()
        ],
        changed_at=changed_at(p),
        distance_ly=p.distance_ly,
        distance_source=p.distance_source,
        path=f"{p.library.mount_path.rstrip('/')}/{p.rel_path}",
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


@router.get("/{id}", response=FinishedOut)
def get_finished(request: HttpRequest, id: int) -> FinishedOut:
    return _out(get_object_or_404(FinishedProject, pk=id))


PREVIEW_PX = 1600


@router.get("/{id}/files/{file_id}/image", response={200: None, 404: None})
def file_image(request: HttpRequest, id: int, file_id: int, size: str = "thumb") -> FileResponse:
    """A JPEG of one output file for the app: `thumb` for the grid, `preview` to look closer. Never the original,
    which can be a 300 MB TIFF."""
    from .api_render import THUMB_PX, _fingerprint, _inside, _thumb

    p = get_object_or_404(FinishedProject, pk=id)
    f = get_object_or_404(FinishedFile, pk=file_id, project=p)
    folder = Path(p.library.mount_path) / p.rel_path
    path = folder / f.rel_path
    if f.section == "project" or f.ext not in IMAGE_EXTS or not path.is_file() or not _inside(path, folder):
        raise ApiError(404, "no_file", "That file can't be shown.")
    out = _thumb(p, path, _fingerprint(f), PREVIEW_PX if size == "preview" else THUMB_PX)
    resp = FileResponse(out.open("rb"), content_type="image/jpeg")
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


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
    """SubStation projects to link (020-FR-004): only those sharing a catalogue number or the name; the year only
    ranks them. TODO(020 T018): add plate-solve field overlap once finished images are solved."""
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
        if not score:  # a shared year alone is no reason to link (020-DR-14 review)
            continue
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
    return out[:5]


class LinkIn(Schema):
    project_ids: list[int]


@router.put("/{id}/links", response=FinishedOut)
@admin_required
def set_links(request: HttpRequest, id: int, body: LinkIn) -> FinishedOut:
    from apps.catalogue.models import Change
    from apps.catalogue.services.changes import record

    p = get_object_or_404(FinishedProject, pk=id)
    projects = list(Project.objects.filter(pk__in=body.project_ids))
    if len(projects) != len(set(body.project_ids)):
        raise ApiError(400, "unknown_project", "One of those SubStation projects doesn't exist.")
    before = sorted(p.linked_projects.values_list("pk", flat=True))
    after = sorted(q.pk for q in projects)
    warnings: list[str] = []
    change = None
    with transaction.atomic():
        p.linked_projects.set(projects)
        p.save(update_fields=["updated_at"])
        if before != after:
            if p.kind == "astro" and before and not after:
                warnings.append("No longer offered to the renderer.")
            n = len(after)
            summary = f"Linked {p.name} to {n} project{'s' if n != 1 else ''}" if n else f"Unlinked {p.name}"
            change = record(
                request.user,
                Change.Kind.LINK,
                summary,
                len(set(before) ^ set(after)),
                finished_id=p.pk,
                before=before,
                after=after,
            )
    if projects:  # 020-DR-15: build the cumulative stacks when nothing needs calibrating again
        try:
            start_progression(p, auto=True)
        except Exception:  # noqa: BLE001 (linking must never fail on it)
            log.exception("Couldn't start the progression of finished project %s", p.pk)
    out = _out(p)
    out.change_id = change.pk if change is not None else None
    out.warnings = warnings
    return out


class RoleIn(Schema):
    file_id: int
    role: str  # "", final, starless, stars, per_filter, progressive, step
    role_filter: str = ""
    role_order: int | None = None
    role_label: str = ""


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
            ordered = r.role in (FileRole.PROGRESSIVE, FileRole.STEP)
            if ordered and (not r.role_order or r.role_order < 1):
                raise ApiError(400, "needs_order", "Give it a position: 1, 2, 3 …")
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
            f.role_order = r.role_order if ordered else None
            f.role_label = r.role_label.strip()[:100] if r.role == FileRole.STEP else ""
            f.role_set_by_owner = True
            f.save(update_fields=["role", "role_filter", "role_order", "role_label", "role_set_by_owner"])
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


class DistanceIn(Schema):
    distance_ly: float | None  # None clears it


@router.put("/{id}/distance", response=FinishedOut)
@admin_required
def set_distance(request: HttpRequest, id: int, body: DistanceIn) -> FinishedOut:
    """The owner's own figure (020-DR-13); it wins over a look-up until cleared."""
    p = get_object_or_404(FinishedProject, pk=id)
    if body.distance_ly is not None and not 0 < body.distance_ly < 2e10:
        raise ApiError(400, "bad_distance", "A distance is a positive number of light years.")
    p.distance_ly = body.distance_ly
    p.distance_source = "manual" if body.distance_ly is not None else ""
    p.save(update_fields=["distance_ly", "distance_source", "updated_at"])
    return _out(p)


def _designations(p: FinishedProject) -> list[str]:
    names: list[str] = []
    for lp in p.linked_projects.select_related("collection"):
        names += [n.strip() for n in lp.collection.objects_text.split("·") if n.strip()]
        names.append(lp.collection.name)
    names += [p.subject]
    catalogued = [n for n in names if _catalogue_ids(n)]
    return list(dict.fromkeys(catalogued + names))[:8]


@router.post("/{id}/distance/lookup", response=FinishedOut)
@admin_required
def lookup_distance(request: HttpRequest, id: int) -> FinishedOut:
    """Ask SIMBAD (020-DR-13). Never replaces a figure the owner typed."""
    from .distance import LookupFailed, lookup

    p = get_object_or_404(FinishedProject, pk=id)
    if p.distance_source == "manual":
        raise ApiError(409, "manual", "You've set this distance yourself; clear it first to look it up.")
    try:
        found = lookup(_designations(p))
    except LookupFailed as e:
        raise ApiError(502, "unreachable", str(e)) from e
    if found is None:
        raise ApiError(404, "not_found", "SIMBAD has no distance for this target. Type it in instead.")
    p.distance_ly, p.distance_source = round(found[0]), found[1][:200]
    p.save(update_fields=["distance_ly", "distance_source", "updated_at"])
    return _out(p)


# -- cumulative progressive stacks (020-DR-15) ---------------------------------------------------------------


class CheckpointOut(Schema):
    order: int
    nights: list[str]
    label: str
    integration_s: float
    subs: int
    filters: dict[str, dict[str, float]]
    image_url: str


class ProgressionOut(Schema):
    state: str
    step: str
    progress: float
    reason: str
    mapping: str
    built_at: datetime | None
    checkpoints: list[CheckpointOut]


class ProgressionIn(Schema):
    force: bool = False


def _progression_out(p: FinishedProject, prog: Progression | None) -> ProgressionOut:
    if prog is None:
        return ProgressionOut(
            state=ProgressionState.NONE,
            step="",
            progress=0,
            reason=progression_availability(p),
            mapping="",
            built_at=None,
            checkpoints=[],
        )
    return ProgressionOut(
        state=prog.state,
        step=prog.step,
        progress=prog.progress,
        reason=prog.reason,
        mapping=prog.mapping,
        built_at=prog.finished_at,
        checkpoints=[
            CheckpointOut(
                order=ck["order"],
                nights=ck.get("nights") or [],
                label=ck.get("label") or "",
                integration_s=ck.get("integration_s") or 0,
                subs=ck.get("subs") or 0,
                filters=ck.get("filters") or {},
                image_url=f"/api/v1/finished/{p.pk}/progression/{ck['order']}/image",
            )
            for ck in prog.checkpoints
        ],
    )


@router.get("/{id}/progression", response=ProgressionOut)
def get_progression(request: HttpRequest, id: int) -> ProgressionOut:
    p = get_object_or_404(FinishedProject, pk=id)
    reconcile_progressions()
    return _progression_out(p, Progression.objects.filter(project=p).first())


@router.post("/{id}/progression", response=ProgressionOut)
@admin_required
def generate_progression(request: HttpRequest, id: int, body: ProgressionIn) -> ProgressionOut:
    """Build the cumulative stacks (the Generate progression button); `force` rebuilds even when cached."""
    p = get_object_or_404(FinishedProject, pk=id)
    prog = start_progression(p, force=body.force)
    if prog.state == ProgressionState.UNAVAILABLE:
        raise ApiError(409, "unavailable", prog.reason)
    return _progression_out(p, prog)


@router.get("/{id}/progression/{order}/image", response={200: None, 404: None})
def progression_image(request: HttpRequest, id: int, order: str) -> FileResponse:
    from .api_render import progression_checkpoint

    p = get_object_or_404(FinishedProject, pk=id)
    found = progression_checkpoint(p, order)
    if found is None:
        raise ApiError(404, "no_file", "There's no progression image with that number.")
    ck, path = found
    resp = FileResponse(path.open("rb"), content_type="image/jpeg")
    resp["ETag"] = f'"{ck["hash"][:32]}"'
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


@router.get("/{id}/render-data", response=dict)
def render_data_preview(request: HttpRequest, id: int) -> dict:
    """What the renderer would get, for checking in the app."""
    p = get_object_or_404(FinishedProject, pk=id)
    if p.kind == "astro" and not p.linked_projects.exists():
        raise ApiError(409, "not_linked", "Link this project to a SubStation project first.")
    return build(p)


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
