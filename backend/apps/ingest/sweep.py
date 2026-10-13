"""Library sweep (research R4; T050): walk with scandir, path-check every file, batch the last-seen updates.

A sweep is the reliable change detector (network shares do not deliver inotify events). Disappearances
are handled at the end of a complete sweep (US2, T065).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from django.utils import timezone

from apps.catalogue.models import Copy
from apps.catalogue.services.ignore import PathRules
from apps.catalogue.services.tracking import mark_copies_missing, mark_frames_missing
from apps.libraries.discovery import is_reachable
from apps.libraries.models import Library, LibraryStatus
from substation.events.emit import emit

from .pathcheck import Action, check_path, skip_dir

log = logging.getLogger(__name__)
BATCH = 500


@dataclass
class SweepResult:
    library: str
    files: int = 0
    queued: int = 0
    unchanged: int = 0
    skipped: int = 0
    moved: int = 0
    ignored: int = 0
    missing: int = 0
    unreadable_dirs: int = 0
    complete: bool = False
    seen_paths: set[str] = field(default_factory=set)


def walk(root: Path, result: SweepResult | None = None):  # -> Iterator[tuple[str, os.stat_result]]
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError as exc:
            log.warning("Could not list %s: %s", current, exc)
            if result is not None:
                result.unreadable_dirs += 1
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if not skip_dir(e.name):
                        stack.append(Path(e.path))
                elif e.is_file(follow_symlinks=False):
                    yield os.path.relpath(e.path, root), e.stat(follow_symlinks=False)
            except OSError:
                continue


def sweep_library(lib: Library) -> SweepResult:
    root = Path(lib.mount_path)
    result = SweepResult(library=lib.name)
    if not is_reachable(root):
        Library.objects.filter(pk=lib.pk).update(status=LibraryStatus.UNREACHABLE)
        emit("library.status", {"library_id": lib.pk, "status": LibraryStatus.UNREACHABLE})
        log.warning("Library %s is unreachable or empty; sweep skipped, nothing marked missing.", lib.name)
        return result
    started = timezone.now()
    Library.objects.filter(pk=lib.pk).update(status=LibraryStatus.SCANNING)
    emit("library.status", {"library_id": lib.pk, "status": LibraryStatus.SCANNING})
    known = {c.rel_path: c for c in Copy.objects.filter(library=lib)}
    unchanged_ids: list[int] = []

    def flush() -> None:
        if unchanged_ids:
            Copy.objects.filter(pk__in=unchanged_ids).update(last_seen_at=timezone.now())
            unchanged_ids.clear()

    rules = PathRules.load()
    for rel, st in walk(root, result):
        result.files += 1
        result.seen_paths.add(rel)
        action = check_path(lib, rel, st, known.get(rel), rules)
        if action is Action.UNCHANGED:
            result.unchanged += 1
            unchanged_ids.append(known[rel].pk)
            if len(unchanged_ids) >= BATCH:
                flush()
        elif action is Action.QUEUED:
            result.queued += 1
        elif action is Action.MOVED:
            result.moved += 1
        elif action is Action.IGNORED:
            result.ignored += 1
        else:
            result.skipped += 1
    flush()
    if result.unreadable_dirs:
        # Part of the tree couldn't be listed: don't call anything missing on the strength of it.
        log.warning(
            "Sweep of %s could not list %s folders; nothing marked missing.", lib.name, result.unreadable_dirs
        )
    else:
        result.complete = True
        _reconcile_disappearances(lib, known, result, started)
    now = timezone.now()
    Library.objects.filter(pk=lib.pk).update(status=LibraryStatus.OK, last_full_sweep_at=now)
    emit(
        "library.status",
        {"library_id": lib.pk, "status": LibraryStatus.OK, "files": result.files, "queued": result.queued},
    )
    log.info(
        "Swept %s: %s files, %s queued, %s unchanged, %s moved, %s missing.",
        lib.name,
        result.files,
        result.queued,
        result.unchanged,
        result.moved,
        result.missing,
    )
    return result


def _reconcile_disappearances(lib: Library, known: dict[str, Copy], result: SweepResult, started) -> None:
    """T065: copies not seen in this complete sweep are missing; frames whose copies were all already missing
    before it began are missing too. Paths are re-read, as a move during the sweep changes them."""
    candidates = [c.pk for rel, c in known.items() if c.present and rel not in result.seen_paths]
    gone = [
        c for c in Copy.objects.filter(pk__in=candidates, present=True) if c.rel_path not in result.seen_paths
    ]
    mark_copies_missing(gone)
    result.missing = len(gone)
    mark_frames_missing(lib.pk, before=started)
