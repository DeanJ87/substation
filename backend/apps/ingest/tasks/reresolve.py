"""ingest.reresolve (T075): after a path pattern is added, changed or removed, re-resolve the frames it could
affect, from stored header values (no file is read), regrouping datasets as values change."""

from __future__ import annotations

from apps.catalogue.models import Copy, Dataset, Frame, FrameStatus
from apps.catalogue.services.tracking import touch_dataset
from substation.tasks import PRIORITY_BULK, report_progress, station_task

from ..resolve import resolve_frame

BIN = [FrameStatus.BINNED, FrameStatus.DELETED]  # in the bin, or gone (spec 011): not re-read
BATCH = 500


def keep_collections(moves: list[tuple[Dataset | None, Dataset | None]]) -> None:
    """A dataset made by a regroup (a merged name or rig) belongs to the collection its subs came from: merging
    names in a collection left every regrouped dataset outside it, and the collection looked emptied (2026-10-14)."""
    from collections import Counter

    came: dict[int, Counter] = {}
    for old, new in moves:
        if old is not None and new is not None and old.pk != new.pk and old.collection_id:
            came.setdefault(new.pk, Counter())[old.collection_id] += 1
    for pk, counts in came.items():
        Dataset.objects.filter(pk=pk, collection__isnull=True).update(
            collection_id=counts.most_common(1)[0][0]
        )


def settle(touched: dict[int, Dataset], before: dict[int, int]) -> None:
    """After subs regroup (a rig or name merge, a pattern change): recount every dataset touched. One left empty
    hands its stacks to the dataset that now holds most of their subs, marked stale with the reason, and goes; one
    that gained subs has its current stacks marked stale and its sessions re-graded, since each sub is compared
    with its own session's median."""
    from django.db.models import Count, Max

    from apps.processing.grading import grade_session
    from apps.processing.models import Master, MasterMember

    for d in touched.values():
        touch_dataset(d)
    for d in touched.values():
        if d.sub_count == 0:
            for m in Master.objects.filter(dataset=d).order_by("version"):
                home = (
                    Frame.objects.filter(pk__in=MasterMember.objects.filter(master=m).values("frame_id"))
                    .exclude(dataset=None)
                    .values("dataset")
                    .annotate(n=Count("pk"))
                    .order_by("-n")
                    .first()
                )
                if home is None:
                    continue
                top = Master.objects.filter(dataset_id=home["dataset"]).aggregate(v=Max("version"))["v"] or 0
                Master.objects.filter(pk=m.pk).update(
                    dataset_id=home["dataset"],
                    version=top + 1,
                    state="stale" if m.state == "current" else m.state,
                    state_reason=f"Merged from {d.display_name} v{m.version}.",
                )
            if not Master.objects.filter(dataset=d).exists():
                d.delete()
            else:
                Dataset.objects.filter(pk=d.pk).update(collection=None)
        elif d.sub_count > before.get(d.pk, d.sub_count):
            Master.objects.filter(dataset=d, state="current").update(
                state="stale", state_reason="New subs after a merge."
            )
            for night_id in set(
                Frame.objects.filter(dataset=d, frame_type="light").values_list("night_id", flat=True)
            ):
                grade_session(d.pk, night_id)


@station_task(queue_name="ingest", priority=PRIORITY_BULK, max_attempts=3)
def reresolve_library(library_id: int | None) -> dict:
    copies = Copy.objects.filter(present=True)
    if library_id is not None:
        copies = copies.filter(library_id=library_id)
    shas = list(
        Frame.objects.filter(pk__in=copies.values("frame_id"))
        .exclude(status__in=[FrameStatus.PENDING, FrameStatus.ERROR, FrameStatus.IGNORED, *BIN])
        .values_list("pk", flat=True)
    )
    touched: dict[int, Dataset] = {}
    before: dict[int, int] = {}
    moves: list = []
    for i in range(0, len(shas), BATCH):
        for frame in Frame.objects.filter(pk__in=shas[i : i + BATCH]):
            old, new = resolve_frame(frame)
            moves.append((old, new))
            for d in (old, new):
                if d is not None:
                    touched[d.pk] = d
                    before.setdefault(d.pk, d.sub_count)
        report_progress(min(1.0, (i + BATCH) / max(1, len(shas))), f"re-reading {len(shas)} frames' values")
    keep_collections(moves)
    settle(touched, before)
    return {"frames": len(shas), "datasets": len(touched)}


@station_task(queue_name="ingest", priority=PRIORITY_BULK + 20, max_attempts=3)
def reresolve_targets(names: list[str]) -> dict:
    """After target names are merged: regroup the frames that carry them, then settle the datasets touched."""
    touched: dict[int, Dataset] = {}
    before: dict[int, int] = {}
    moves: list = []
    for frame in Frame.objects.filter(target__in=names).exclude(
        status__in=[FrameStatus.PENDING, FrameStatus.ERROR, FrameStatus.IGNORED, *BIN]
    ):
        old, new = resolve_frame(frame)
        moves.append((old, new))
        for d in (old, new):
            if d is not None:
                touched[d.pk] = d
                before.setdefault(d.pk, d.sub_count)
    keep_collections(moves)
    settle(touched, before)
    return {"datasets": len(touched)}


def header_from_snapshot(frame: Frame):  # noqa: ANN201
    """The integration image's header as stored at cataloguing (no file is read)."""
    from ..headers import ImageHeader, Keyword

    snap = frame.headers.filter(image_index=frame.integration_index or 0).first() or frame.headers.first()
    if snap is None:
        return None
    img = ImageHeader(
        index=snap.image_index,
        image_id=snap.image_id,
        geometry=tuple(int(g) for g in snap.geometry.split(":") if g.isdigit()),
        sample_format=snap.sample_format,
        image_type="",
    )
    img.keywords = {
        k: Keyword(v.get("value"), v.get("comment", "")) for k, v in (snap.keywords or {}).items()
    }
    img.properties = snap.properties or {}
    return img


@station_task(queue_name="ingest", priority=PRIORITY_BULK, max_attempts=2)
def reextract_headers(library_id: int | None = None) -> dict:
    """Re-run header extraction from stored headers after the extraction rules improve, then re-resolve."""
    from ..fields import extract
    from ..resolve import record_header_values

    frames = Frame.objects.exclude(
        status__in=[FrameStatus.PENDING, FrameStatus.ERROR, FrameStatus.IGNORED, *BIN]
    )
    if library_id is not None:
        frames = frames.filter(copies__library_id=library_id).distinct()
    shas = list(frames.values_list("pk", flat=True))
    touched: dict[int, Dataset] = {}
    for i in range(0, len(shas), BATCH):
        for frame in Frame.objects.filter(pk__in=shas[i : i + BATCH]).prefetch_related("headers"):
            img = header_from_snapshot(frame)
            if img is None:
                continue
            record_header_values(frame, extract(img))
            old, new = resolve_frame(frame)
            for d in (old, new):
                if d is not None:
                    touched[d.pk] = d
        report_progress(
            min(1.0, (i + BATCH) / max(1, len(shas))), f"re-reading stored headers of {len(shas)} frames"
        )
    for d in touched.values():
        touch_dataset(d)
    return {"frames": len(shas)}
