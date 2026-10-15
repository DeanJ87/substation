"""Bulk actions beyond subs (spec 016 U6, on the catalogue router): build several raw calibration sets, re-grade,
stack or move several datasets. Moving is recorded as a change, so it can be undone. No `from __future__ import
annotations` here: see substation.api."""

from django.shortcuts import get_object_or_404

from apps.accounts.roles import is_viewer
from apps.catalogue.api import router
from apps.catalogue.models import CalibrationSet, Change, Collection, Dataset
from apps.catalogue.services.changes import record
from substation.api import ApiError, Schema
from substation.tasks import PRIORITY_BULK, enqueue

from . import calibration as cal
from . import masters as svc
from .calibration import BUILD_PRIORITY, RAW_TYPES

MOST = 500  # sets or datasets at a time


def _may_change(request, ids: list) -> None:  # noqa: ANN001
    if is_viewer(request.user):
        raise ApiError(403, "read_only", "Your account can't change things.")
    if not ids:
        raise ApiError(422, "none_chosen", "Choose at least one.")
    if len(ids) > MOST:
        raise ApiError(422, "too_many", f"Up to {MOST} at a time.")


class Skipped(Schema):
    id: int
    reason: str


# ---- calibration sets -----------------------------------------------------------------------------------------
class BuildManyIn(Schema):
    ids: list[int]
    force: bool = False


class BuildManyOut(Schema):
    queued: int
    skipped: list[Skipped]


@router.post("/bulk/calibration-sets/build", response=BuildManyOut)
def build_many(request, body: BuildManyIn):
    """Queue a master build for each chosen raw set. A set already building, or not a raw set, is skipped and
    said why."""
    _may_change(request, body.ids)
    queued, skipped = 0, []
    for cs in CalibrationSet.objects.filter(pk__in=body.ids).order_by("pk"):
        if cs.type not in RAW_TYPES:
            skipped.append(Skipped(id=cs.pk, reason="Not a raw calibration set."))
        elif cs.built.filter(state__in=["queued", "running"]).exists():
            skipped.append(Skipped(id=cs.pk, reason="Already building."))
        else:
            cal.request_build(cs, force=body.force, priority=PRIORITY_BULK + BUILD_PRIORITY.get(cs.type, 0))
            queued += 1
    return BuildManyOut(queued=queued, skipped=skipped)


# ---- datasets --------------------------------------------------------------------------------------------------
class DatasetsIn(Schema):
    dataset_ids: list[int]


class RegradeManyOut(Schema):
    queued: int


@router.post("/bulk/datasets/regrade", response=RegradeManyOut)
def regrade_many(request, body: DatasetsIn):
    """Re-grade these datasets with the current thresholds, in one job. Human verdicts are kept."""
    from .grading import regrade_datasets

    _may_change(request, body.dataset_ids)
    ids = sorted(Dataset.objects.filter(pk__in=body.dataset_ids).values_list("pk", flat=True))
    if ids:
        enqueue(regrade_datasets, ids, dedupe_key=f"regrade:{','.join(map(str, ids))}")
    return RegradeManyOut(queued=len(ids))


class StackManyOut(Schema):
    started: int
    master_ids: list[int]
    skipped: list[Skipped]


@router.post("/bulk/datasets/stack", response=StackManyOut)
def stack_many(request, body: DatasetsIn):
    """Start a master for each dataset with the default rule (accepted and down-weighted subs, every night). A
    dataset that can't be stacked is skipped, with the reason."""
    _may_change(request, body.dataset_ids)
    ids, skipped = [], []
    for ds in Dataset.objects.filter(pk__in=body.dataset_ids).order_by("pk"):
        try:
            ids.append(svc.start(ds, None, "default", request.user).pk)
        except ValueError as e:
            skipped.append(Skipped(id=ds.pk, reason=str(e)))
    return StackManyOut(started=len(ids), master_ids=ids, skipped=skipped)


class DatasetsMoveIn(Schema):
    dataset_ids: list[int]
    collection_id: int | None = None  # none: out of their collections


class DatasetsMoveOut(Schema):
    moved: int
    change_id: int | None = None  # undo it with POST /changes/{id}/undo


@router.post("/bulk/datasets/move", response=DatasetsMoveOut)
def move_many(request, body: DatasetsMoveIn):
    """Move these datasets into another collection (or out of their collections). They leave any project of the
    collection they came from; undoing puts them back in both."""
    from apps.catalogue.services.library import refresh_objects

    _may_change(request, body.dataset_ids)
    to = get_object_or_404(Collection, pk=body.collection_id) if body.collection_id is not None else None
    chosen = Dataset.objects.filter(pk__in=body.dataset_ids)
    chosen = chosen.exclude(collection=to) if to else chosen.exclude(collection__isnull=True)
    rows = list(chosen.values_list("pk", "collection_id", "project_id", "project_position"))
    if not rows:
        return DatasetsMoveOut(moved=0)
    Dataset.objects.filter(pk__in=[r[0] for r in rows]).update(
        collection=to, project=None, project_position=None
    )
    for c in Collection.objects.filter(pk__in={r[1] for r in rows if r[1]} | ({to.pk} if to else set())):
        refresh_objects(c)
    n = len(rows)
    what = f"{n:,} dataset{'s' if n != 1 else ''}"
    change = record(
        request.user,
        Change.Kind.MOVE,
        f"Moved {what} to {to.name}" if to else f"Took {what} out of their collection",
        n,
        to=to.pk if to else None,
        previous={str(pk): [col, project, pos] for pk, col, project, pos in rows},
    )
    return DatasetsMoveOut(moved=n, change_id=change.pk)
