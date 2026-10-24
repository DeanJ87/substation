"""Builds and file moves of one collection take turns (spec 013, amendment 2026-10-24).

A build reads a collection's files (its subs, their calibration frames, the masters made from them): a dataset
master being stacked, a mosaic being stitched or masters stacked together, post-processing, a finished project's
progression, a calibration master its subs use. Moving those files under it (Archive, Bring back, the bin) can
break the build or leave its result pointing at files that went elsewhere. So:

- a move, an archive, a bring-back or binning of a collection's files is refused while one of its builds is
  queued or running, naming the build (`builds`, `refusal`);
- a build that reaches the worker while a move of its collection's files is waiting or running goes back in the
  queue until the move ends, saying so in Activity (`wait_for_moves`).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from apps.catalogue.models import (
    ACTIVE_MOVE_STATES,
    Collection,
    CollectionMove,
    Frame,
    MoveDirection,
)
from substation.tasks.models import Task, TaskStatus

from .models import BuiltMaster, CombinedMaster, Master, MasterState

LIVE = (TaskStatus.READY, TaskStatus.RUNNING)
BUILDING = (MasterState.QUEUED, MasterState.RUNNING)


def _filt(f: str | None) -> str:
    return f"{f} " if f else ""


def _combined_name(c: CombinedMaster) -> str:
    return (
        f"{_filt(c.filter_norm)}{'mosaic' if c.method == CombinedMaster.Method.STITCH else 'stacked master'}"
    )


def builds(col: Collection, running_only: bool = False) -> list[str]:
    """Each job queued or running that reads this collection's files, said plainly ("NGC 7000's Hα master v3 is
    being stacked"). `running_only`: only those already reading them."""
    states = (MasterState.RUNNING,) if running_only else BUILDING
    out: list[str] = []
    name = col.name
    for m in (
        Master.objects.filter(dataset__collection=col, state__in=states, task__status__in=LIVE)
        .select_related("dataset")
        .order_by("pk")
    ):
        what = f"{name}'s {_filt(m.dataset.filter_norm)}master v{m.version}"
        out.append(
            f"{what} is being stacked"
            if m.state == MasterState.RUNNING
            else f"{what} is waiting to be stacked"
        )
    for c in CombinedMaster.objects.filter(collection=col, state__in=states, task__status__in=LIVE).order_by(
        "pk"
    ):
        verb = "stitched" if c.method == CombinedMaster.Method.STITCH else "stacked together"
        what = f"{name}'s {_filt(c.filter_norm)}{'mosaic' if c.method == CombinedMaster.Method.STITCH else 'masters'}"
        are = "is" if c.method == CombinedMaster.Method.STITCH else "are"
        out.append(
            f"{what} {are} being {verb}"
            if c.state == MasterState.RUNNING
            else f"{what} {are} waiting to be {verb}"
        )
    out += _post(col, running_only)
    out += _progressions(col, running_only)
    out += _calibration(col, running_only)
    return out


def _tasks(prefix: str, running_only: bool) -> dict[int, str]:
    """Live queue jobs whose dedupe key is `prefix` + an id: {id: status}."""
    statuses = (TaskStatus.RUNNING,) if running_only else LIVE
    out = {}
    for key, status in Task.objects.filter(dedupe_key__startswith=prefix, status__in=statuses).values_list(
        "dedupe_key", "status"
    ):
        tail = (key or "")[len(prefix) :]
        if tail.isdigit():
            out[int(tail)] = status
    return out


def _post(col: Collection, running_only: bool) -> list[str]:
    out = []
    jobs = _tasks("post:", running_only)
    for m in (
        Master.objects.filter(pk__in=jobs, dataset__collection=col).select_related("dataset").order_by("pk")
    ):
        what = f"{col.name}'s {_filt(m.dataset.filter_norm)}master v{m.version}"
        running = jobs[m.pk] == TaskStatus.RUNNING
        out.append(
            f"{what} is being post-processed" if running else f"{what} is waiting to be post-processed"
        )
    jobs = _tasks("post-combined:", running_only)
    for c in CombinedMaster.objects.filter(pk__in=jobs, collection=col).order_by("pk"):
        what = f"{col.name}'s {_combined_name(c)}"
        running = jobs[c.pk] == TaskStatus.RUNNING
        out.append(
            f"{what} is being post-processed" if running else f"{what} is waiting to be post-processed"
        )
    return out


def _progressions(col: Collection, running_only: bool) -> list[str]:
    from apps.finished.models import Progression, ProgressionState

    states = (
        (ProgressionState.RUNNING,) if running_only else (ProgressionState.QUEUED, ProgressionState.RUNNING)
    )
    rows = (
        Progression.objects.filter(
            state__in=states, task__status__in=LIVE, project__linked_projects__collection=col
        )
        .select_related("project")
        .distinct()
        .order_by("pk")
    )
    return [
        f"The progression of {p.project.name} is being built"
        if p.state == ProgressionState.RUNNING
        else f"The progression of {p.project.name} is waiting to be built"
        for p in rows
    ]


def _live_builds(running_only: bool) -> dict[int, str]:
    """Calibration masters being built: {BuiltMaster id: job status}. They have no link to their job but its
    arguments."""
    from substation.tasks import module_path

    from .calibration import build_master

    statuses = (TaskStatus.RUNNING,) if running_only else LIVE
    out = {}
    for args, status in Task.objects.filter(
        name=module_path(build_master.func), status__in=statuses
    ).values_list("args", "status"):
        if args and isinstance(args[0], int):
            out[args[0]] = status
    return out


def _calibration(col: Collection, running_only: bool) -> list[str]:
    from apps.catalogue.services.archive import calibration_for, light_frames

    from .calibration import TYPE_WORD

    jobs = _live_builds(running_only)
    if not jobs:
        return []
    built = list(
        BuiltMaster.objects.filter(pk__in=jobs, state__in=["queued", "running"]).select_related(
            "calibration_set"
        )
    )
    if not built:
        return []
    used = calibration_for(light_frames(col))
    out = []
    for bm in built:
        cs = bm.calibration_set
        if not Frame.objects.filter(calibration_set=cs, pk__in=used).exists():
            continue
        what = f"A master {TYPE_WORD.get(cs.type, cs.type)}{f' ({cs.filter_norm})' if cs.filter_norm else ''}"
        doing = "is being built" if jobs[bm.pk] == TaskStatus.RUNNING else "is waiting to be built"
        out.append(f"{what} that {col.name}'s subs use {doing}")
    return out


def refusal(found: list[str]) -> str:
    """One sentence for a refusal: the first build, how many more, and when to try again."""
    if not found:
        return ""
    more = len(found) - 1
    if not more:
        return f"{found[0]}; try again when it finishes."
    return f"{found[0]} (and {more} more job{'s' if more != 1 else ''}); try again when they finish."


def check_collection(col: Collection, running_only: bool = False) -> str:
    """Why this collection's files can't move now, or ''."""
    return refusal(builds(col, running_only))


def check_frames(shas: Iterable[str]) -> str:
    """Why these files can't be binned now (a build of their collection reads them), or ''."""
    ids = (
        Frame.objects.filter(pk__in=list(shas), dataset__collection__isnull=False)
        .values_list("dataset__collection_id", flat=True)
        .distinct()
    )
    for col in Collection.objects.filter(pk__in=list(ids)).order_by("name"):
        why = check_collection(col)
        if why:
            return why
    return ""


# -- the other way: builds wait for moves --------------------------------------------------------------------------


def _moving(qs: Any) -> CollectionMove | None:
    from apps.catalogue.services.archive import sync

    for m in qs.filter(state__in=ACTIVE_MOVE_STATES).select_related("collection").order_by("pk"):
        if sync(m).state in ACTIVE_MOVE_STATES:
            return m
    return None


def move_of(collection_ids: Iterable[int | None]) -> CollectionMove | None:
    """A move of one of these collections' files, waiting or running."""
    ids = [i for i in collection_ids if i]
    return _moving(CollectionMove.objects.filter(collection_id__in=ids)) if ids else None


def move_note(m: CollectionMove) -> str:
    doing = "archived" if m.direction == MoveDirection.ARCHIVE else "brought back"
    return f"Waiting for {m.collection.name}'s files to be {doing}; starts when the move finishes."


def wait_for_moves(collection_ids: Iterable[int | None], delay_s: float = 60) -> None:
    """Raise Reschedule while a move of these collections' files is waiting or running."""
    from substation.tasks import Reschedule

    m = move_of(collection_ids)
    if m is not None:
        raise Reschedule(delay_s, move_note(m))


def wait_for_calibration_moves(set_id: int, delay_s: float = 60) -> None:
    """A calibration master's build waits while a move takes the set's frames elsewhere."""
    from apps.catalogue.services.archive import calibration_for, light_frames
    from substation.tasks import Reschedule

    frames = Frame.objects.filter(calibration_set_id=set_id)
    for m in (
        CollectionMove.objects.filter(state__in=ACTIVE_MOVE_STATES)
        .select_related("collection")
        .order_by("pk")
    ):
        if _moving(CollectionMove.objects.filter(pk=m.pk)) is None:
            continue
        if frames.filter(pk__in=calibration_for(light_frames(m.collection))).exists():
            raise Reschedule(delay_s, move_note(m))
