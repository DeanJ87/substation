"""Content tracking (US2): moves and renames, disappearances and reappearances. A frame is its content; copies
come and go without losing any decision attached to the frame (constitution II, III)."""

from __future__ import annotations

import os
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from substation.events.emit import emit

from ..models import (
    Copy,
    CopyEvent,
    CopyEventKind,
    Dataset,
    Frame,
    FrameStatus,
    ReconciliationItem,
    ReconciliationKind,
    ReconciliationStatus,
)
from .grouping import refresh_dataset
from .verdicts import apply_bad_prefix


def touch_dataset(ds: Dataset | None) -> None:
    """Recount a dataset (which also updates its state) and tell browsers."""
    if ds is None:
        return
    refresh_dataset(ds)
    emit(
        "dataset.updated",
        {
            "dataset_id": ds.pk,
            "sub_count": ds.sub_count,
            "integration_s": ds.integration_s,
            "state": ds.state,
        },
    )


def mark_present(frame: Frame) -> None:
    """A copy of this frame exists again: undo a missing status and resolve its item."""
    if frame.status != FrameStatus.MISSING:
        return
    if frame.catalogued_at is None:
        frame.status = FrameStatus.PENDING
    else:
        frame.status = FrameStatus.ERROR if frame.error else FrameStatus.CATALOGUED
    frame.save(update_fields=["status"])
    ReconciliationItem.objects.filter(
        frame=frame, kind=ReconciliationKind.FRAME_MISSING, status=ReconciliationStatus.OPEN
    ).update(
        status=ReconciliationStatus.RESOLVED, resolved_at=timezone.now(), resolution={"by": "reappeared"}
    )
    emit("frame.updated", {"sha256": frame.sha256, "fields": ["status"]})
    touch_dataset(frame.dataset)


def record_move(copy: Copy, new_rel: str, st: os.stat_result) -> None:
    """Same file object (device, inode, size, mtime) now at another path of the same library: a move or
    rename, recorded without re-hashing. Renaming to BAD_ is NINA's thumbs-down."""
    old = copy.rel_path
    now = timezone.now()
    with transaction.atomic():
        copy.rel_path = new_rel
        copy.is_bad_prefixed = os.path.basename(new_rel).startswith("BAD_")
        copy.st_dev, copy.st_ino, copy.st_size, copy.st_mtime_ns = (
            st.st_dev,
            st.st_ino,
            st.st_size,
            st.st_mtime_ns,
        )
        copy.present, copy.last_seen_at, copy.missing_since = True, now, None
        copy.save()
        kind = (
            CopyEventKind.RENAMED if os.path.dirname(old) == os.path.dirname(new_rel) else CopyEventKind.MOVED
        )
        CopyEvent.objects.create(
            kind=kind, frame=copy.frame, copy=copy, library=copy.library, details={"from": old, "to": new_rel}
        )
    emit("copy.moved", {"sha256": copy.frame_id, "from": old, "to": new_rel})
    frame = copy.frame
    if apply_bad_prefix(frame):
        touch_dataset(frame.dataset)
    mark_present(frame)


def _moved_to(c: Copy) -> Copy | None:
    """A copy of the same content that appeared after this one was last seen: where it moved to. (Used when
    the filesystem can't keep inode numbers across a rename, so the move was only found by hashing.)"""
    return (
        Copy.objects.filter(frame_id=c.frame_id, present=True, first_seen_at__gte=c.last_seen_at)
        .exclude(pk=c.pk)
        .order_by("first_seen_at")
        .first()
    )


def mark_copies_missing(copies: list[Copy]) -> None:
    now = timezone.now()
    for c in copies:
        if (new := _moved_to(c)) is not None:
            with transaction.atomic():
                frm = f"{c.library.name}/{c.rel_path}"
                logged = CopyEvent.objects.filter(copy=new, kind=CopyEventKind.COPIED).first()
                if logged is not None:
                    logged.kind, logged.details = CopyEventKind.MOVED, {"from": frm, "to": new.rel_path}
                    logged.save(update_fields=["kind", "details"])
                else:
                    CopyEvent.objects.create(
                        kind=CopyEventKind.MOVED,
                        frame_id=c.frame_id,
                        copy=new,
                        library_id=new.library_id,
                        details={"from": frm, "to": new.rel_path},
                    )
                c.delete()
            emit("copy.moved", {"sha256": c.frame_id, "from": frm, "to": new.rel_path})
            continue
        with transaction.atomic():
            Copy.objects.filter(pk=c.pk).update(present=False, missing_since=now)
            CopyEvent.objects.create(
                kind=CopyEventKind.MISSING,
                frame_id=c.frame_id,
                copy=c,
                library_id=c.library_id,
                details={"path": c.rel_path},
            )
        emit("copy.missing", {"sha256": c.frame_id, "path": c.rel_path})


def mark_frames_missing(library_id: int, before: datetime) -> int:
    """Frames whose every copy has been missing since before this sweep began, i.e. for at least one further
    complete sweep, are missing: the dataset needs reconciliation until they come back or are dealt with."""
    frames = (
        Frame.objects.filter(
            copies__library_id=library_id, copies__present=False, copies__missing_since__lt=before
        )
        .exclude(copies__present=True)
        .exclude(status__in=[FrameStatus.MISSING, FrameStatus.IGNORED])
        .distinct()
    )
    n = 0
    for frame in frames:
        path = frame.copies.order_by("-missing_since").values_list("rel_path", flat=True).first() or ""
        with transaction.atomic():
            frame.status = FrameStatus.MISSING
            frame.save(update_fields=["status"])
            ReconciliationItem.objects.get_or_create(
                kind=ReconciliationKind.FRAME_MISSING,
                frame=frame,
                field="",
                status=ReconciliationStatus.OPEN,
                defaults={
                    "dataset_id": frame.dataset_id,
                    "reason": f"{os.path.basename(path)} is no longer on disk, and no other copy of it is.",
                },
            )
        emit("frame.updated", {"sha256": frame.sha256, "fields": ["status"]})
        touch_dataset(frame.dataset)
        n += 1
    return n
