"""Archive collections (spec 013): where a collection's files are, what Archive or Bring back would move, starting
and cancelling a move, and dismissing a suggestion. On the catalogue router. No `from __future__ import annotations`
here: see substation.api."""

from datetime import datetime
from typing import Literal

from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.catalogue.api import router
from apps.catalogue.models import Change, Collection, CollectionMove, MoveDirection, MoveItem, MoveItemState
from apps.catalogue.services import archive
from apps.processing.move_guard import check_collection
from substation.api import ApiError, Schema, Status


class LibraryShare(Schema):
    id: int
    name: str
    role: str
    files: int
    bytes: int


class MoveProblemOut(Schema):
    path: str
    reason: str


class CollectionMoveOut(Schema):
    id: int
    direction: str
    state: str
    from_library: str
    to_library: str
    files_total: int
    bytes_total: int
    files_done: int
    bytes_done: int
    problems: int
    error: str
    by: str
    created_at: datetime
    finished_at: datetime | None
    problem_files: list[MoveProblemOut] = []
    change_id: int | None = None  # spec 016: undo it with POST /changes/{id}/undo


class MoveChoice(Schema):
    possible: bool
    reason: str | None = None  # why not, in a sentence
    from_library: str | None = None
    to_library: str | None = None


class CollectionFilesOut(Schema):
    location: Literal["", "active", "archive", "both"]
    libraries: list[LibraryShare]
    active_bytes: int
    archive_bytes: int
    move: CollectionMoveOut | None  # the move under way, or the latest one
    archive: MoveChoice
    bring_back: MoveChoice
    suggested: bool  # worth archiving (FR-010)
    suggest_after_days: int
    can_move: bool  # read-only accounts can't


class MovePreviewOut(Schema):
    direction: str
    from_library: str
    to_library: str
    files: int
    bytes: int
    lights: int
    calibration: int
    calibration_kept: int  # calibration frames staying: other collections still in the library use them
    refused: str | None = None  # why it can't start now: a build reads these files (amendment 2026-10-24)


class CollectionMoveIn(Schema):
    direction: Literal["archive", "bring_back"]


def _move_out(m: CollectionMove) -> CollectionMoveOut:
    problems = MoveItem.objects.filter(move=m, state=MoveItemState.PROBLEM).order_by("pk")[:20]
    return CollectionMoveOut(
        id=m.pk,
        direction=m.direction,
        state=m.state,
        from_library=m.from_library.name,
        to_library=m.to_library.name,
        files_total=m.files_total,
        bytes_total=m.bytes_total,
        files_done=m.files_done,
        bytes_done=m.bytes_done,
        problems=m.problems,
        error=m.error,
        by=m.created_by.get_username() if m.created_by else "",
        created_at=m.created_at,
        finished_at=m.finished_at,
        problem_files=[MoveProblemOut(path=p.rel_path, reason=p.reason) for p in problems],
    )


def _choice(col: Collection, direction: str, moving: bool, building: str = "") -> MoveChoice:
    if moving:
        return MoveChoice(possible=False, reason="Its files are being moved.")
    if building:  # its builds and its moves take turns (amendment 2026-10-24)
        return MoveChoice(possible=False, reason=building)
    try:
        src, dst = archive.pair(col, direction)
    except archive.CantMove as e:
        return MoveChoice(possible=False, reason=str(e))
    return MoveChoice(possible=True, from_library=src.name, to_library=dst.name)


def _cant_move(request) -> bool:  # noqa: ANN001
    from apps.accounts.roles import is_viewer

    return is_viewer(request.user)


@router.get("/collections/{id}/files", response=CollectionFilesOut)
def collection_files(request, id: int):  # noqa: A002
    """Where the collection's files are (active, archive, both; FR-009), whether it can be archived or brought back
    and why not, and its move under way."""
    col = get_object_or_404(Collection, pk=id)
    w = archive.where(col)
    latest = (
        CollectionMove.objects.filter(collection=col)
        .select_related("from_library", "to_library", "created_by")
        .order_by("-pk")
        .first()
    )
    if latest is not None:
        archive.sync(latest)
    moving = archive.busy(col) is not None
    building = "" if moving else check_collection(col)
    return CollectionFilesOut(
        location=w.location,  # type: ignore[arg-type]
        libraries=[LibraryShare(**x) for x in w.libraries],
        active_bytes=w.active_bytes,
        archive_bytes=w.archive_bytes,
        move=_move_out(latest) if latest else None,
        archive=_choice(col, MoveDirection.ARCHIVE, moving, building),
        bring_back=_choice(col, MoveDirection.BRING_BACK, moving, building),
        suggested=col.pk in archive.suggested({col.pk: w.location}),
        suggest_after_days=archive.suggest_after_days(),
        can_move=not _cant_move(request),
    )


@router.get("/collections/{id}/move-preview", response=MovePreviewOut)
def move_preview(request, id: int, direction: Literal["archive", "bring_back"]):  # noqa: A002
    """What Archive or Bring back would move: how many files and bytes, from which library to which."""
    col = get_object_or_404(Collection, pk=id)
    try:
        p = archive.plan(col, direction)
    except archive.CantMove as e:
        raise ApiError(409, "cant_move", str(e)) from None
    return MovePreviewOut(
        direction=direction,
        from_library=p.src.name,
        to_library=p.dst.name,
        files=p.files,
        bytes=p.bytes,
        lights=len(p.lights),
        calibration=len(p.calibration),
        calibration_kept=p.kept,
        refused=check_collection(col) or None,
    )


def _summary(col: Collection, direction: str, files: int, size: int, to: str) -> str:
    what = f"{files:,} file{'s' if files != 1 else ''}, {size / 1e9:.1f} GB"
    verb = "Archived" if direction == MoveDirection.ARCHIVE else "Brought back"
    return f"{verb} {col.name}: {what} to {to}"


@router.post("/collections/{id}/move", response={202: CollectionMoveOut})
def start_move(request, id: int, body: CollectionMoveIn):  # noqa: A002
    """Archive the collection, or bring it back: a job on the bulk queue, followed in Activity (FR-006)."""
    from apps.catalogue.services.changes import record

    if _cant_move(request):
        raise ApiError(403, "forbidden", "Read-only users can't move files.")
    col = get_object_or_404(Collection, pk=id)
    try:
        move, p = archive.start_move(col, body.direction, request.user)
    except archive.CantMove as e:
        raise ApiError(409, "cant_move", str(e)) from None
    change = record(
        request.user,
        Change.Kind.ARCHIVE,
        _summary(col, body.direction, p.files, p.bytes, p.dst.name),
        p.files,
        move_id=move.pk,
    )
    out = _move_out(
        CollectionMove.objects.select_related("from_library", "to_library", "created_by").get(pk=move.pk)
    )
    out.change_id = change.pk
    return Status(202, out)


@router.post("/moves/{id}/cancel", response=CollectionMoveOut)
def cancel_move(request, id: int):  # noqa: A002
    """Stop a move: every file is left either fully moved or untouched (FR-006)."""
    if _cant_move(request):
        raise ApiError(403, "forbidden", "Read-only users can't move files.")
    m = get_object_or_404(
        CollectionMove.objects.select_related("from_library", "to_library", "created_by"), pk=id
    )
    try:
        archive.cancel_move(m, request.user.get_username())
    except archive.CantMove as e:
        raise ApiError(409, "cant_move", str(e)) from None
    m.refresh_from_db()
    return _move_out(m)


@router.post("/collections/{id}/archive-suggestion/dismiss", response={204: None})
def dismiss_suggestion(request, id: int):  # noqa: A002
    """Stop suggesting this collection, until a newer sub of it is shot (FR-010)."""
    if _cant_move(request):
        raise ApiError(403, "forbidden", "Read-only users can't change suggestions.")
    col = get_object_or_404(Collection, pk=id)
    Collection.objects.filter(pk=col.pk).update(archive_dismissed_at=timezone.now())
    return Status(204, None)
