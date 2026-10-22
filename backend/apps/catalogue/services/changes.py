"""Changes made by hand, and undoing them (spec 016)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from django.db import transaction
from django.utils import timezone

from apps.catalogue.models import Change, Dataset, Frame, UserVerdict

UNDO_FOR_DAYS = 30


class CantUndo(Exception):
    """Said plainly, for the page."""


def record(user, kind: str, summary: str, count: int, **data) -> Change:  # noqa: ANN001
    return Change.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        kind=kind,
        summary=summary[:200],
        count=count,
        data=data,
    )


def _touch(dataset_ids: Iterable[int]) -> None:
    from apps.catalogue.services.tracking import touch_dataset
    from apps.processing.effective import recount_grades

    for ds in Dataset.objects.filter(pk__in=set(dataset_ids)):
        recount_grades(ds)
        touch_dataset(ds)


def _undo_verdicts(change: Change) -> str:
    rows = UserVerdict.objects.filter(pk__in=change.data.get("verdict_ids", []))
    frames = list(Frame.objects.filter(verdicts__in=rows).distinct().values_list("pk", "dataset_id"))
    rows.delete()
    _touch(ds for _, ds in frames if ds)
    from substation.events.emit import emit

    for sha, _ in frames:
        emit("frame.updated", {"sha256": sha, "fields": ["verdict"]})
    return f"Undone: {change.summary[:1].lower()}{change.summary[1:]}"


def _undo_bin(change: Change) -> str:
    from apps.catalogue.services.binning import restore_frames

    out = restore_frames(change.data.get("sha256s", []))
    note = f"Restored {out['restored']:,} from the bin"
    if out["not_restored"]:
        note += f"; {out['not_restored']:,} couldn't be put back"
    return note


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'s' if n != 1 else ''}"


def _undo_move(change: Change) -> str:
    """Put each dataset back in the collection (and project) it came from, unless it has moved again since."""
    from apps.catalogue.models import Collection, Project
    from apps.catalogue.services.library import refresh_objects

    to = change.data.get("to")
    back = 0
    touched = {to} if to else set()
    previous = change.data.get("previous", {})
    # a collection or project deleted since can't be returned to: those datasets go back to no collection or project
    cols = set(
        Collection.objects.filter(pk__in={c for c, _, _ in previous.values() if c}).values_list(
            "pk", flat=True
        )
    )
    projects = set(
        Project.objects.filter(pk__in={p for _, p, _ in previous.values() if p}).values_list("pk", flat=True)
    )
    for ds_id, (col, project, position) in previous.items():
        col = col if col in cols else None
        project, position = (project, position) if project in projects and col else (None, None)
        n = Dataset.objects.filter(pk=int(ds_id), collection_id=to).update(
            collection_id=col, project_id=project, project_position=position
        )
        back += n
        if n and col:
            touched.add(col)
    for c in Collection.objects.filter(pk__in=touched):
        refresh_objects(c)
    return f"Put {_plural(back, 'dataset')} back where {'it was' if back == 1 else 'they were'}"


def _undo_dismiss(change: Change) -> str:
    """Show the dismissed failures again (those still dismissed)."""
    from substation.tasks.models import Task

    back = 0
    for task_id, note in change.data.get("tasks", {}).items():
        back += Task.objects.filter(pk=task_id, progress_note="dismissed").update(progress_note=note)
    return f"{_plural(back, 'failed job')} back in Activity"


def _undo_qa(change: Change) -> str:
    """Put back each frame's QA choice from before, where this change's choice is still the one in force."""
    from apps.processing.models import CalibrationQA
    from substation.events.emit import emit

    now = change.data.get("verdict", "")
    back = 0
    for sha, before in change.data.get("previous", {}).items():
        back += CalibrationQA.objects.filter(frame_id=sha, override=now).update(override=before)
    emit("calibration.updated", {})
    return f"Put back the QA choice on {_plural(back, 'frame')}"


def _undo_archive(change: Change) -> str:
    """Spec 013: a move that hasn't started is cancelled; otherwise the files go back the other way."""
    from apps.catalogue.services.archive import CantMove, undo

    try:
        return undo(int(change.data.get("move_id", 0)), change.user)
    except CantMove as e:
        raise CantUndo(str(e)) from None


def _undo_project(change: Change) -> str:
    """Projects merged, split, removed, edited or datasets moved between them (amendment 2026-10-22)."""
    from apps.catalogue.services.projects import undo as undo_project

    return undo_project(change.data)


def _undo_collection(change: Change) -> str:
    """A collection's record deleted, with its projects (amendment 2026-10-22)."""
    from apps.catalogue.services.collections import undo as undo_collection

    return undo_collection(change.data)


def _undo_link(change: Change) -> str:
    """A finished image's links to projects: put back the ones from before, if nobody has changed them since."""
    from apps.finished.models import FinishedProject

    fp = FinishedProject.objects.filter(pk=change.data.get("finished_id")).first()
    if fp is None:
        raise CantUndo("That finished image is no longer recorded.")
    now = sorted(fp.linked_projects.values_list("pk", flat=True))
    if now != sorted(change.data.get("after", [])):
        raise CantUndo(f"The links of {fp.name} have changed since.")
    from apps.catalogue.models import Project

    fp.linked_projects.set(Project.objects.filter(pk__in=change.data.get("before", [])))
    return f"Put back the links of {fp.name}"


UNDOERS: dict[str, Callable[[Change], str]] = {
    Change.Kind.VERDICT: _undo_verdicts,
    Change.Kind.AGREE: _undo_verdicts,
    Change.Kind.BIN: _undo_bin,
    Change.Kind.MOVE: _undo_move,
    Change.Kind.DISMISS: _undo_dismiss,
    Change.Kind.QA: _undo_qa,
    Change.Kind.ARCHIVE: _undo_archive,
    Change.Kind.PROJECT: _undo_project,
    Change.Kind.COLLECTION: _undo_collection,
    Change.Kind.LINK: _undo_link,
}


def undo(change: Change) -> str:
    """Reverse one change; returns what happened, as a sentence."""
    if change.undone_at is not None:
        raise CantUndo("That change was already undone.")
    if (timezone.now() - change.created_at).days > UNDO_FOR_DAYS:
        raise CantUndo(f"Changes can be undone for {UNDO_FOR_DAYS} days; this one is older.")
    how = UNDOERS.get(change.kind)
    if how is None:
        raise CantUndo("This kind of change can't be undone.")
    with transaction.atomic():
        note = how(change)
        Change.objects.filter(pk=change.pk).update(undone_at=timezone.now())
    return note + "."
