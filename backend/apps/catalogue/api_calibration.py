"""Calibration library endpoints (T097; contracts/openapi.yaml). No `from __future__ import annotations` here:
see substation.api."""

from datetime import date, datetime

from django.shortcuts import get_object_or_404
from ninja import Query

from substation.api import ApiError, Schema

from .api import FrameSummaryOut, frame_summary, router
from .scope import Scope, apply, without
from .services.calibration_queries import calibration_sets, masters, value_sources


class CalibrationSetOut(Schema):
    id: int
    type: str
    camera: str
    filter: str | None
    exptime_s: float
    gain: int | None
    offset: int | None
    binning: str
    set_temp_c: float | None
    session_start_utc: datetime
    session_end_utc: datetime
    night: date | None
    frame_count: int
    filter_blocks: dict[str, int]
    built_state: str | None = None
    built_id: int | None = None


class MasterOut(FrameSummaryOut):
    camera: str | None
    gain: int | None
    offset: int | None
    set_temp_c: float | None
    sources: dict[str, str | None]
    missing: list[str]
    telescope: str | None = None
    frames: int | None = None
    built_set_id: int | None = None
    used_datasets: int = 0
    used_sessions: int = 0
    state: str = ""
    valid_from: date | None = None  # 002 C13: nights outside the window don't use this master
    valid_to: date | None = None
    thumb: str | None = None  # built masters' preview; any master opens at 100% on request


class MasterWindowOut(Schema):
    sha256: str
    valid_from: date | None
    valid_to: date | None


class BlockingOut(Schema):
    dataset_id: int
    dataset: str
    collection: str | None
    rig: str | None
    night: date | None
    subs: int
    waiting_for: str
    needs: list[str]


def _usage() -> dict[str, tuple[set, set]]:
    """Master sha → (datasets, (dataset, night) sessions) from the lights matched to it."""
    from apps.processing.models import CalibrationMatch

    use: dict[str, tuple[set, set]] = {}
    for dark, flat, ds, night in CalibrationMatch.objects.filter(state="matched").values_list(
        "dark_id", "flat_id", "frame__dataset_id", "frame__night_id"
    ):
        for m in (dark, flat):
            if m:
                a, b = use.setdefault(m, (set(), set()))
                a.add(ds)
                b.add((ds, night))
    return use


def _state(f, used: int, newer: bool, present: bool) -> str:  # noqa: ANN001
    """002-DR-03: Current, Kept for <year> data, Missing or Unused · <age>."""
    if not present:
        return "Missing"
    if not used:
        age = (datetime.now(f.date_obs_utc.tzinfo) - f.date_obs_utc).days if f.date_obs_utc else None
        return "Unused" + (f" · {age // 30} months" if age and age >= 60 else f" · {age} days" if age else "")
    if newer and f.date_obs_utc:
        return f"Kept for {f.date_obs_utc.year} data"
    return "Current"


def _built(cs) -> dict:  # noqa: ANN001
    b = cs.built.order_by("-created_at").first()
    return {"built_state": b.state, "built_id": b.pk} if b else {}


@router.get("/calibration-sets", response=list[CalibrationSetOut])
def list_calibration_sets(
    request,
    scope: Query[Scope],
    type: str | None = None,  # noqa: A002
    night: date | None = None,
):
    """Raw calibration sets in the shared scope (spec 018): nights, place, camera, filter, a rig (its camera) and
    free text (type, filter, camera, or a date as search reads it). `night` is the older name for `date`. Not paged:
    the Calibration page groups every set by night, and there are hundreds, not thousands."""
    return [
        CalibrationSetOut(
            id=cs.pk,
            type=cs.type,
            camera=cs.camera,
            filter=cs.filter_norm,
            exptime_s=cs.exptime_s,
            gain=cs.gain,
            offset=cs.offset,
            binning=f"{cs.xbin}x{cs.ybin}",
            set_temp_c=cs.set_temp_c,
            session_start_utc=cs.session_start_utc,
            session_end_utc=cs.session_end_utc,
            night=cs.night.date if cs.night else None,
            frame_count=cs.frame_count,
            filter_blocks=cs.filter_blocks or {},
            **_built(cs),
        )
        for cs in apply(calibration_sets(type, night), scope, "set")
    ]


@router.get("/masters", response=list[MasterOut])
def list_masters(request, scope: Query[Scope]):
    """Masters in the shared scope (spec 018). A master built here has no night of its own but the night its frames
    were shot, so the nights are compared with the night shown, after the rest of the scope narrows the query."""
    from apps.processing.models import BuiltMaster, MasterWindow

    use = _usage()
    built = {
        b.frame_id: b
        for b in BuiltMaster.objects.filter(state="done")
        .exclude(frame=None)
        .select_related("calibration_set__night")
    }
    windows = {w.frame_id: w for w in MasterWindow.objects.all()}
    rows = list(masters())
    # the newest master of each kind (type, camera, telescope, filter, exposure) is the current one
    newest: dict[tuple, datetime] = {}
    for f in rows:
        k = (f.frame_type, f.camera, f.telescope, f.filter_norm, f.exptime_s)
        if f.date_obs_utc and (k not in newest or f.date_obs_utc > newest[k]):
            newest[k] = f.date_obs_utc
    out = []
    for f in apply(masters(), without(scope, "date", "date_from", "date_to"), "master"):
        sources = value_sources(f, ("gain", "offset", "set_temp", "ccd_temp", "exptime", "filter"))
        temp_missing = sources["set_temp"] is None and sources["ccd_temp"] is None
        missing = [k for k in ("gain", "offset") if sources[k] is None] + (
            ["temperature"] if temp_missing else []
        )
        ds, sess = use.get(f.sha256, (set(), set()))
        b = built.get(f.sha256)
        present = any(c.present for c in f.copies.all())
        k = (f.frame_type, f.camera, f.telescope, f.filter_norm, f.exptime_s)
        summary = frame_summary(f).dict()
        if summary.get("night") is None and b is not None:
            # a master built here has no night of its own: it's the night its frames were shot (owner 2026-10-11)
            cs = b.calibration_set
            summary["night"] = (
                cs.night.date if cs.night else (cs.session_start_utc.date() if cs.session_start_utc else None)
            )
        out.append(
            MasterOut(
                **summary,
                camera=f.camera,
                gain=f.gain,
                offset=f.offset,
                set_temp_c=f.set_temp_c if f.set_temp_c is not None else f.ccd_temp_c,
                sources=sources,
                missing=missing,
                telescope=f.telescope,
                frames=b.frames_used if b else None,
                built_set_id=b.calibration_set_id if b else None,
                used_datasets=len(ds),
                used_sessions=len(sess),
                valid_from=windows[f.sha256].valid_from if f.sha256 in windows else None,
                valid_to=windows[f.sha256].valid_to if f.sha256 in windows else None,
                thumb=f"/api/v1/built-masters/{b.pk}/preview?kind=thumb" if b and b.preview_path else None,
                state=_state(
                    f,
                    len(sess),
                    bool(f.date_obs_utc and newest.get(k) and newest[k] > f.date_obs_utc),
                    present,
                ),
            )
        )
    return [m for m in out if _in_nights(m.night, scope)]


def _in_nights(night: date | None, scope: Scope) -> bool:
    if not (scope.date or scope.date_from or scope.date_to):
        return True
    if night is None:
        return False
    if scope.date and night != scope.date:
        return False
    return not (scope.date_from and night < scope.date_from) and not (scope.date_to and night > scope.date_to)


class WindowIn(Schema):
    valid_from: date | None = None
    valid_to: date | None = None


@router.put("/masters/{sha256}/window", response=MasterWindowOut)
def set_window(request, sha256: str, body: WindowIn):
    """Limit the nights a master may calibrate (002 C13); every light is matched again. Empty dates clear it."""
    from apps.processing.models import MasterWindow
    from apps.processing.tasks import rematch_lights
    from substation.tasks import enqueue

    from .models import Frame

    f = get_object_or_404(Frame, pk=sha256, frame_type__startswith="master_")
    if body.valid_from and body.valid_to and body.valid_from > body.valid_to:
        raise ApiError(422, "invalid", "The window must start on or before it ends.")
    if body.valid_from is None and body.valid_to is None:
        MasterWindow.objects.filter(frame=f).delete()
    else:
        MasterWindow.objects.update_or_create(
            frame=f,
            defaults={"valid_from": body.valid_from, "valid_to": body.valid_to, "set_by": request.user},
        )
    enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True)
    return MasterWindowOut(sha256=f.pk, valid_from=body.valid_from, valid_to=body.valid_to)


@router.get("/calibration/blocking", response=list[BlockingOut])
def blocking(request, scope: Query[Scope]):
    """What is stopping grading (002-DR-02): lights waiting for calibration, per dataset and night, with what
    SubStation is looking for."""
    from collections import Counter

    from apps.processing.models import CalibrationMatch

    from .models import Dataset

    n: Counter = Counter()
    from .scope import apply

    waiting = apply(
        CalibrationMatch.objects.filter(state="awaiting", frame__dataset__isnull=False), scope, "match"
    )
    for ds, night, reason in waiting.values_list("frame__dataset_id", "frame__night__date", "reason"):
        n[(ds, night, reason)] += 1
    names = {
        d.pk: d for d in Dataset.objects.filter(pk__in={k[0] for k in n}).select_related("rig", "collection")
    }
    out = []
    for (ds, night, reason), count in n.most_common():
        d = names[ds]
        needs = [
            x.strip().rstrip(".")
            for x in reason.removeprefix("Awaiting calibration:").split(";")
            if x.strip()
        ]
        kinds = [k for k in ("dark", "flat", "bias") if any(k in x for x in needs)]
        out.append(
            BlockingOut(
                dataset_id=ds,
                dataset=f"{d.rig.name if d.rig else d.camera} · {d.filter_norm}",
                night=night,
                subs=count,
                collection=d.collection.name if d.collection else d.target,
                rig=d.rig.name if d.rig else None,
                waiting_for=" and ".join(kinds) or "calibration",
                needs=needs,
            )
        )
    return out
