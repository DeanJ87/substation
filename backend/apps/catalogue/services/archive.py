"""Archive collections (spec 013): move a collection's files from its active library (fast storage, where new subs
land) to that library's archive (large, slower storage), or bring them back.

Only libraries mounted read-write take part, as the owner set out: a read-only library is never archived to or
brought back from (FR-011). Each file keeps its path relative to the library root (FR-002). It is copied beside its
destination under a hidden name, the copy's SHA-256 is checked against the catalogue, and only then is it put in
place, recorded as the frame's copy there and removed from the source (FR-003). A file already at the destination
with the same content isn't copied again; one with different content is never overwritten, only reported (FR-004).
A row per file records what is done, so a move stopped by a restart carries on (SC-002), and a cancelled move leaves
every file either fully moved or untouched (FR-006). While files are moving, library scans don't call them missing
(FR-007)."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.db import transaction
from django.db.models import Count, F, Max, QuerySet, Sum
from django.utils import timezone

from apps.libraries.access import read_only_reason
from apps.libraries.models import Library, LibraryRole, LibraryStatus
from substation.events.emit import emit
from substation.tasks import Cancelled, check_cancelled, check_interrupted, report_progress

from ..models import (
    ACTIVE_MOVE_STATES,
    Collection,
    CollectionMove,
    Copy,
    CopyEvent,
    CopyEventKind,
    Frame,
    FrameStatus,
    FrameType,
    MoveDirection,
    MoveItem,
    MoveItemState,
    MoveState,
)
from .binning import QUARANTINE

log = logging.getLogger(__name__)
CHUNK = 8 << 20
PROGRESS_EVERY = 256 << 20  # bytes between progress notes within one large file
PART = ".substation-part"  # a copy being written: hidden (a dot name), so no scan or watcher picks it up
GONE = (FrameStatus.BINNED, FrameStatus.DELETED)


class CantMove(Exception):
    """Why a collection can't be archived or brought back, said plainly for the page."""


# -- where a collection's files are (FR-009) ------------------------------------------------------------------------


def light_frames(col: Collection) -> QuerySet[Frame]:
    return Frame.objects.filter(dataset__collection=col).exclude(status__in=GONE)


def present_copies(frames: QuerySet[Frame]) -> QuerySet[Copy]:
    """Copies on disk, outside the bin's quarantine (binned files are the bin's business, not the archive's)."""
    return Copy.objects.filter(frame__in=frames, present=True).exclude(rel_path__startswith=f"{QUARANTINE}/")


def location(active_bytes: int, archive_bytes: int) -> str:
    if active_bytes and archive_bytes:
        return "both"
    if archive_bytes:
        return "archive"
    return "active" if active_bytes else ""


@dataclass
class Where:
    libraries: list[dict] = field(default_factory=list)  # {id, name, role, files, bytes}
    active_bytes: int = 0
    archive_bytes: int = 0

    @property
    def location(self) -> str:
        return location(self.active_bytes, self.archive_bytes)


def where(col: Collection) -> Where:
    rows = (
        present_copies(light_frames(col))
        .values("library_id", "library__name", "library__role")
        .annotate(files=Count("id"), bytes=Sum("frame__size_bytes"))
        .order_by("library__name")
    )
    out = Where()
    for r in rows:
        out.libraries.append(
            {
                "id": r["library_id"],
                "name": r["library__name"],
                "role": r["library__role"] or "",
                "files": r["files"],
                "bytes": r["bytes"] or 0,
            }
        )
        if r["library__role"] == LibraryRole.ACTIVE:
            out.active_bytes += r["bytes"] or 0
        elif r["library__role"] == LibraryRole.ARCHIVE:
            out.archive_bytes += r["bytes"] or 0
    return out


def locations() -> dict[int, str]:
    """Every collection's location at once, for the Library's filter: active, archive, both, or blank."""
    rows = (
        Copy.objects.filter(present=True, frame__dataset__collection__isnull=False)
        .exclude(frame__status__in=GONE)
        .exclude(rel_path__startswith=f"{QUARANTINE}/")
        .filter(library__role__in=[LibraryRole.ACTIVE, LibraryRole.ARCHIVE])
        .values("frame__dataset__collection_id", "library__role")
        .annotate(bytes=Sum("frame__size_bytes"))
    )
    by: dict[int, dict[str, int]] = {}
    for r in rows:
        by.setdefault(r["frame__dataset__collection_id"], {})[r["library__role"]] = r["bytes"] or 0
    return {cid: location(b.get("active", 0), b.get("archive", 0)) for cid, b in by.items()}


# -- which libraries, and whether they may take part (FR-001, FR-011) -----------------------------------------------


def _holding(col: Collection, role: str) -> Library | None:
    """The library of this role holding most of the collection's files."""
    w = where(col)
    held = sorted((x for x in w.libraries if x["role"] == role), key=lambda x: -x["bytes"])
    return Library.objects.filter(pk=held[0]["id"]).select_related("archive_to").first() if held else None


def _archive_pair(col: Collection) -> tuple[Library, Library]:
    if not Library.objects.filter(role=LibraryRole.ACTIVE).exists():
        raise CantMove(
            "No library is set as active. Choose an active library and its archive in Settings → Library."
        )
    src = _holding(col, LibraryRole.ACTIVE)
    if src is None:
        raise CantMove("None of its files are in an active library.")
    if src.archive_to is None:
        raise CantMove(f"{src.name} has no archive library. Choose one in Settings → Library.")
    return src, src.archive_to


def _bring_back_pair(col: Collection) -> tuple[Library, Library]:
    src = _holding(col, LibraryRole.ARCHIVE)
    if src is None:
        raise CantMove("None of its files are in an archive library.")
    dst = Library.objects.filter(role=LibraryRole.ACTIVE, archive_to=src).order_by("name").first()
    if dst is None:
        raise CantMove(f"No active library archives to {src.name}. Choose one in Settings → Library.")
    return src, dst


def pair(col: Collection, direction: str) -> tuple[Library, Library]:
    src, dst = _archive_pair(col) if direction == MoveDirection.ARCHIVE else _bring_back_pair(col)
    check_libraries(src, dst, direction)
    return src, dst


def check_libraries(src: Library, dst: Library, direction: str) -> None:
    """Both libraries reachable, mounted read-write, and still in the roles the move needs."""
    want = (
        (LibraryRole.ACTIVE, LibraryRole.ARCHIVE)
        if direction == MoveDirection.ARCHIVE
        else (LibraryRole.ARCHIVE, LibraryRole.ACTIVE)
    )
    if (src.role, dst.role) != want:
        raise CantMove("The libraries' roles have changed since; check Settings → Library.")
    for lib in (src, dst):
        if (why := read_only_reason(lib)) is not None:
            raise CantMove(f"{lib.name}: {why}")
        if lib.status == LibraryStatus.UNREACHABLE:
            raise CantMove(f"{lib.name} can't be reached right now.")


# -- which files move (FR-002, FR-005) -----------------------------------------------------------------------------


def calibration_for(lights: QuerySet[Frame]) -> set[str]:
    """The calibration frames these lights use: the masters matched to them, what built those masters (a master
    flat's bias or dark flat), and the raw frames of the sets they were built from. Masters SubStation built live in
    its own folder, not a library, so they have no copy here and never move."""
    from apps.processing.models import BuiltMaster, CalibrationMatch

    matches = CalibrationMatch.objects.filter(frame__in=lights)
    masters = set(matches.exclude(dark=None).values_list("dark_id", flat=True))
    masters |= set(matches.exclude(flat=None).values_list("flat_id", flat=True))
    built = BuiltMaster.objects.filter(frame_id__in=masters)
    masters |= set(built.exclude(calibrated_with=None).values_list("calibrated_with_id", flat=True))
    sets = BuiltMaster.objects.filter(frame_id__in=masters).values("calibration_set_id")
    return masters | set(Frame.objects.filter(calibration_set_id__in=sets).values_list("pk", flat=True))


@dataclass
class Plan:
    direction: str
    src: Library
    dst: Library
    lights: list[tuple[str, str, int]]  # (sha256, rel_path, size)
    calibration: list[tuple[str, str, int]]
    kept: int = 0  # calibration frames staying behind: other collections still in this library use them

    @property
    def files(self) -> int:
        return len(self.lights) + len(self.calibration)

    @property
    def bytes(self) -> int:
        return sum(x[2] for x in self.lights) + sum(x[2] for x in self.calibration)


def _rows(copies: QuerySet[Copy]) -> list[tuple[str, str, int]]:
    return [
        (sha, rel, size or 0)
        for sha, rel, size in copies.values_list("frame_id", "rel_path", "frame__size_bytes")
    ]


def files_for(col: Collection, direction: str, src: Library, dst: Library) -> Plan:
    lights_q = light_frames(col)
    lights = _rows(present_copies(lights_q).filter(library=src))
    cal = calibration_for(lights_q)
    kept: set[str] = set()
    if direction == MoveDirection.ARCHIVE:
        # calibration still needed by lights staying in the active library (other collections, or none) stays too
        staying = (
            Frame.objects.filter(frame_type=FrameType.LIGHT, copies__library=src, copies__present=True)
            .exclude(dataset__collection=col)
            .exclude(status__in=GONE)
        )
        kept = cal & calibration_for(staying)
    in_src = present_copies(Frame.objects.filter(pk__in=cal)).filter(library=src)
    calibration = _rows(in_src.exclude(frame_id__in=kept))
    n_kept = in_src.filter(frame_id__in=kept).values("frame_id").distinct().count()
    return Plan(direction, src, dst, lights, calibration, n_kept)


def plan(col: Collection, direction: str) -> Plan:
    src, dst = pair(col, direction)
    return files_for(col, direction, src, dst)


# -- starting, cancelling, following a move -------------------------------------------------------------------------


def busy(col: Collection) -> CollectionMove | None:
    for m in CollectionMove.objects.filter(collection=col, state__in=ACTIVE_MOVE_STATES).order_by("pk"):
        sync(m)
        if m.state in ACTIVE_MOVE_STATES:
            return m
    return None


def start_move(col: Collection, direction: str, user=None) -> tuple[CollectionMove, Plan]:  # noqa: ANN001
    """Queue a move on the bulk queue. Its files are chosen again when it starts, so a move queued behind another
    (an undo) moves what is there by then."""
    from apps.ingest.tasks.archive import move_collection
    from substation.tasks import PRIORITY_BULK, enqueue

    if busy(col) is not None:
        raise CantMove("Its files are already being moved.")
    p = plan(col, direction)
    if not p.files:
        raise CantMove(f"None of its files are in {p.src.name}; there's nothing to move.")
    move = CollectionMove.objects.create(
        collection=col,
        direction=direction,
        from_library=p.src,
        to_library=p.dst,
        files_total=p.files,
        bytes_total=p.bytes,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    result = enqueue(
        move_collection, move.pk, dedupe_key=f"move-collection:{move.pk}", priority=PRIORITY_BULK
    )
    CollectionMove.objects.filter(pk=move.pk).update(task_id=result.id)
    move.refresh_from_db()
    emit("collection.files", {"collection_id": col.pk, "move_id": move.pk, "state": move.state})
    return move, p


def sync(move: CollectionMove) -> CollectionMove:
    """A move whose job was cancelled or failed outside it (Activity's Cancel on a waiting job) says so too."""
    from substation.tasks.models import Task, TaskStatus

    if move.state not in ACTIVE_MOVE_STATES or move.task_id is None:
        return move
    row = Task.objects.filter(pk=move.task_id).values_list("status", "error").first()
    if row is None or row[0] in (TaskStatus.CANCELLED, TaskStatus.FAILED):
        state = MoveState.CANCELLED if row is None or row[0] == TaskStatus.CANCELLED else MoveState.FAILED
        error = (row[1] or "").strip().splitlines()[-1:] if row else []
        _finish(move, state, error[0] if error else "")
    return move


def cancel_move(move: CollectionMove, by: str = "") -> CollectionMove:
    from substation.tasks.models import Task, TaskStatus

    sync(move)
    if move.state not in ACTIVE_MOVE_STATES:
        raise CantMove("That move has already finished.")
    task = Task.objects.filter(pk=move.task_id).first() if move.task_id else None
    if task is not None and task.status == TaskStatus.RUNNING:
        # stops between chunks: the file being copied is left untouched, every file before it fully moved
        Task.objects.filter(pk=task.pk).update(
            cancel_requested=True, progress_note=f"Cancelling (asked by {by})"[:300]
        )
        return move
    if task is not None:
        Task.objects.filter(pk=task.pk).update(status=TaskStatus.CANCELLED, finished_at=timezone.now())
    _finish(move, MoveState.CANCELLED)
    return move


def moving_frames() -> QuerySet[MoveItem, Any]:
    """Frames with a file still to move in a move that's waiting or running: scans leave their copies alone."""
    from substation.tasks.models import TaskStatus

    return MoveItem.objects.filter(
        state=MoveItemState.PENDING,
        move__state__in=ACTIVE_MOVE_STATES,
        move__task__status__in=[TaskStatus.READY, TaskStatus.RUNNING],
    ).values("frame_id")


def _finish(move: CollectionMove, state: str, error: str = "") -> None:
    now = timezone.now()
    CollectionMove.objects.filter(pk=move.pk).update(state=state, finished_at=now, error=error[:1000])
    move.state, move.finished_at, move.error = state, now, error[:1000]
    emit("collection.files", {"collection_id": move.collection_id, "move_id": move.pk, "state": state})


# -- running a move (the queued job) ---------------------------------------------------------------------------------


def _plan_items(move: CollectionMove) -> None:
    check_libraries(move.from_library, move.to_library, move.direction)
    p = files_for(move.collection, move.direction, move.from_library, move.to_library)
    items = {(sha, rel): (size, False) for sha, rel, size in p.lights}
    items.update({(sha, rel): (size, True) for sha, rel, size in p.calibration if (sha, rel) not in items})
    with transaction.atomic():
        MoveItem.objects.bulk_create(
            MoveItem(move=move, frame_id=sha, rel_path=rel, size_bytes=size, calibration=cal)
            for (sha, rel), (size, cal) in items.items()
        )
        CollectionMove.objects.filter(pk=move.pk).update(
            planned=True, files_total=len(items), bytes_total=sum(s for s, _ in items.values())
        )
    move.refresh_from_db()


def _wait_for_earlier(move: CollectionMove) -> None:
    from substation.tasks import Reschedule

    earlier = CollectionMove.objects.filter(
        collection_id=move.collection_id, state__in=ACTIVE_MOVE_STATES, pk__lt=move.pk
    ).order_by("pk")
    for m in earlier:
        if sync(m).state in ACTIVE_MOVE_STATES:
            raise Reschedule(30, "Waiting for the collection's earlier move to stop")


def run_move(move_id: int) -> dict:
    move = CollectionMove.objects.select_related("collection", "from_library", "to_library").get(pk=move_id)
    if move.state not in ACTIVE_MOVE_STATES:
        return {"result": move.state}
    _wait_for_earlier(move)
    try:
        if not move.planned:
            _plan_items(move)
        else:  # resumed after a restart: the mounts may have changed meanwhile
            check_libraries(move.from_library, move.to_library, move.direction)
    except CantMove as e:
        _finish(move, MoveState.FAILED, str(e))
        return {"result": "failed", "reason": str(e)}
    CollectionMove.objects.filter(pk=move.pk).update(state=MoveState.RUNNING)
    try:
        for item in MoveItem.objects.filter(move=move, state=MoveItemState.PENDING).order_by("pk"):
            move_one(move, item)
    except Cancelled:
        _finish(move, MoveState.CANCELLED)
        raise
    move.refresh_from_db()
    _finish(move, MoveState.DONE)
    return {
        "result": "done",
        "files": move.files_done,
        "bytes": move.bytes_done,
        "problems": move.problems,
        "collection": move.collection.name,
        "direction": move.direction,
    }


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
            check_interrupted()
    return h.hexdigest()


def _progress(move: CollectionMove, extra: int = 0) -> None:
    m = CollectionMove.objects.filter(pk=move.pk).values(
        "files_done", "files_total", "bytes_done", "bytes_total"
    )
    r: dict[str, Any] = dict(m.first() or {})
    done, total = (r.get("bytes_done") or 0) + extra, r.get("bytes_total") or 0
    gb = 1e9
    report_progress(
        done / total if total else None,
        f"{r.get('files_done', 0):,} of {r.get('files_total', 0):,} files · {done / gb:.1f} of {total / gb:.1f} GB",
    )


def _copy(move: CollectionMove, src: Path, part: Path) -> None:
    """Copy in chunks, stopping cleanly between them when asked to (cancel) or when the worker stops."""
    written = since = 0
    with open(src, "rb") as r, open(part, "wb") as w:
        while chunk := r.read(CHUNK):
            w.write(chunk)
            written += len(chunk)
            since += len(chunk)
            check_cancelled()
            check_interrupted()
            if since >= PROGRESS_EVERY:
                since = 0
                _progress(move, written)
        w.flush()
        os.fsync(w.fileno())
    with contextlib.suppress(OSError):  # keep its modification time
        os.utime(part, ns=(os.stat(src).st_atime_ns, os.stat(src).st_mtime_ns))


def _into_place(part: Path, dst: Path) -> str | None:
    """Put the verified copy at its name without ever replacing a file that appeared there meanwhile."""
    try:
        os.link(part, dst)
    except FileExistsError:
        return "A different file appeared at its place in the destination while it was copying; neither was changed."
    except OSError:  # a filesystem without hard links
        if dst.exists():
            return "A different file appeared at its place in the destination while it was copying; neither was changed."
        os.rename(part, dst)
    return None


def _copy_verified(move: CollectionMove, item: MoveItem, src: Path, dst: Path) -> str | None:
    part = dst.with_name(f".{dst.name}{PART}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        _copy(move, src, part)
        if sha256_of(part) != item.frame_id:
            return "Its copy didn't match its content in the catalogue, so it was left where it was."
        return _into_place(part, dst)
    finally:
        part.unlink(missing_ok=True)  # the hidden copy goes whatever happened: a file is never half-moved


def _place(move: CollectionMove, item: MoveItem, src: Path, dst: Path) -> str | None:
    """Get a verified copy of the file at the destination. Returns why not, or None when it's there."""
    if dst.exists():
        if sha256_of(dst) == item.frame_id:
            return None  # already there (a resumed move, or the owner copied it): not copied again
        return (
            f"A different file is already at {item.rel_path} in {move.to_library.name}; neither was changed."
        )
    if not src.exists():
        return f"It's no longer in {move.from_library.name}."
    return _copy_verified(move, item, src, dst)


def _record(move: CollectionMove, item: MoveItem, dst: Path) -> None:
    st = os.stat(dst)
    now = timezone.now()
    fp = {"st_dev": st.st_dev, "st_ino": st.st_ino, "st_size": st.st_size, "st_mtime_ns": st.st_mtime_ns}
    with transaction.atomic():
        copy, created = Copy.objects.get_or_create(
            library=move.to_library,
            rel_path=item.rel_path,
            defaults={
                "frame_id": item.frame_id,
                "first_seen_at": now,
                "last_seen_at": now,
                "is_bad_prefixed": dst.name.startswith("BAD_"),
                **fp,
            },
        )
        if not created:
            Copy.objects.filter(pk=copy.pk).update(
                frame_id=item.frame_id, present=True, missing_since=None, last_seen_at=now, **fp
            )
        CopyEvent.objects.create(
            kind=CopyEventKind.MOVED,
            frame_id=item.frame_id,
            copy=copy,
            library=move.to_library,
            details={
                "from": f"{move.from_library.name}/{item.rel_path}",
                "to": f"{move.to_library.name}/{item.rel_path}",
                "by": move.direction,
            },
        )


def _remove_source(move: CollectionMove, item: MoveItem, src: Path) -> str | None:
    try:
        src.unlink(missing_ok=True)
    except OSError as e:
        return f"Copied, but it couldn't be removed from {move.from_library.name}: {e.strerror or e}"
    Copy.objects.filter(library=move.from_library, rel_path=item.rel_path, frame_id=item.frame_id).delete()
    return None


def move_one(move: CollectionMove, item: MoveItem) -> None:
    root_from, root_to = Path(move.from_library.mount_path), Path(move.to_library.mount_path)
    src, dst = root_from / item.rel_path, root_to / item.rel_path
    try:
        why = _place(move, item, src, dst)
    except OSError as e:
        why = f"It couldn't be copied: {e.strerror or e}"
    if why is None:
        _record(move, item, dst)
        why = _remove_source(move, item, src)
    if why is not None:
        MoveItem.objects.filter(pk=item.pk).update(state=MoveItemState.PROBLEM, reason=why[:500])
        CollectionMove.objects.filter(pk=move.pk).update(problems=F("problems") + 1)
        log.warning("Move %s left %s: %s", move.pk, item.rel_path, why)
    else:
        MoveItem.objects.filter(pk=item.pk).update(state=MoveItemState.DONE)
        CollectionMove.objects.filter(pk=move.pk).update(
            files_done=F("files_done") + 1, bytes_done=F("bytes_done") + item.size_bytes
        )
    _progress(move)


# -- suggestions (FR-010) -----------------------------------------------------------------------------------------


def suggest_after_days() -> int:
    from apps.processing.config import processing_settings

    return int(processing_settings().get("archive", {}).get("suggest_after_days", 60))


def suggested(where_by: dict[int, str] | None = None) -> set[int]:
    """Collections worth archiving: files in an active library that has an archive, not moving now, not dismissed
    since its last sub, and either every project marked done or no sub shot for the set number of days and a
    current master."""
    from apps.processing.models import Master

    days = suggest_after_days()
    if days <= 0 or not Library.objects.filter(role=LibraryRole.ACTIVE, archive_to__isnull=False).exists():
        return set()
    where_by = locations() if where_by is None else where_by
    candidates = [cid for cid, loc in where_by.items() if loc in ("active", "both")]
    cutoff = timezone.now() - timedelta(days=days)
    last = dict(
        Frame.objects.filter(dataset__collection_id__in=candidates, frame_type=FrameType.LIGHT)
        .values("dataset__collection_id")
        .annotate(last=Max("date_obs_utc"))
        .values_list("dataset__collection_id", "last")
    )
    current = set(
        Master.objects.filter(dataset__collection_id__in=candidates, state="current").values_list(
            "dataset__collection_id", flat=True
        )
    )
    moving = set(
        CollectionMove.objects.filter(collection_id__in=candidates, state__in=ACTIVE_MOVE_STATES).values_list(
            "collection_id", flat=True
        )
    )
    dismissed = dict(
        Collection.objects.filter(pk__in=candidates, archive_dismissed_at__isnull=False).values_list(
            "pk", "archive_dismissed_at"
        )
    )
    old = {
        cid
        for cid, at in last.items()
        if at is not None
        and at < cutoff
        and cid in current
        and cid not in moving
        and not (cid in dismissed and dismissed[cid] >= at)
    }
    # every project marked done: worth archiving now, without waiting out the days (amendment 2026-10-22)
    done = {
        cid
        for cid in Collection.objects.filter(pk__in=candidates, projects__isnull=False)
        .exclude(projects__done_at__isnull=True)
        .values_list("pk", flat=True)
        .distinct()
        if cid not in moving
        and not (cid in dismissed and (last.get(cid) is None or dismissed[cid] >= last[cid]))
    }
    return old | done


def undo(move_id: int, user=None) -> str:  # noqa: ANN001
    """Undo an archive or bring-back (spec 016): one that hasn't started is cancelled; otherwise the files go back
    the other way, after the first move stops."""
    from substation.tasks.models import Task, TaskStatus

    move = CollectionMove.objects.select_related("collection").filter(pk=move_id).first()
    if move is None:
        raise CantMove("That move is no longer recorded.")
    sync(move)
    task = Task.objects.filter(pk=move.task_id).first() if move.task_id else None
    if move.state in ACTIVE_MOVE_STATES and (task is None or task.status == TaskStatus.READY):
        cancel_move(move)
        return "Cancelled the move before it started"
    back = MoveDirection.BRING_BACK if move.direction == MoveDirection.ARCHIVE else MoveDirection.ARCHIVE
    src, dst = move.to_library, move.from_library
    check_libraries(src, dst, back)
    if move.state in ACTIVE_MOVE_STATES and move.task_id is not None:
        # it stops after the file it's on; the move back waits for that (_wait_for_earlier)
        Task.objects.filter(pk=move.task_id).update(cancel_requested=True)
    new = CollectionMove.objects.create(
        collection=move.collection,
        direction=back,
        from_library=src,
        to_library=dst,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    from apps.ingest.tasks.archive import move_collection
    from substation.tasks import PRIORITY_BULK, enqueue

    result = enqueue(move_collection, new.pk, dedupe_key=f"move-collection:{new.pk}", priority=PRIORITY_BULK)
    CollectionMove.objects.filter(pk=new.pk).update(task_id=result.id)
    return f"Moving {move.collection.name}'s files back to {dst.name}"
