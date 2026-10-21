"""The render read API (020-FR-012, -013, -016): what a renderer app reads with a render token.

Bearer tokens only (created in Settings, spec 020); a session can't use these routes and a render token can't use
any other. Refusals say nothing about projects. No `from __future__ import annotations` here: see substation.api."""

import hashlib
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseNotModified
from django.utils import timezone
from ninja import Router, Schema
from ninja.security import HttpBearer

from substation.api import ApiError

from .models import ApiToken, FinishedFile, FinishedProject, TokenScope, hash_token
from .render import build, changed_at, files_url, offered, role_files
from .scan import SCAN_MAX_AGE_S, completed_libraries, scan_all

log = logging.getLogger("substation.render_api")


class RenderToken(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> ApiToken | None:
        tok = ApiToken.objects.filter(digest=hash_token(token or ""), scope=TokenScope.RENDER).first()
        if tok is None or not tok.active:
            log.info("render api refused: %s %s", request.method, request.path)
            return None
        now = timezone.now()
        if tok.last_used_at is None or (now - tok.last_used_at).total_seconds() > 60:
            ApiToken.objects.filter(pk=tok.pk).update(last_used_at=now)
        log.info("render api: token %r %s %s", tok.name, request.method, request.path)
        return tok


router = Router(auth=RenderToken(), tags=["render"])


class ProjectSummary(Schema):
    id: str
    name: str
    kind: str
    target: str
    common_name: str | None = None
    collection_ids: list[int] = []
    updated_at: datetime
    thumb_url: str


class ProjectsOut(Schema):
    projects: list[ProjectSummary]
    library_reachable: bool


def _aware(t: datetime | None) -> datetime | None:
    """A time without a zone is read as UTC, not a 500."""
    if t is not None and timezone.is_naive(t):
        return t.replace(tzinfo=UTC)
    return t


@router.get("/projects", response=ProjectsOut, exclude_none=True)
def list_projects(
    request: HttpRequest, since: datetime | None = None, kind: str | None = None
) -> ProjectsOut:
    results = scan_all(max_age_s=SCAN_MAX_AGE_S)
    reachable = all(r.reachable for r in results.values()) if results else bool(completed_libraries())
    since = _aware(since)
    qs = FinishedProject.objects.filter(missing=False).prefetch_related(
        "files", "linked_projects__collection"
    )
    if kind:
        qs = qs.filter(kind=kind)
    out: list[tuple[datetime, ProjectSummary]] = []
    for p in qs:
        ok, _ = offered(p)
        if not ok:
            continue
        changed = changed_at(p)
        if since and changed <= since:
            continue
        cols = sorted({lp.collection_id for lp in p.linked_projects.all()})
        names = [lp.collection.name for lp in p.linked_projects.all() if lp.collection]
        out.append(
            (
                changed,
                ProjectSummary(
                    id=str(p.pk),
                    name=p.name,
                    kind=p.kind,
                    target=p.subject,
                    common_name=names[0] if names and names[0] != p.subject else None,
                    collection_ids=cols,
                    updated_at=changed,
                    thumb_url=f"{files_url(p)}/thumb",
                ),
            )
        )
    out.sort(key=lambda x: x[0])
    log.info("render api: listed %d projects", len(out))
    return ProjectsOut(projects=[s for _, s in out], library_reachable=reachable)


def _project(id: str) -> FinishedProject:
    p = FinishedProject.objects.filter(pk=int(id) if id.isascii() and id.isdigit() else -1).first()
    if p is None or not offered(p)[0]:
        raise ApiError(404, "not_found", "No finished project with that id is offered.")
    return p


@router.get("/projects/{id}", response=dict[str, Any])
def get_project(request: HttpRequest, id: str) -> dict[str, Any]:
    return build(_project(id))


THUMB_PX = 640


def _fingerprint(f: FinishedFile) -> str:
    """A cheap content tag (path, size, time) instead of hashing a 360 MB TIFF inside a request."""
    return hashlib.sha256(f"{f.rel_path}|{f.size_bytes}|{f.mtime:.6f}".encode()).hexdigest()[:32]


def _to_rgb(im):  # noqa: ANN001, ANN202
    """16-bit and float images are scaled to 8 bits by their own range, not clipped."""
    if im.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        from PIL import ImageOps

        im = im.convert("F")
        lo, hi = im.getextrema()
        scale = 255.0 / (hi - lo) if hi > lo else 1.0
        im = im.point(lambda v: (v - lo) * scale).convert("L")
        return ImageOps.autocontrast(im).convert("RGB")
    return im.convert("RGB")


def _thumb(p: FinishedProject, src: Path, tag: str, px: int = THUMB_PX) -> Path:
    from django.conf import settings
    from PIL import Image, UnidentifiedImageError

    size = "" if px == THUMB_PX else f"-{px}"
    out = Path(settings.STATION_ROOT) / "cache" / "finished" / f"{p.pk}-{tag}{size}.jpg"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.tmp")
    try:
        with Image.open(src) as im:
            im.thumbnail((px, px))
            _to_rgb(im).save(tmp, "JPEG", quality=85)
        os.replace(tmp, out)
    except (OSError, UnidentifiedImageError, ValueError) as e:
        tmp.unlink(missing_ok=True)
        log.warning("render api: couldn't make a thumbnail of %s: %s", src.name, e)
        raise ApiError(404, "no_thumbnail", f"Couldn't make a thumbnail of {src.name}.") from e
    return out


def _inside(path: Path, folder: Path) -> bool:
    try:
        return path.resolve().is_relative_to(folder.resolve())
    except OSError:
        return False


@router.get("/projects/{id}/files/{path:key}", response={200: None, 304: None, 404: None})
def get_file(request: HttpRequest, id: str, key: str) -> HttpResponse | FileResponse:
    p = _project(id)
    want = "final" if key == "thumb" else key
    f = role_files(p).get(want)
    if f is None:
        raise ApiError(404, "no_file", "This project has no file with that role.")
    folder = Path(p.library.mount_path) / p.rel_path
    path = folder / f.rel_path
    if not path.is_file() or not _inside(path, folder):
        raise ApiError(404, "no_file", "That file is missing from the project folder.")
    tag = _fingerprint(f)
    etag = f'"{tag}{"-thumb" if key == "thumb" else ""}"'
    match = request.headers.get("If-None-Match", "")
    if etag in {t.strip().removeprefix("W/") for t in match.split(",")}:
        resp: HttpResponse = HttpResponseNotModified()
        resp["ETag"] = etag
        return resp
    if key == "thumb":
        path = _thumb(p, path, tag)
    out = FileResponse(path.open("rb"), filename=path.name)
    out["ETag"] = etag
    out["Cache-Control"] = "private, max-age=300"
    log.info("render api: served %s of project %s", key, p.pk)
    return out
