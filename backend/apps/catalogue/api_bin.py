"""The bin (spec 011): bin and restore files, list what's in the bin, run the daily tidy now. On the catalogue
router. No `from __future__ import annotations` here: see substation.api."""

from datetime import datetime

from django.db.models import Sum
from django.shortcuts import get_object_or_404

from apps.catalogue.api import router
from apps.catalogue.models import Copy, Frame, FrameStatus, FrameType, IgnoreRule
from apps.catalogue.services.binning import QUARANTINE, bin_frames, bin_settings, restore_frames
from substation.api import ApiError, Schema, admin_required


class BinIn(Schema):
    sha256s: list[str]
    reason: str = ""


class BinOut(Schema):
    binned: int = 0
    moved: int = 0  # into the library's quarantine, deleted after the purge period
    hidden: int = 0  # in a library SubStation may not delete in: only hidden
    restored: int = 0
    not_restored: int = 0


class BinRow(Schema):
    sha256: str
    name: str
    frame_type: str
    target: str | None
    reason: str
    by: str
    binned_at: datetime | None
    purge_after: datetime | None  # none: only hidden, never deleted
    size_bytes: int


class BinListOut(Schema):
    total: int
    moved: int
    hidden: int
    bytes_in_quarantine: int
    deleted: int  # files already deleted for good (their records remain)
    auto_bin_rejected_days: int
    purge_after_days: int
    rows: list[BinRow]


def _no_viewers(request) -> None:  # noqa: ANN001
    from apps.accounts.roles import is_viewer

    if is_viewer(request.user):
        raise ApiError(403, "forbidden", "Read-only users can't bin files.")


def _by(request) -> str:  # noqa: ANN001
    return getattr(request.user, "username", "") or ""


@router.post("/bin", response=BinOut)
def bin_files(request, body: BinIn):
    """Bin files by hand: moved to their library's quarantine where SubStation may delete, else hidden."""
    _no_viewers(request)
    if not body.sha256s:
        raise ApiError(422, "invalid", "Choose at least one file.")
    return BinOut(**bin_frames(body.sha256s, body.reason.strip() or "Binned by hand", by=_by(request)))


@router.post("/bin/restore", response=BinOut)
def restore_files(request, body: BinIn):
    _no_viewers(request)
    return BinOut(**restore_frames(body.sha256s))


@router.post("/datasets/{id}/bin-rejected", response=BinOut)
def bin_rejected(request, id: int):  # noqa: A002
    """Every rejected sub in the dataset (by the grader or by hand), unless marked Keep."""
    from apps.processing.effective import effective
    from apps.processing.models import MachineGrade

    _no_viewers(request)
    shas = []
    for f in Frame.objects.filter(
        dataset_id=id, frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED
    ).prefetch_related("verdicts"):
        try:
            g = f.grade
        except MachineGrade.DoesNotExist:
            g = None
        if effective(f, list(f.verdicts.all()), g).verdict == "reject":
            shas.append(f.pk)
    return BinOut(**bin_frames(shas, "Rejected; binned by hand", by=_by(request)))


@router.post("/ignore-rules/{id}/bin", response=BinOut)
def bin_ignored(request, id: int):  # noqa: A002
    """The files an ignore rule sets aside (e.g. 8-bit captures), into the bin."""
    from apps.catalogue.services.ignore import frames_for_rule

    _no_viewers(request)
    rule = get_object_or_404(IgnoreRule, pk=id)
    shas = [f.pk for f in frames_for_rule(rule) if f.status == FrameStatus.IGNORED]
    return BinOut(**bin_frames(shas, rule.note or "Ignored, then binned", by=_by(request)))


@router.get("/bin", response=BinListOut)
def list_bin(request, offset: int = 0, limit: int = 100):
    binned = Frame.objects.filter(status=FrameStatus.BINNED)
    rows = []
    for f in binned.order_by("purge_after", "-binned_at")[offset : offset + min(limit, 500)]:
        c = Copy.objects.filter(frame=f).order_by("-present").first()
        name = (c.binned_from or c.rel_path).rsplit("/", 1)[-1] if c else f.sha256[:12]
        rows.append(
            BinRow(
                sha256=f.pk,
                name=name,
                frame_type=f.frame_type,
                target=f.target,
                reason=f.bin_reason,
                by=f.binned_by,
                binned_at=f.binned_at,
                purge_after=f.purge_after,
                size_bytes=f.size_bytes,
            )
        )
    s = bin_settings()
    q = Copy.objects.filter(
        frame__status=FrameStatus.BINNED, present=True, rel_path__startswith=f"{QUARANTINE}/"
    )
    return BinListOut(
        total=binned.count(),
        moved=binned.exclude(purge_after=None).count(),
        hidden=binned.filter(purge_after=None).count(),
        bytes_in_quarantine=q.aggregate(n=Sum("st_size"))["n"] or 0,
        deleted=Frame.objects.filter(status=FrameStatus.DELETED).count(),
        auto_bin_rejected_days=int(s.get("auto_bin_rejected_days", 30)),
        purge_after_days=int(s.get("purge_after_days", 30)),
        rows=rows,
    )


@router.post("/bin/tidy", response={202: dict})
@admin_required
def tidy_now(request):
    """Run the daily tidy now: bin long-rejected subs, delete what's past its date."""
    from apps.ingest.tasks.bin import tidy_bin
    from substation.tasks import enqueue

    enqueue(tidy_bin, dedupe_key="tidy-bin")
    return 202, {"message": "Tidying the bin."}
