"""The bin (spec 011, owner 2026-10-13). A binned file leaves SubStation's view at once. Where its library allows it,
the file is moved to `.substation-quarantine/` at the library's root (same disk: instant, no extra space) and deleted
for good once its purge date passes; elsewhere it is only hidden. The frame's record, grade and measurements stay,
so history can still be counted.

Deleting only ever touches a file inside a library's quarantine folder, in a library marked "may delete"."""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Collection, Copy, Dataset, Frame, FrameStatus, FrameType

log = logging.getLogger(__name__)
QUARANTINE = ".substation-quarantine"


def bin_settings() -> dict:
    from apps.processing.config import processing_settings

    return processing_settings().get("bin", {})


def writable(lib) -> bool:  # noqa: ANN001
    """Moves and deletes happen only where the owner allowed them and the library is mounted writable."""
    from apps.libraries.access import is_writable

    return bool(lib.allow_delete) and is_writable(lib)


def in_quarantine(rel_path: str) -> bool:
    return rel_path.startswith(f"{QUARANTINE}/")


def _refresh(datasets: dict[int, Dataset]) -> None:
    from apps.catalogue.services.tracking import touch_dataset

    for d in datasets.values():
        touch_dataset(d)


def bin_frames(shas: list[str], reason: str, by: str = "") -> dict:
    """Put frames in the bin. Returns how many were binned, moved to quarantine and only hidden."""
    days = int(bin_settings().get("purge_after_days", 30))
    now = timezone.now()
    touched: dict[int, Dataset] = {}
    out = {"binned": 0, "moved": 0, "hidden": 0}
    for frame in Frame.objects.filter(pk__in=shas).exclude(
        status__in=[FrameStatus.BINNED, FrameStatus.DELETED]
    ):
        moved = False
        for c in Copy.objects.filter(frame=frame, present=True).select_related("library"):
            if not writable(c.library) or in_quarantine(c.rel_path):
                continue
            root = Path(c.library.mount_path)
            src, dst = root / c.rel_path, root / QUARANTINE / c.rel_path
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.rename(src, dst)
            except OSError as e:
                log.warning("Couldn't move %s to quarantine: %s", src, e)
                continue
            Copy.objects.filter(pk=c.pk).update(rel_path=f"{QUARANTINE}/{c.rel_path}", binned_from=c.rel_path)
            moved = True
        old = Dataset.objects.filter(pk=frame.dataset_id).first() if frame.dataset_id else None
        with transaction.atomic():
            Frame.objects.filter(pk=frame.pk).update(
                status=FrameStatus.BINNED,
                dataset=None,
                binned_dataset=old,
                binned_at=now,
                bin_reason=reason[:500],
                binned_by=by[:150],
                # only a file in quarantine is ever deleted; one that's only hidden stays
                purge_after=now + timedelta(days=days) if moved else None,
            )
        if old is not None:
            touched[old.pk] = old
        out["binned"] += 1
        out["moved" if moved else "hidden"] += 1
    _refresh(touched)
    return out


def restore_frames(shas: list[str]) -> dict:
    """Take frames out of the bin: files go back where they were, and each is a sub (or calibration frame) again."""
    from apps.catalogue.services.grouping import refresh_dataset
    from apps.ingest.resolve import resolve_frame

    out = {"restored": 0, "not_restored": 0}
    for frame in Frame.objects.filter(pk__in=shas, status=FrameStatus.BINNED):
        for c in Copy.objects.filter(frame=frame).exclude(binned_from=None).select_related("library"):
            root = Path(c.library.mount_path)
            src, dst = root / c.rel_path, root / str(c.binned_from)
            if dst.exists():  # something new is in its old place: leave the binned copy where it is
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.rename(src, dst)
            except OSError as e:
                log.warning("Couldn't restore %s: %s", src, e)
                continue
            Copy.objects.filter(pk=c.pk).update(rel_path=c.binned_from, binned_from=None)
        if Copy.objects.filter(frame=frame).exclude(binned_from=None).exists():
            out["not_restored"] += 1
            continue
        Frame.objects.filter(pk=frame.pk).update(
            status=FrameStatus.CATALOGUED,
            binned_at=None,
            bin_reason="",
            binned_by="",
            purge_after=None,
            binned_dataset=None,
        )
        frame.refresh_from_db()
        _old, new = resolve_frame(frame)
        refresh_dataset(new)
        out["restored"] += 1
    return out


def purge_due(now=None) -> dict:  # noqa: ANN001
    """Delete binned files whose purge date has passed. Only files inside a quarantine folder of a library that
    allows deleting are removed; the frame's record stays, marked deleted."""
    from apps.processing.models import SubMeasurement

    now = now or timezone.now()
    out = {"deleted": 0, "bytes": 0}
    for frame in Frame.objects.filter(status=FrameStatus.BINNED, purge_after__lte=now):
        gone = True
        for c in Copy.objects.filter(frame=frame, present=True).select_related("library"):
            if not in_quarantine(c.rel_path):
                gone = False  # a copy that was only hidden is never deleted
                continue
            if not writable(c.library):
                gone = False
                continue
            p = Path(c.library.mount_path) / c.rel_path
            try:
                size = p.stat().st_size if p.exists() else 0
                p.unlink(missing_ok=True)
            except OSError as e:
                log.warning("Couldn't delete %s: %s", p, e)
                gone = False
                continue
            out["bytes"] += size
            Copy.objects.filter(pk=c.pk).update(present=False, missing_since=now)
        if not gone:
            continue
        # SubStation's own working files for it go too; its measurements stay
        work = Path(settings.WORK_DIR)
        for m in SubMeasurement.objects.filter(frame=frame).exclude(calibrated_path=""):
            cal = Path(m.calibrated_path)
            if work in cal.parents:
                cal.unlink(missing_ok=True)
        Frame.objects.filter(pk=frame.pk).update(status=FrameStatus.DELETED, deleted_at=now)
        out["deleted"] += 1
    return out


def auto_bin(now=None) -> dict:  # noqa: ANN001
    """Bin lights that have been rejected for longer than the waiting period (Settings → Library → Bin), unless
    marked Keep. Rejected by the grader counts from its grading; by hand, from the verdict."""
    from apps.processing.effective import effective
    from apps.processing.models import MachineGrade

    days = int(bin_settings().get("auto_bin_rejected_days", 30))
    if days <= 0:
        return {"binned": 0}
    now = now or timezone.now()
    cutoff = now - timedelta(days=days)
    due = []
    from django.db.models import Q

    lights = (
        Frame.objects.filter(frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED)
        .filter(Q(grade__verdict="reject") | Q(verdicts__verdict="reject"))
        .distinct()
        .prefetch_related("verdicts")
    )
    for f in lights:
        try:
            g = f.grade
        except MachineGrade.DoesNotExist:
            g = None
        vs = list(f.verdicts.all())
        e = effective(f, vs, g)
        if e.verdict != "reject":
            continue
        if e.manual:
            since = max((v.created_at for v in vs), default=None)
            why = "rejected by hand"
        else:
            since = g.graded_at if g else None
            why = (g.reason if g else "") or "rejected"
        if since is None or since > cutoff:
            continue
        due.append((f.pk, f"Rejected for over {days} days: {why}"))
    from apps.processing.move_guard import check_collection

    # a build of its collection reads it: binned on a later tidy (spec 013, 2026-10-24)
    cols = dict(Frame.objects.filter(pk__in=[d[0] for d in due]).values_list("pk", "dataset__collection_id"))
    building = {c.pk for c in Collection.objects.filter(pk__in=set(cols.values())) if check_collection(c)}
    n = 0
    for sha, reason in due:
        if cols.get(sha) in building:
            continue
        n += bin_frames([sha], reason, by="auto")["binned"]
    return {"binned": n}


def tidy_due() -> bool:
    """Whether today's tidy hasn't run yet."""
    from apps.libraries.models import InstallationSettings

    p = InstallationSettings.load().processing or {}
    return p.get("bin_tidied_on") != timezone.localdate().isoformat()
