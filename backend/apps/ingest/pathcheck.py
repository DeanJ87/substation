"""Path check (research R4; T048): decide what a file seen by the watcher or a sweep needs.

Unchanged fingerprint (device, inode, size, mtime) → nothing to do. A new path whose fingerprint belongs to
a copy whose old path is gone → a move or rename, recorded without hashing (T062). Anything else → queue a hash job:
live priority if the file was modified in the last 15 minutes, bulk otherwise. Fingerprints only ever skip
work; identity is always the SHA-256 (constitution II). Priority: live if modified in the last 15 minutes,
bulk if in the last 30 days, archive otherwise (US4).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum

from apps.catalogue.models import Copy
from apps.catalogue.services.ignore import PathRules
from apps.libraries.models import Library
from substation.tasks import PRIORITY_ARCHIVE, PRIORITY_BULK, PRIORITY_LIVE, enqueue

from .headers import is_image_name

LIVE_WINDOW_S = 15 * 60
BULK_WINDOW_S = 30 * 24 * 3600  # older than this: archive priority
# Folders that NAS and desktop OSes create and that never hold subs
SKIP_DIRS = {
    "@eaDir",
    "#recycle",
    "#snapshot",
    ".Trashes",
    ".Spotlight-V100",
    ".fseventsd",
    ".TemporaryItems",
    "$RECYCLE.BIN",
    "System Volume Information",
    "lost+found",
}


class Action(Enum):
    SKIP = "skip"
    UNCHANGED = "unchanged"
    QUEUED = "queued"
    MOVED = "moved"
    IGNORED = "ignored"


@dataclass(frozen=True)
class Fingerprint:
    dev: int
    ino: int
    size: int
    mtime_ns: int

    @classmethod
    def of(cls, st: os.stat_result) -> Fingerprint:
        return cls(st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)

    def same_file(self, other: Fingerprint) -> bool:
        """Unchanged file: same inode, size and mtime. The device number is left out: it changes when a share is
        remounted or a container restarts (Docker Desktop), which must not mean re-reading every file."""
        return (self.ino, self.size, self.mtime_ns) == (other.ino, other.size, other.mtime_ns)

    @classmethod
    def of_copy(cls, c: Copy) -> Fingerprint:
        return cls(c.st_dev, c.st_ino, c.st_size, c.st_mtime_ns)


def skip_dir(name: str) -> bool:
    return name.startswith(".") or name in SKIP_DIRS


def priority_for(st: os.stat_result, now: float | None = None) -> int:
    """Live subs first, then recent bulk arrivals (a holiday's worth), then old archive files."""
    now = time.time() if now is None else now
    age = now - st.st_mtime
    if age < LIVE_WINDOW_S:
        return PRIORITY_LIVE
    return PRIORITY_BULK if age < BULK_WINDOW_S else PRIORITY_ARCHIVE


def _moved_from(lib: Library, rel_path: str, fp: Fingerprint) -> Copy | None:
    """A known copy with this exact file object whose old path is gone: the file was moved or renamed."""
    for c in Copy.objects.filter(
        library=lib, st_ino=fp.ino, st_size=fp.size, st_mtime_ns=fp.mtime_ns
    ).exclude(rel_path=rel_path):
        if not os.path.lexists(os.path.join(lib.mount_path, c.rel_path)):
            return c
    return None


def check_path(
    lib: Library, rel_path: str, st: os.stat_result, known: Copy | None, rules: PathRules | None = None
) -> Action:
    if not is_image_name(os.path.basename(rel_path)):
        return Action.SKIP
    if (rules if rules is not None else PathRules.load()).matches(lib.pk, rel_path):
        return Action.IGNORED  # a folder or glob ignore rule (US5)
    fp = Fingerprint.of(st)
    if known is not None and known.present and Fingerprint.of_copy(known).same_file(fp):
        return Action.UNCHANGED
    if known is None and (moved := _moved_from(lib, rel_path, fp)) is not None:
        from apps.catalogue.services.tracking import record_move

        record_move(moved, rel_path, st)
        return Action.MOVED
    from .tasks.hash import hash_file

    enqueue(
        hash_file,
        lib.pk,
        rel_path,
        time.time(),
        dedupe_key=f"hash:{lib.pk}:{rel_path}:{fp.mtime_ns}:{fp.size}",
        priority=priority_for(st),
    )
    return Action.QUEUED
