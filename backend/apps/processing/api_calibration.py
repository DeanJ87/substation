"""Calibration set inspection and master building (spec 002 US2, US3; on the catalogue router). No
`from __future__ import annotations` here: see substation.api."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404

from apps.catalogue.api import router
from apps.catalogue.models import CalibrationSet, Copy, Frame, FrameStatus, FrameType
from substation.api import Schema
from substation.events.emit import emit
from substation.tasks import PRIORITY_BULK, enqueue

from . import calibration as svc
from .calibration import BUILD_PRIORITY, RAW_TYPES  # noqa: E402
from .models import BuiltMaster, CalibrationQA


class QAFrameOut(Schema):
    sha256: str
    file: str
    date_obs_utc: datetime | None
    verdict: str | None
    override: str | None
    reason: str
    stats: dict
    has_thumb: bool


class BuiltOut(Schema):
    id: int
    state: str
    reason: str
    method: str
    frames_used: int
    frames_excluded: list[dict]
    calibrated_with: str | None
    master_sha256: str | None
    report: dict
    has_preview: bool
    has_motes: bool
    has_comparison: bool
    error: str | None
    engine_version: str
    created_at: datetime
    finished_at: datetime | None


class SetDetailOut(Schema):
    id: int
    type: str
    camera: str
    telescope: str | None
    filter: str | None
    exptime_s: float
    gain: int | None
    offset: int | None
    set_temp_c: float | None
    session_start_utc: datetime
    frame_count: int
    qa_checked: int
    qa_counts: dict[str, int]
    calibrator: str | None
    calibrator_note: str
    frames: list[QAFrameOut]
    builds: list[BuiltOut]


class BuildIn(Schema):
    force: bool = False


class QAOverrideIn(Schema):
    sha256s: list[str]
    verdict: Literal["pass", "reject"] | None = None


class QueuedOut(Schema):
    queued: int


def _file(f: Frame) -> str:
    c = Copy.objects.filter(frame=f, present=True).first()
    return Path(c.rel_path).name if c else f.sha256[:12]


def _built_out(b: BuiltMaster) -> BuiltOut:
    prev = Path(b.preview_path) if b.preview_path else None
    motes = prev.with_name(prev.stem + "_motes.jpg") if prev else None
    return BuiltOut(
        id=b.pk,
        state=b.state,
        reason=b.reason,
        method=b.method,
        frames_used=b.frames_used,
        frames_excluded=b.frames_excluded or [],
        calibrated_with=_file(b.calibrated_with) if b.calibrated_with else None,
        master_sha256=b.frame_id,
        report={k: v for k, v in (b.report or {}).items() if k != "force"},
        has_preview=bool(prev and prev.exists()),
        has_motes=bool(motes and motes.exists()),
        has_comparison=bool(prev and prev.with_name(prev.stem + "_cmp.jpg").exists()),
        error=b.error,
        engine_version=b.engine_version or "",
        created_at=b.created_at,
        finished_at=b.finished_at,
    )


@router.get("/calibration-sets/{id}/detail", response=SetDetailOut)
def set_detail(request, id: int):  # noqa: A002
    cs = get_object_or_404(CalibrationSet, pk=id)
    frames = list(
        Frame.objects.filter(calibration_set=cs, status=FrameStatus.CATALOGUED).order_by("date_obs_utc")
    )
    qa = {q.frame_id: q for q in CalibrationQA.objects.filter(frame__in=frames)}
    counts: dict[str, int] = {}
    out = []
    for f in frames:
        q = qa.get(f.sha256)
        eff = (q.override or q.verdict) if q else None
        if eff:
            counts[eff] = counts.get(eff, 0) + 1
        out.append(
            QAFrameOut(
                sha256=f.sha256,
                file=_file(f),
                date_obs_utc=f.date_obs_utc,
                verdict=q.verdict if q else None,
                override=(q.override or None) if q else None,
                reason=q.reason if q else "",
                stats=q.stats if q else {},
                has_thumb=bool(q and q.thumb_path and Path(q.thumb_path).is_file()),
            )
        )
    cal, note = None, ""
    if cs.type == FrameType.FLAT:
        c = svc.flat_calibrator(cs)
        if c is None:
            note = (
                f"No master dark flat at {cs.exptime_s:g} s or master bias for {cs.camera or 'this camera'}."
            )
        else:
            cal = _file(c)
            note = "master bias" if c.frame_type == FrameType.MASTER_BIAS else "master dark flat"
    tele = frames[0].telescope if frames else None
    return SetDetailOut(
        id=cs.pk,
        type=cs.type,
        camera=cs.camera,
        telescope=tele,
        filter=cs.filter_norm,
        exptime_s=cs.exptime_s,
        gain=cs.gain,
        offset=cs.offset,
        set_temp_c=cs.set_temp_c,
        session_start_utc=cs.session_start_utc,
        frame_count=len(frames),
        qa_checked=len(qa),
        qa_counts=counts,
        calibrator=cal,
        calibrator_note=note,
        frames=out,
        builds=[_built_out(b) for b in cs.built.order_by("-created_at")[:10]],
    )


@router.post("/calibration-sets/{id}/qa", response=QueuedOut)
def run_qa(request, id: int):  # noqa: A002
    cs = get_object_or_404(CalibrationSet, pk=id)
    enqueue(svc.qa_calibration_set, cs.pk, dedupe_key=f"calqa:{cs.pk}", priority=PRIORITY_BULK + 10)
    return QueuedOut(queued=1)


@router.post("/calibration-sets/{id}/build", response=BuiltOut)
def build(request, id: int, body: BuildIn):  # noqa: A002
    cs = get_object_or_404(CalibrationSet, pk=id)
    return _built_out(
        svc.request_build(cs, force=body.force, priority=PRIORITY_BULK + BUILD_PRIORITY.get(cs.type, 0))
    )


@router.post("/calibration-sets/build-missing", response=QueuedOut)
def build_missing(request):
    """Queue a build for every raw set of 3+ frames with no master built, queued or running from it."""
    sets = CalibrationSet.objects.filter(type__in=RAW_TYPES, frame_count__gte=3).exclude(
        built__state__in=["queued", "running", "done"]
    )
    n = 0
    for cs in sets.distinct():
        svc.request_build(cs, priority=PRIORITY_BULK + BUILD_PRIORITY.get(cs.type, 0))
        n += 1
    return QueuedOut(queued=n)


@router.post("/calibration-qa/override", response=QueuedOut)
def qa_override(request, body: QAOverrideIn):
    n = CalibrationQA.objects.filter(frame_id__in=body.sha256s).update(override=body.verdict or "")
    emit("calibration.updated", {})
    return QueuedOut(queued=n)


@router.get("/calibration-qa/{sha256:sha256}/thumb", response={200: None, 404: None})
def qa_thumb(request, sha256: str):
    q = CalibrationQA.objects.filter(frame_id=sha256).first()
    if q is None or not q.thumb_path or not Path(q.thumb_path).is_file():
        return HttpResponse(status=404)
    return FileResponse(Path(q.thumb_path).open("rb"), content_type="image/jpeg")


@router.get("/built-masters/{id}/preview", response={200: None, 404: None})
def built_preview(request, id: int, kind: Literal["screen", "thumb", "motes", "cmp"] = "screen"):  # noqa: A002
    b = get_object_or_404(BuiltMaster, pk=id)
    p = Path(b.preview_path) if b.preview_path else None
    if p is not None and kind != "screen":
        p = p.with_name(p.stem + {"thumb": "_t.jpg", "motes": "_motes.jpg", "cmp": "_cmp.jpg"}[kind])
    if p is None or not p.exists():
        return HttpResponse(status=404)
    return FileResponse(p.open("rb"), content_type="image/jpeg")


class SetFilterIn(Schema):
    filter: str


class SetFilterOut(Schema):
    updated: int
    set_id: int | None  # where the flats are now (a set of that filter)


@router.post("/calibration-sets/{id}/filter", response=SetFilterOut)
def set_flat_filter(request, id: int, body: SetFilterIn):  # noqa: A002
    """Say which filter these flats were taken through (a camera with no filter wheel records none, so a Duo NB
    night's flats read as plain OSC). Stored as your correction for each flat, which regroups them with flats of
    that filter so that filter's lights find them. Clear the box to go back to what the headers say."""
    from apps.accounts.roles import is_viewer
    from apps.catalogue.services.corrections import CorrectionError, set_value
    from substation.api import ApiError

    from .tasks import rematch_lights

    if is_viewer(request.user):
        raise ApiError(403, "forbidden", "Read-only users can't change frames.")
    cs = get_object_or_404(CalibrationSet, pk=id)
    if cs.type != "flat":
        raise ApiError(422, "invalid", "Only flats are taken through a filter.")
    shas = list(Frame.objects.filter(calibration_set=cs).values_list("sha256", flat=True))
    try:
        n = set_value(shas, "filter", body.filter.strip() or None, request.user)
    except CorrectionError as e:
        raise ApiError(422, "invalid_value", str(e)) from None
    now = Frame.objects.filter(pk__in=shas).values_list("calibration_set_id", flat=True).first()
    enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True)  # lights of that filter can use them now
    return SetFilterOut(updated=n, set_id=now)
