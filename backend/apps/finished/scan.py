"""Find finished projects in Completed libraries (020-FR-001..003, -005).

Read-only: a stat-only walk of `<kind>/<subject>/<name>/{exports,web,social,project}/`. Files are tracked by path,
size and modification time here; their content hash is filled in when first served (render.py), so a scan of a
folder of 60 MP TIFFs stays cheap. Folders that don't fit the layout are reported, never guessed into a project."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.libraries.models import InstallationSettings, Library, LibraryRole

from .models import KIND_FOLDERS, SECTIONS, FileRole, FinishedFile, FinishedProject

log = logging.getLogger(__name__)

IMAGE_EXTS = {"png", "jpg", "jpeg", "tif", "tiff"}  # what the render API may serve (020-FR-013)
SCAN_MAX_AGE_S = 300  # 020-SC-001: a list call rescans a library that hasn't been scanned for 5 minutes
_last_scan: dict[int, float] = {}


@dataclass
class ScanResult:
    projects: int = 0
    files: int = 0
    not_projects: list[tuple[str, str]] = field(default_factory=list)  # (path, reason)
    reachable: bool = True


def completed_libraries() -> list[Library]:
    return list(Library.objects.filter(role=LibraryRole.COMPLETED, enabled=True))


def _entries(path: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(path) as it:
            return sorted((e for e in it if not e.name.startswith((".", "@", "#"))), key=lambda e: e.name)
    except OSError:
        return []


def _walk_files(root: Path) -> list[tuple[str, int, float]]:
    out: list[tuple[str, int, float]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if not d.startswith((".", "@", "#")) and not d.endswith(".pxiproject")
        ]
        for fn in filenames:
            if fn.startswith(".") or fn in {"Thumbs.db", "desktop.ini"}:
                continue
            p = Path(dirpath) / fn
            try:
                st = p.stat()
            except OSError:
                continue
            out.append((str(p.relative_to(root.parent)), st.st_size, st.st_mtime))
    return out


def scan_library(lib: Library) -> ScanResult:
    res = ScanResult()
    root = Path(lib.mount_path)
    if not root.is_dir() or not _entries(
        root
    ):  # a dropped share leaves an empty mount point: keep what we know
        res.reachable = False
        return res
    seen: set[str] = set()
    for kind_dir in _entries(root):
        if not kind_dir.is_dir():
            continue
        kind = KIND_FOLDERS.get(kind_dir.name.lower())
        if kind is None:
            res.not_projects.append((kind_dir.name, "not Astro, Nightscapes or Videos"))
            continue
        for subject_dir in _entries(Path(kind_dir.path)):
            if not subject_dir.is_dir():
                continue
            for proj_dir in _entries(Path(subject_dir.path)):
                if not proj_dir.is_dir():
                    continue
                rel = f"{kind_dir.name}/{subject_dir.name}/{proj_dir.name}"
                if not any(Path(proj_dir.path, s).is_dir() for s in SECTIONS):
                    res.not_projects.append((rel, "no exports, web, social or project folder"))
                    continue
                seen.add(rel)
                res.files += _sync_project(
                    lib, rel, kind, subject_dir.name, proj_dir.name, Path(proj_dir.path)
                )
                res.projects += 1
    FinishedProject.objects.filter(library=lib).exclude(rel_path__in=seen).update(missing=True)
    _last_scan[lib.pk] = timezone.now().timestamp()
    return res


@transaction.atomic
def _sync_project(lib: Library, rel: str, kind: str, subject: str, name: str, path: Path) -> int:
    proj, created = FinishedProject.objects.get_or_create(
        library=lib,
        rel_path=rel,
        defaults={
            "kind": kind,
            "subject": subject,
            "name": name,
            "processing": list(InstallationSettings.load().default_processing or []),
        },
    )
    if proj.missing:
        proj.missing = False
        proj.save(update_fields=["missing", "updated_at"])
    files: list[tuple[str, int, float]] = []
    for section in SECTIONS:
        sec = path / section
        if sec.is_dir():
            files += _walk_files(sec)  # paths relative to the project folder: "exports/heart-final.png"
    existing = {f.rel_path: f for f in proj.files.all()}
    newest = proj.files_changed_at.timestamp() if proj.files_changed_at else 0.0
    changed = False
    present: set[str] = set()
    for rel_file, size, mtime in files:
        present.add(rel_file)
        section = rel_file.split("/", 1)[0]
        f = existing.get(rel_file)
        if f is None:
            FinishedFile.objects.create(
                project=proj, rel_path=rel_file, section=section, size_bytes=size, mtime=mtime
            )
            changed = True
        elif f.size_bytes != size or abs(f.mtime - mtime) > 1e-3 or f.missing:
            f.size_bytes, f.mtime, f.missing, f.sha256 = size, mtime, False, ""
            f.save(update_fields=["size_bytes", "mtime", "missing", "sha256"])
            changed = True
        newest = max(newest, min(mtime, timezone.now().timestamp()))
    gone = [f for p, f in existing.items() if p not in present and not f.missing]
    for f in gone:
        f.missing = True
        f.save(update_fields=["missing"])
        changed = True
    _carry_roles(proj, gone)
    if changed:
        proj.files_changed_at = datetime.fromtimestamp(newest, tz=UTC) if newest else timezone.now()
        proj.save(update_fields=["files_changed_at", "updated_at"])
    if created or changed:
        guess_roles(proj)
    return len(files)


def _carry_roles(proj: FinishedProject, gone: list[FinishedFile]) -> None:
    """A renamed or moved export keeps its role (020-FR-003): the new file with the same size and time inherits it."""
    for old in gone:
        if not old.role:
            continue
        twin = (
            proj.files.filter(missing=False, size_bytes=old.size_bytes, role="")
            .exclude(pk=old.pk)
            .order_by("pk")
        )
        new = next((f for f in twin if abs(f.mtime - old.mtime) < 1e-3), None)
        if new is None:
            continue
        new.role, new.role_filter, new.role_order = old.role, old.role_filter, old.role_order
        new.role_set_by_owner = old.role_set_by_owner
        new.save(update_fields=["role", "role_filter", "role_order", "role_set_by_owner"])
        old.role, old.role_filter, old.role_order = "", "", None
        old.save(update_fields=["role", "role_filter", "role_order"])


_ROLE_PATTERNS = (
    (FileRole.STARLESS, re.compile(r"(^|[-_ .])(starless|nostars|no[-_ ]stars)([-_ .]|$)", re.I)),
    (FileRole.STARS, re.compile(r"(^|[-_ .])(stars|stars[-_ ]?only|starmask)([-_ .]|$)", re.I)),
    (FileRole.FINAL, re.compile(r"(^|[-_ .])(final)([-_ .]|$)", re.I)),
)
_PROGRESSIVE = re.compile(r"(?:progress(?:ive)?|stack)[-_ ]?(\d{1,3})(?!\d)", re.I)


def _filter_names() -> list[str]:
    from apps.catalogue.models import Dataset

    names = {n for n in Dataset.objects.values_list("filter_norm", flat=True).distinct() if n}
    return sorted(names, key=len, reverse=True)


def _per_filter(stem: str, names: list[str]) -> str | None:
    tokens = [t for t in re.split(r"[-_ .]+", stem) if t]
    low = {t.lower() for t in tokens}
    aliases = {"ha": "Hα", "halpha": "Hα", "h-alpha": "Hα", "o3": "OIII", "s2": "SII"}
    for t in tokens:
        if t.lower() in aliases and aliases[t.lower()] in names:
            return aliases[t.lower()]
    for n in names:
        if n.lower() in low:
            return n
    return None


def _role_for(stem: str, names: list[str]) -> tuple[str, str, int | None]:
    """(role, filter, order) from a file name: final/starless/stars, then progressive stacks, then a filter."""
    for r, pat in _ROLE_PATTERNS:
        if pat.search(stem):
            return r, "", None
    m = _PROGRESSIVE.search(stem)
    if m:
        return FileRole.PROGRESSIVE, "", int(m.group(1))
    n = _per_filter(stem, names)
    return (FileRole.PER_FILTER, n, None) if n else ("", "", None)


def _one_final(files: list[FinishedFile]) -> None:
    """Exactly one final where possible: the only unroled export, or the newest of several finals."""
    finals = [f for f in files if f.role == FileRole.FINAL]
    if not finals:
        unroled = [f for f in files if not f.role and f.section == "exports"]
        if len(unroled) == 1:
            unroled[0].role = FileRole.FINAL
            unroled[0].save(update_fields=["role"])
        return
    keep = max(finals, key=lambda f: f.mtime)  # several (versions, crops): the owner can change it
    for f in finals:
        if f.pk != keep.pk:
            f.role = ""
            f.save(update_fields=["role"])


def guess_roles(proj: FinishedProject) -> None:
    """Pre-select roles from file names (020-FR-005). Never overrides a role the owner set."""
    files = [f for f in proj.files.filter(missing=False) if f.ext in IMAGE_EXTS and f.section != "project"]
    if not files or proj.files.filter(role_set_by_owner=True).exists():
        return
    names = _filter_names()
    for f in files:
        role, flt, order = _role_for(Path(f.rel_path).stem, names)
        if role == FileRole.FINAL and f.section != "exports":  # web and social crops are never the final
            role = ""
        if (f.role, f.role_filter, f.role_order) != (role, flt, order):
            f.role, f.role_filter, f.role_order = role, flt, order
            f.save(update_fields=["role", "role_filter", "role_order"])
    _one_final(files)


def scan_all(max_age_s: float | None = None) -> dict[int, ScanResult]:
    """Scan every Completed library, or only those not scanned for `max_age_s` seconds."""
    out: dict[int, ScanResult] = {}
    now = timezone.now().timestamp()
    for lib in completed_libraries():
        if max_age_s is not None and now - _last_scan.get(lib.pk, 0) < max_age_s:
            continue
        try:
            out[lib.pk] = scan_library(lib)
        except OSError as e:
            log.warning("Couldn't scan Completed library %s: %s", lib.name, e)
            out[lib.pk] = ScanResult(reachable=False)
    return out
