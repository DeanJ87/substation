"""Subs, sessions, grades, overrides, previews and review (specs 002, 003; v2 design D1–D4, A2).
Attached to the catalogue router (one router per prefix in Ninja). No `from __future__ import annotations`
here: see substation.api."""

import logging
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.catalogue.api import router
from apps.catalogue.models import (
    Copy,
    Dataset,
    Frame,
    FrameStatus,
    FrameType,
    UserVerdict,
    Verdict,
    VerdictSource,
)
from apps.catalogue.services.tracking import touch_dataset
from substation.api import ApiError, Schema
from substation.events.emit import emit
from substation.tasks import PRIORITY_LIVE, enqueue

from .annotation_schemas import AnnotationOut, AnnotationsOut
from .effective import effective, recount_grades
from .models import CalibrationMatch, MachineGrade, MatchState, MeasureState, PlateSolve, SubMeasurement

# Header keywords for conditions and capture (NINA and common writers)
COND = {
    "sqm": ("MPSAS", "SQM", "SKYQUAL"),
    "cloud": ("CLOUDCVR",),
    "humidity": ("HUMIDITY",),
    "ambient": ("AMBTEMP",),
    "dewpoint": ("DEWPOINT",),
    "skytemp": ("SKYTEMP",),
    "wind": ("WINDSPD",),
    "altitude": ("CENTALT", "OBJCTALT"),
    "airmass": ("AIRMASS",),
    "focpos": ("FOCPOS", "FOCUSPOS"),
    "foctemp": ("FOCTEMP", "FOCUSTEM"),
    "pierside": ("PIERSIDE",),
    "guiding": ("GUIDRMS", "GUIDERMS"),
}


def _kw(frame: Frame) -> dict:
    snaps = list(frame.headers.all())
    snap = next(
        (h for h in snaps if h.image_index == (frame.integration_index or 0)), snaps[0] if snaps else None
    )
    return {k: v.get("value") for k, v in (snap.keywords if snap else {}).items()}


def _num(kw: dict, names: tuple[str, ...]) -> float | None:
    for n in names:
        v = kw.get(n)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _text(kw: dict, names: tuple[str, ...]) -> str | None:
    for n in names:
        if kw.get(n) not in (None, ""):
            return str(kw[n])
    return None


class SubOut(Schema):
    sha256: str
    file: str
    night: date | None
    time: datetime | None
    exptime_s: float | None
    verdict: str | None
    machine_verdict: str | None
    source: str
    manual: bool
    weight: float
    reason: str | None
    provisional: bool
    near_threshold: bool
    measure_state: str | None
    awaiting_reason: str | None
    error: str | None
    stars: int | None
    fwhm_px: float | None
    fwhm_arcsec: float | None
    background: float | None
    eccentricity: float | None
    snr: float | None
    sqm: float | None
    altitude: float | None
    cloud: float | None
    focpos: float | None
    foctemp: float | None
    has_preview: bool
    decided_by: str | None = None
    decided_at: datetime | None = None
    guiding: float | None = None


def _file(f: Frame) -> str:
    c = next((c for c in f.copies.all() if c.present), None) or next(iter(f.copies.all()), None)
    return c.rel_path.rsplit("/", 1)[-1] if c else f.sha256[:12]


_RMS_IN_NAME = re.compile(
    # after "_" or a space only a decimal counts: NINA writes "_RMS_" when nothing was guided, and the frame number
    # after it ("_RMS_0001") must not be read as the RMS
    r"(?i)(?:^|[_\-\s.])(?:total[_\-\s]?)?(?:rms|guid(?:e|ing)?(?:[_\-\s]?rms)?)"
    r"(?:[\-=]?(\d+(?:\.\d+)?)|[_\s](\d+\.\d+))"
)


def rms_from_name(name: str) -> float | None:
    """Guiding RMS written into a file name ("…_RMS0.62_…", "…_guiding-0.8″_…"); owner 2026-10-10: the rig will
    carry it there from now on, as the capture software doesn't put it in the header."""
    m = _RMS_IN_NAME.search(name.rsplit("/", 1)[-1])
    return float(m.group(1) or m.group(2)) if m else None


def _condition_sources(kws: list[dict], subs: list) -> dict[str, str]:
    """Which keyword each recorded condition came from in this session (001-DR-08)."""
    out: dict[str, str] = {}
    for k in ("sqm", "ambient", "humidity", "cloud", "dewpoint", "guiding"):
        for name in COND[k]:
            if any(kw.get(name) is not None for kw in kws):
                out[k] = f"header {name}"
                break
    if "guiding" not in out and any(getattr(s, "guiding", None) is not None for s in subs):
        out["guiding"] = "file name"
    return out


def _guiding(f: Frame, kw: dict) -> tuple[float | None, str]:
    """(guiding RMS in arcsec, where it came from)"""
    v = _num(kw, COND["guiding"])
    if v is not None:
        return v, "header"
    v = rms_from_name(_file(f))
    return (v, "file name") if v is not None else (None, "header")


def _matched_on(f: Frame) -> list[dict]:
    """The values calibration matching used for this light and where each came from (002 C14, FR-008a)."""
    from apps.catalogue.services.calibration_queries import value_sources

    src = value_sources(
        f, ("exptime", "gain", "offset", "set_temp", "ccd_temp", "filter", "date_obs", "xbin")
    )
    temp_key = "set_temp" if f.set_temp_c is not None else "ccd_temp"
    temp = f.set_temp_c if f.set_temp_c is not None else f.ccd_temp_c
    rows = [
        ("Exposure", f"{f.exptime_s:g} s" if f.exptime_s is not None else None, src["exptime"]),
        ("Gain", f.gain, src["gain"]),
        ("Offset", f.offset, src["offset"]),
        ("Temperature", f"{temp:.1f} °C".replace("-", "−") if temp is not None else None, src[temp_key]),
        ("Filter", f.filter_norm, src["filter"]),
        ("Binning", f"{f.xbin or 1}×{f.ybin or 1}", src["xbin"]),
        ("Time", f.date_obs_utc.strftime("%-d %b %Y %H:%M UTC") if f.date_obs_utc else None, src["date_obs"]),
    ]
    return [
        {
            "label": a,
            "value": str(b) if b is not None else None,
            "source": c or ("not recorded" if b is None else ""),
        }
        for a, b, c in rows
    ]


def sub_out(f: Frame) -> SubOut:
    try:
        m: SubMeasurement | None = f.measurement
    except SubMeasurement.DoesNotExist:
        m = None
    try:
        g: MachineGrade | None = f.grade
    except MachineGrade.DoesNotExist:
        g = None
    try:
        cm: CalibrationMatch | None = f.calibration
    except CalibrationMatch.DoesNotExist:
        cm = None
    e = effective(f, list(f.verdicts.all()), g)
    kw = _kw(f)
    reason = g.reason if g else None
    if e.source == "nina":
        reason = "Rejected by you in NINA." + (f" Auto grade: {g.reason}" if g else "")
    return SubOut(
        sha256=f.sha256,
        file=_file(f),
        night=f.night.date if f.night else None,
        time=f.date_obs_utc,
        exptime_s=f.exptime_s,
        verdict=e.verdict,
        machine_verdict=g.verdict if g else None,
        source=e.source,
        manual=e.source == "override",
        weight=e.weight,
        reason=reason,
        provisional=bool(g and g.provisional),
        near_threshold=bool(g and g.near_threshold),
        measure_state=m.state if m else None,
        awaiting_reason=cm.reason if cm and cm.state == MatchState.AWAITING else None,
        error=m.error if m and m.state == MeasureState.FAILED else None,
        stars=m.stars if m else None,
        fwhm_px=m.fwhm_px if m else None,
        fwhm_arcsec=m.fwhm_arcsec if m else None,
        background=m.background if m else None,
        eccentricity=m.eccentricity if m else None,
        snr=m.snr if m else None,
        sqm=_num(kw, COND["sqm"]),
        altitude=_num(kw, COND["altitude"]),
        cloud=_num(kw, COND["cloud"]),
        focpos=_num(kw, COND["focpos"]),
        foctemp=_num(kw, COND["foctemp"]),
        guiding=_guiding(f, kw)[0],
        has_preview=bool(m and m.preview_path),
        **_decided(f, e),
    )


def _decided(f: Frame, e) -> dict:  # noqa: ANN001
    """Who made the human decision and when, for "You accepted it at …" (003-DR-09)."""
    if not e.manual:
        return {}
    from .effective import human

    h = human(list(f.verdicts.all()))
    if h is None:
        return {}
    who = (
        h.user.get_username() if h.user_id and h.user else ("NINA" if h.source == "nina_bad_prefix" else None)
    )
    return {"decided_by": who, "decided_at": h.created_at}


def _lights(**filters):  # noqa: ANN003, ANN202
    return (
        Frame.objects.filter(frame_type=FrameType.LIGHT, status=FrameStatus.CATALOGUED, **filters)
        .select_related("night", "measurement", "grade", "calibration")
        .prefetch_related("verdicts", "copies", "headers")
        .order_by("date_obs_utc")
    )


@router.get("/datasets/{id}/subs", response=list[SubOut])
def dataset_subs(request, id: int, night: date | None = None):  # noqa: A002
    get_object_or_404(Dataset, pk=id)
    qs = _lights(dataset_id=id)
    if night:
        qs = qs.filter(night__date=night)
    return [sub_out(f) for f in qs]


class Spread(Schema):
    median: float | None
    p10: float | None
    p90: float | None


class SessionOut(Schema):
    night: date
    sub_count: int
    integration_s: float
    accepted: int
    down: int
    rejected: int
    ungraded: int
    awaiting: int
    first_utc: datetime | None
    last_utc: datetime | None
    fwhm_arcsec: Spread
    fwhm_px: Spread
    stars: Spread
    background: Spread
    sqm: Spread
    conditions: dict[str, float | None]
    condition_sources: dict[str, str] = {}  # e.g. {"sqm": "header MPSAS", "guiding": "file name"} (001-DR-08)
    dark: str | None
    dark_note: str | None
    flat: str | None
    flat_note: str | None
    weak: bool
    flat_sha: str | None = None  # to look at the flat (owner 2026-10-11)
    flat_thumb: str | None = None


def _spread(values: list[float]) -> Spread:
    v = sorted(x for x in values if x is not None)
    if not v:
        return Spread(median=None, p10=None, p90=None)
    q = statistics.quantiles(v, n=10) if len(v) >= 2 else [v[0]] * 9
    return Spread(median=statistics.median(v), p10=q[0], p90=q[-1])


def frame_thumb(sha: str | None) -> str | None:
    """A thumbnail URL for a calibration frame or master: its built master's preview, else its QA thumbnail."""
    if not sha:
        return None
    from .models import BuiltMaster, CalibrationQA

    b = BuiltMaster.objects.filter(frame_id=sha).exclude(preview_path="").order_by("-pk").first()
    if b is not None:
        return f"/api/v1/built-masters/{b.pk}/preview?kind=thumb"
    if CalibrationQA.objects.filter(frame_id=sha).exclude(thumb_path="").exists():
        return f"/api/v1/calibration-qa/{sha}/thumb"
    return None


def master_label(f: Frame | None) -> str | None:
    if f is None:
        return None
    t = f.set_temp_c if f.set_temp_c is not None else f.ccd_temp_c
    when = f.night.date.strftime("%-d %b %Y") if f.night else None
    if f.frame_type == FrameType.MASTER_DARK:
        return f"Dark {f.exptime_s:g} s" + (f" {t:g} °C".replace("-", "−") if t is not None else "")
    if f.frame_type == FrameType.MASTER_FLAT:
        return f"Flat {f.filter_norm or ''}" + (f" · {when}" if when else "")
    return f.frame_type.replace("_", " ").capitalize()


@router.get("/datasets/{id}/sessions", response=list[SessionOut])
def dataset_sessions(request, id: int):  # noqa: A002
    get_object_or_404(Dataset, pk=id)
    by_night: dict[date, list[SubOut]] = defaultdict(list)
    frames = {f.sha256: f for f in _lights(dataset_id=id)}
    for f in frames.values():
        if f.night:
            by_night[f.night.date].append(sub_out(f))
    out = []
    for night, subs in sorted(by_night.items(), reverse=True):
        fs = [frames[s.sha256] for s in subs]
        matches = [getattr(f, "calibration", None) for f in fs if hasattr(f, "calibration")]
        darks = Counter(m.dark_id for m in matches if m and m.dark_id)
        flats = Counter(m.flat_id for m in matches if m and m.flat_id)
        dark = (
            Frame.objects.select_related("night").filter(pk=darks.most_common(1)[0][0]).first()
            if darks
            else None
        )
        flat = (
            Frame.objects.select_related("night").filter(pk=flats.most_common(1)[0][0]).first()
            if flats
            else None
        )
        mfor = {m.dark_id: m for m in matches if m}
        ffor = {m.flat_id: m for m in matches if m}
        kws = [_kw(f) for f in fs]
        verdicts = Counter(s.verdict for s in subs)
        times = [s.time for s in subs if s.time]
        out.append(
            SessionOut(
                night=night,
                sub_count=len(subs),
                integration_s=sum(s.exptime_s or 0 for s in subs),
                accepted=verdicts["accept"],
                down=verdicts["down"],
                rejected=verdicts["reject"],
                ungraded=verdicts[None],
                awaiting=sum(1 for s in subs if s.awaiting_reason),
                first_utc=min(times) if times else None,
                last_utc=max(times) if times else None,
                fwhm_arcsec=_spread([s.fwhm_arcsec for s in subs if s.fwhm_arcsec]),
                fwhm_px=_spread([s.fwhm_px for s in subs if s.fwhm_px]),
                stars=_spread([float(s.stars) for s in subs if s.stars]),
                background=_spread([s.background for s in subs if s.background is not None]),
                sqm=_spread([s.sqm for s in subs if s.sqm]),
                conditions={
                    k: (
                        statistics.median(v)
                        if (v := [x for kw in kws if (x := _num(kw, COND[k])) is not None])
                        else None
                    )
                    for k in ("sqm", "ambient", "humidity", "cloud", "dewpoint")
                }
                | {
                    "guiding": statistics.median(g)
                    if (g := [s.guiding for s in subs if s.guiding is not None])
                    else None
                },
                condition_sources=_condition_sources(kws, subs),
                dark=master_label(dark),
                dark_note=mfor[dark.pk].dark_note if dark else None,
                flat=master_label(flat),
                flat_note=ffor[flat.pk].flat_note if flat else None,
                weak=any(m.weak for m in matches if m),
                flat_sha=flat.pk if flat else None,
                flat_thumb=frame_thumb(flat.pk) if flat else None,
            )
        )
    return out


# ---- overrides --------------------------------------------------------------------------------------------
class VerdictIn(Schema):
    sha256s: list[str]
    verdict: Literal["accept", "keep", "reject", "auto"]
    note: str | None = None


class VerdictUpdatedOut(Schema):
    updated: int


@router.post("/frames/verdict", response=VerdictUpdatedOut)
def set_verdict(request, body: VerdictIn):
    from apps.accounts.roles import is_viewer

    if is_viewer(request.user):
        raise ApiError(403, "read_only", "Your account can't change verdicts.")
    if len(body.sha256s) > 10000:
        raise ApiError(422, "too_many", "Up to 10,000 subs at a time.")
    frames = list(Frame.objects.filter(pk__in=body.sha256s, frame_type=FrameType.LIGHT))
    UserVerdict.objects.bulk_create(
        [
            UserVerdict(frame=f, verdict=body.verdict, source=VerdictSource.OVERRIDE, user=request.user)
            for f in frames
        ]
    )
    for ds in Dataset.objects.filter(pk__in={f.dataset_id for f in frames if f.dataset_id}):
        recount_grades(ds)
        touch_dataset(ds)
    for f in frames:
        emit("frame.updated", {"sha256": f.sha256, "fields": ["verdict"]})
    return VerdictUpdatedOut(updated=len(frames))


# ---- previews ---------------------------------------------------------------------------------------------
@router.get("/frames/{sha256:sha256}/preview", response={200: None, 404: None})
def preview(request, sha256: str, size: Literal["screen", "thumb"] = "screen"):
    m = SubMeasurement.objects.filter(frame_id=sha256).first()
    if m is None or not m.preview_path:
        return HttpResponse(status=404)
    p = Path(m.preview_path)
    if size == "thumb":
        p = p.with_name(p.stem + "_t.jpg")
    if not p.exists():
        return HttpResponse(status=404)
    resp = FileResponse(p.open("rb"), content_type="image/jpeg")
    resp["Cache-Control"] = "private, max-age=86400"
    return resp


@router.get("/frames/{sha256:sha256}/glance", response={200: None, 404: None})
def glance_image(request, sha256: str):
    """A small image of any frame for hover previews: its preview, QA thumbnail or built-master preview when one
    exists, else drawn from the file once and cached (owner 2026-10-11)."""
    import tempfile

    from .models import BuiltMaster, CalibrationQA
    from .previews import glance
    from .tasks import source_path

    def send(p: Path) -> FileResponse:
        resp = FileResponse(p.open("rb"), content_type="image/jpeg")
        resp["Cache-Control"] = "private, max-age=86400"
        return resp

    m = SubMeasurement.objects.filter(frame_id=sha256).exclude(preview_path="").first()
    if m is not None and (p := Path(m.preview_path)).exists():
        return send(p)
    q = CalibrationQA.objects.filter(frame_id=sha256).exclude(thumb_path="").first()
    if q is not None and (p := Path(q.thumb_path)).exists():
        return send(p)
    b = BuiltMaster.objects.filter(frame_id=sha256).exclude(preview_path="").order_by("-pk").first()
    if b is not None and (p := Path(b.preview_path)).exists():
        return send(p)
    # the API's folders are read-only: cache in its own temp space
    cached = Path(tempfile.gettempdir()) / "sst-glance" / f"{sha256[:24]}.jpg"
    if cached.exists():
        return send(cached)
    frame = get_object_or_404(Frame, pk=sha256)
    src = source_path(frame)
    if (
        src is None
    ):  # a binned file in a read-only library is only hidden: it is still there to look at (spec 011)
        for c in Copy.objects.filter(frame=frame).select_related("library"):
            if (Path(c.library.mount_path) / c.rel_path).is_file():
                src = Path(c.library.mount_path) / c.rel_path
                break
    if src is None:
        return HttpResponse(status=404)
    try:
        glance(src, cached)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("Couldn't draw a glance of %s", sha256, exc_info=True)
        return HttpResponse(status=404)
    return send(cached)


@router.get("/frames/{sha256:sha256}/stars", response={200: None, 404: None})
def stars(request, sha256: str):
    """The detected stars for the Stars and FWHM map views (003 G15): positions as fractions of the frame."""
    m = SubMeasurement.objects.filter(frame_id=sha256).first()
    if m is None or not m.preview_path:
        return HttpResponse(status=404)
    p = Path(m.preview_path)
    p = p.with_name(p.stem + "_stars.json")
    if not p.exists():
        return HttpResponse(status=404)
    return FileResponse(p.open("rb"), content_type="application/json")


# ---- one sub ----------------------------------------------------------------------------------------------
class Field(Schema):
    label: str
    value: str | None
    source: str  # SubStation, header, solve, …


class Section(Schema):
    title: str
    source: str
    fields: list[Field]


class OverrideOut(Schema):
    verdict: str
    by: str | None
    at: datetime
    source: str


class ProcessingOut(Schema):
    sub: SubOut
    dataset_id: int | None
    session_medians: dict
    calibration: dict
    sections: list[Section]
    history: list[OverrideOut]
    graded_at: datetime | None
    neighbours: dict
    collection: str | None = None
    collection_id: int | None = None
    dataset_label: str | None = None
    raw_header: dict[str, str] = {}
    site_lat: float | None = None  # where it was shot, for the sub page's map (spec 012)
    site_lon: float | None = None


@router.get("/frames/{sha256:sha256}/processing", response=ProcessingOut)
def frame_processing(request, sha256: str):
    f = get_object_or_404(_lights(), pk=sha256)
    s = sub_out(f)
    kw = _kw(f)
    g = getattr(f, "grade", None) if MachineGrade.objects.filter(frame=f).exists() else None
    cm = CalibrationMatch.objects.filter(frame=f).select_related("dark__night", "flat__night").first()
    med = g.session_medians if g else {}

    def fmt(v: float | None, unit: str = "", digits: int = 2) -> str | None:
        return None if v is None else f"{v:,.{digits}f}{unit}"

    measured = Section(
        title="Measured",
        source="SubStation",
        fields=[
            Field(
                label="FWHM",
                value=(
                    f"{s.fwhm_arcsec:.2f}″ · {s.fwhm_px:.2f} px"
                    if s.fwhm_arcsec and s.fwhm_px
                    else fmt(s.fwhm_px, " px")
                ),
                source="SubStation",
            ),
            Field(
                label="Stars",
                value=(f"{s.stars:,}" + (f" of {med['stars']:,.0f} median" if med.get("stars") else ""))
                if s.stars is not None
                else None,
                source="SubStation",
            ),
            Field(label="Background", value=fmt(s.background, " ADU", 0), source="SubStation"),
            Field(label="Eccentricity", value=fmt(s.eccentricity), source="SubStation"),
            Field(label="SNR", value=fmt(s.snr, "", 1), source="SubStation"),
        ],
    )
    # where each resolved value came from (001-DR-04): Header, Pattern, User or SubStation
    label_of = {
        "header": "Header",
        "folder_pattern": "Pattern",
        "filename_pattern": "Pattern",
        "user": "User",
        "inferred": "SubStation",
        "settings": "Settings",
    }
    won = dict(f.metadata.filter(is_winner=True).values_list("field", "source"))

    def src(*fields: str) -> str:
        return next((label_of.get(won[x], "Header") for x in fields if x in won), "Header")

    capture = Section(
        title="Capture",
        source=_text(kw, ("SWCREATE",)) or "Header",
        fields=[
            Field(
                label="Camera",
                value=" · ".join(
                    x
                    for x in [
                        f.camera or "",
                        f"gain {f.gain}" if f.gain is not None else "",
                        f"offset {f.offset}" if f.offset is not None else "",
                    ]
                    if x
                )
                or None,
                source=src("camera", "gain"),
            ),
            Field(
                label="Sensor",
                value=(
                    f"{f.ccd_temp_c:g} °C" + (f" · set {f.set_temp_c:g}" if f.set_temp_c is not None else "")
                ).replace("-", "−")
                if f.ccd_temp_c is not None
                else None,
                source=src("ccd_temp"),
            ),
            Field(label="Filter", value=f.filter_raw, source=src("filter")),
            Field(
                label="Telescope",
                value=" · ".join(
                    x
                    for x in [
                        f.telescope or "",
                        f"{_num(kw, ('FOCALLEN',)):g} mm" if _num(kw, ("FOCALLEN",)) else "",
                    ]
                    if x
                )
                or None,
                source=src("telescope"),
            ),
            Field(
                label="Focuser",
                value=" · ".join(
                    x
                    for x in [
                        f"{_num(kw, COND['focpos']):,.0f}" if _num(kw, COND["focpos"]) else "",
                        f"{_num(kw, COND['foctemp']):.1f} °C"
                        if _num(kw, COND["foctemp"]) is not None
                        else "",
                    ]
                    if x
                )
                or None,
                source="header",
            ),
            Field(label="Guiding", value=fmt(_guiding(f, kw)[0], "″ RMS"), source=_guiding(f, kw)[1]),
            Field(
                label="Mount",
                value=" · ".join(
                    x
                    for x in [
                        f"Alt {_num(kw, COND['altitude']):.0f}°" if _num(kw, COND["altitude"]) else "",
                        f"pier {str(_text(kw, COND['pierside'])).lower()}"
                        if _text(kw, COND["pierside"])
                        else "",
                    ]
                    if x
                )
                or None,
                source="header",
            ),
            Field(label="Airmass", value=fmt(_num(kw, COND["airmass"])), source="header"),
        ],
    )
    sqm = _num(kw, COND["sqm"])
    conditions = Section(
        title="Conditions",
        source="where recorded",
        fields=[
            Field(label="SQM", value=f"{sqm:.2f} mag/arcsec²" if sqm else None, source="header"),
            Field(label="Cloud", value=fmt(_num(kw, COND["cloud"]), "%", 0), source="header"),
            Field(
                label="Ambient",
                value=" · ".join(
                    x
                    for x in [
                        f"{_num(kw, COND['ambient']):.1f} °C"
                        if _num(kw, COND["ambient"]) is not None
                        else "",
                        f"{_num(kw, COND['humidity']):.0f}% RH"
                        if _num(kw, COND["humidity"]) is not None
                        else "",
                        f"dew point {_num(kw, COND['dewpoint']):.1f} °C"
                        if _num(kw, COND["dewpoint"]) is not None
                        else "",
                    ]
                    if x
                )
                or None,
                source="header",
            ),
            Field(label="Sky temperature", value=fmt(_num(kw, COND["skytemp"]), " °C", 1), source="header"),
            Field(label="Wind", value=fmt(_num(kw, COND["wind"]), " m/s", 1), source="header"),
        ],
    )
    ps = PlateSolve.objects.filter(frame=f).first()
    if ps is not None and ps.state == "solved":
        solve = Section(
            title="Plate solve",
            source=f"{ps.solver} · {ps.seconds:g} s" if ps.seconds else ps.solver,
            fields=[
                Field(
                    label="Centre",
                    value=f"RA {ps.ra_deg:.4f}° Dec {ps.dec_deg:+.4f}°".replace("-", "−"),
                    source=ps.solver,
                ),
                Field(
                    label="Rotation",
                    value=f"{ps.rotation_deg:.1f}°" if ps.rotation_deg is not None else None,
                    source=ps.solver,
                ),
                Field(label="Pixel scale", value=fmt(ps.scale_arcsec, "″/px"), source=ps.solver),
                Field(
                    label="Field",
                    value=f"{ps.fov_w_deg:.2f}° × {ps.fov_h_deg:.2f}°" if ps.fov_w_deg else None,
                    source=ps.solver,
                ),
            ],
        )
    else:
        solve = Section(
            title="Plate solve",
            source=(ps.reason if ps else "not solved yet"),
            fields=[
                Field(
                    label="Pointing (header)",
                    value=(
                        f"RA {_num(kw, ('RA',)):.4f}° Dec {_num(kw, ('DEC',)):+.4f}°".replace("-", "−")
                        if _num(kw, ("RA",)) is not None and _num(kw, ("DEC",)) is not None
                        else None
                    ),
                    source="header",
                ),
                Field(
                    label="Pixel scale",
                    value=fmt(
                        f.measurement.pixel_scale
                        if hasattr(f, "measurement") and SubMeasurement.objects.filter(frame=f).exists()
                        else None,
                        "″/px",
                    ),
                    source="SubStation",
                ),
            ],
        )
    calib = {
        "state": cm.state if cm else None,
        "reason": cm.reason if cm else None,
        "dark": master_label(cm.dark) if cm else None,
        "dark_note": cm.dark_note if cm else None,
        "flat": master_label(cm.flat) if cm else None,
        "flat_note": cm.flat_note if cm else None,
        "weak": cm.weak if cm else False,
        "matched_on": _matched_on(f),
    }
    hist = [
        OverrideOut(
            verdict=v.verdict, by=v.user.get_username() if v.user else None, at=v.created_at, source=v.source
        )
        for v in f.verdicts.select_related("user").order_by("created_at")
    ]
    neighbours: dict = {}
    if f.dataset_id:
        same = list(
            Frame.objects.filter(
                dataset_id=f.dataset_id,
                night_id=f.night_id,
                frame_type=FrameType.LIGHT,
                status=FrameStatus.CATALOGUED,
            )
            .order_by("date_obs_utc")
            .values_list("pk", flat=True)
        )
        i = same.index(f.pk) if f.pk in same else -1
        neighbours = {
            "index": i + 1,
            "count": len(same),
            "previous": same[i - 1] if i > 0 else None,
            "next": same[i + 1] if 0 <= i < len(same) - 1 else None,
        }
    from apps.catalogue.services.library import label

    ds = f.dataset
    snap = f.headers.all()[0] if f.headers.all() else None
    raw = {k: str(v.get("value")) for k, v in (snap.keywords or {}).items()} if snap else {}
    return ProcessingOut(
        sub=s,
        dataset_id=f.dataset_id,
        session_medians=med,
        calibration=calib,
        sections=[measured, solve, capture, conditions],
        history=hist,
        graded_at=g.graded_at if g else None,
        neighbours=neighbours,
        collection=ds.collection.name if ds and ds.collection else (ds.target if ds else None),
        collection_id=ds.collection_id if ds else None,
        dataset_label=label(ds) if ds else None,
        raw_header=raw,
        site_lat=f.site_lat if f.site_lat or f.site_lon else None,
        site_lon=f.site_lon if f.site_lat or f.site_lon else None,
    )


# ---- review -----------------------------------------------------------------------------------------------
class ReviewGroup(Schema):
    dataset_id: int
    dataset: str
    target: str
    night: date | None
    rejected: int
    down: int
    near: int
    subs: list[SubOut]


@router.get("/review", response=list[ReviewGroup])
def review(request):
    """Flagged subs (spec 003 A2): rejected, down-weighted or near a threshold, grouped by dataset and night,
    newest first. Subs the user already decided are left out."""
    groups: dict[tuple[int, date | None], list[SubOut]] = defaultdict(list)
    qs = _lights(dataset__isnull=False, grade__isnull=False)
    for f in qs:
        s = sub_out(f)
        if s.manual or s.source == "nina":
            continue
        if s.verdict in ("reject", "down") or s.near_threshold:
            groups[(f.dataset_id, s.night)].append(s)  # type: ignore[index]
    names = {d.pk: d for d in Dataset.objects.filter(pk__in={k[0] for k in groups})}
    out = []
    for (ds_id, night), subs in sorted(groups.items(), key=lambda kv: kv[0][1] or date.min, reverse=True):
        d = names[ds_id]
        c = Counter(s.verdict for s in subs)
        out.append(
            ReviewGroup(
                dataset_id=ds_id,
                dataset=d.display_name,
                target=d.target,
                night=night,
                rejected=c["reject"],
                down=c["down"],
                near=sum(1 for s in subs if s.verdict == "accept"),
                subs=subs,
            )
        )
    return out


class RegradeIn(Schema):
    confirm: bool = False


class RegradeOut(Schema):
    changes: int
    by_change: dict[str, int]
    queued: bool


@router.post("/datasets/{id}/regrade", response=RegradeOut)
def regrade_dataset(request, id: int, body: RegradeIn):  # noqa: A002
    """Re-grade with the current thresholds (003-DR-02): without `confirm`, only say what would change; with it,
    queue the re-grade. Human verdicts are kept either way."""
    from .grading import preview_regrade, regrade_datasets

    get_object_or_404(Dataset, pk=id)
    rows = preview_regrade({}, dataset_id=id)
    by = rows[0]["by_change"] if rows else {}
    if body.confirm:
        enqueue(regrade_datasets, [id], dedupe_key=f"regrade:{id}")
    return RegradeOut(changes=sum(by.values()), by_change=by, queued=body.confirm)


class RecalibrationOut(Schema):
    pending: int
    sessions: dict[str, int]
    queued: int = 0


def _outdated(dataset_id: int) -> list[tuple[str, str]]:
    """Measured subs whose current match names a different dark or flat than they were calibrated with."""
    out = []
    rows = SubMeasurement.objects.filter(state=MeasureState.DONE, frame__dataset_id=dataset_id).values_list(
        "frame_id", "dark_id", "flat_id", "frame__night__date"
    )
    matched = dict(
        (r[0], (r[1], r[2]))
        for r in CalibrationMatch.objects.filter(
            frame__dataset_id=dataset_id, state=MatchState.MATCHED
        ).values_list("frame_id", "dark_id", "flat_id")
    )
    for sha, dark, flat, night in rows:
        if sha in matched and matched[sha] != (dark, flat):
            out.append((sha, str(night)))
    return out


class PendingRecalOut(Schema):
    dataset_id: int
    dataset: str
    collection: str | None
    subs: int
    sessions: int


@router.get("/calibration/recalibration", response=list[PendingRecalOut])
def pending_recalibration(request):
    """Datasets whose calibrated subs now match different masters (002 C11): listed on the Calibration screen,
    re-calibrated only when you say so on the dataset's Calibration tab."""
    from apps.catalogue.api_library import label

    rows = SubMeasurement.objects.filter(
        state=MeasureState.DONE, frame__calibration__state=MatchState.MATCHED
    ).values_list(
        "frame__dataset_id",
        "frame__night_id",
        "dark_id",
        "flat_id",
        "frame__calibration__dark_id",
        "frame__calibration__flat_id",
    )
    diff = [(ds_id, night) for ds_id, night, d, f, md, mf in rows if (d, f) != (md, mf)]
    per: dict[int, list] = defaultdict(list)
    for ds_id, night in diff:
        if ds_id:
            per[ds_id].append(night)
    out = []
    for d in Dataset.objects.filter(pk__in=per).select_related("rig", "collection"):
        out.append(
            PendingRecalOut(
                dataset_id=d.pk,
                dataset=label(d),
                collection=d.collection.name if d.collection else None,
                subs=len(per[d.pk]),
                sessions=len(set(per[d.pk])),
            )
        )
    return sorted(out, key=lambda r: -r.subs)


@router.get("/datasets/{id}/recalibration", response=RecalibrationOut)
def recalibration(request, id: int):  # noqa: A002
    """002 C11 / 004 T014: newer calibration is offered, never applied silently to calibrated subs."""
    rows = _outdated(id)
    return RecalibrationOut(pending=len(rows), sessions=dict(Counter(n for _, n in rows)))


@router.post("/datasets/{id}/recalibration", response=RecalibrationOut)
def apply_recalibration(request, id: int):  # noqa: A002
    from .models import Master, MasterState
    from .tasks import queue_measure

    rows = _outdated(id)
    shas = [sha for sha, _ in rows]
    for f in Frame.objects.filter(pk__in=shas):
        queue_measure(f, force=True)
    hit = Master.objects.filter(
        dataset_id=id, state=MasterState.CURRENT, members__frame_id__in=shas, members__included=True
    ).distinct()
    hit.update(state=MasterState.STALE, state_reason=f"Calibration changed for {len(shas)} subs.")
    return RecalibrationOut(pending=len(rows), sessions=dict(Counter(n for _, n in rows)), queued=len(shas))


class MasterChoice(Schema):
    sha256: str
    label: str
    note: str
    thumb: str | None = None
    # for the flat table (owner 2026-10-12)
    filter: str = ""
    night: date | None = None
    days: int | None = None  # flat's night minus the session's: negative is before
    frames: int | None = None
    telescope: str = ""
    same_filter: bool = True


class FlatSetChoice(Schema):
    set_id: int
    label: str
    note: str
    built: bool
    sha: str | None = None  # its master when built, else one of its flats, to look at
    thumb: str | None = None
    filter: str = ""
    night: date | None = None
    days: int | None = None
    frames: int | None = None
    telescope: str = ""
    same_filter: bool = True


class SessionChoicesOut(Schema):
    darks: list[MasterChoice]
    flats: list[MasterChoice]
    flat_sets: list[FlatSetChoice] = []
    filters: list[str] = []


class SessionCalibrationIn(Schema):
    dark: str | None = None
    flat: str | None = None
    flat_set: int | None = None


def _session_lights(dataset_id: int, night: date) -> list[Frame]:
    return list(
        Frame.objects.filter(
            dataset_id=dataset_id,
            night__date=night,
            frame_type=FrameType.LIGHT,
            status=FrameStatus.CATALOGUED,
        )
    )


@router.get("/datasets/{id}/sessions/{night}/calibration", response=SessionChoicesOut)
def session_choices(request, id: int, night: date):  # noqa: A002
    """Masters a session could use instead (002 C10): same camera; darks of the session's exposure (or a bias),
    flats of its filter. Age and temperature are shown so the choice is informed."""
    lights = _session_lights(id, night)
    if not lights:
        raise ApiError(404, "not_found", "That session has no subs.")
    f0 = lights[0]
    cams = {f0.camera, None, ""}
    darks = (
        Frame.objects.filter(status=FrameStatus.CATALOGUED, camera__in=cams)
        .filter(
            Q(
                frame_type=FrameType.MASTER_DARK,
                exptime_s__gte=(f0.exptime_s or 0) - 0.01,
                exptime_s__lte=(f0.exptime_s or 0) + 0.01,
            )
            | Q(frame_type=FrameType.MASTER_BIAS)
        )
        .select_related("night")
    )
    flats = (
        Frame.objects.filter(
            status=FrameStatus.CATALOGUED,
            camera__in=cams,
            frame_type=FrameType.MASTER_FLAT,
            filter_norm__iexact=f0.filter_norm or "",
        )
        .select_related("night")
        .prefetch_related("headers")
    )

    def note(m: Frame) -> str:
        bits = []
        if m.night:
            days = (night - m.night.date).days
            bits.append(
                "same night" if days == 0 else f"{abs(days)} days {'before' if days > 0 else 'after'}"
            )
        if m.gain is not None:
            bits.append(f"gain {m.gain}")
        if m.telescope:
            bits.append(m.telescope)
        return " · ".join(bits)

    sets = _flat_sets(f0, night)
    built_shas = {x.sha for x in sets if x.built}
    return SessionChoicesOut(
        flat_sets=sets,
        filters=sorted(
            {
                str(x)
                for x in Frame.objects.filter(frame_type=FrameType.LIGHT)
                .exclude(filter_norm=None)
                .exclude(filter_norm="")
                .values_list("filter_norm", flat=True)
                .distinct()
            }
        ),
        darks=[
            MasterChoice(
                sha256=m.pk,
                label=master_label(m) or ("Bias" if m.frame_type == FrameType.MASTER_BIAS else m.pk[:12]),
                note=note(m),
            )
            for m in darks
        ],
        flats=[
            MasterChoice(
                sha256=m.pk,
                label=master_label(m) or m.pk[:12],
                note=note(m),
                thumb=frame_thumb(m.pk),
                filter=m.filter_norm or "",
                night=m.night.date if m.night else None,
                days=(m.night.date - night).days if m.night else None,
                frames=_frames_in(m),
                telescope=m.telescope or "",
            )
            for m in flats
            if m.pk not in built_shas  # a set SubStation built is listed once, as its set
        ],
    )


class SessionFilterIn(Schema):
    filter: str


class SessionFilterOut(Schema):
    updated: int
    dataset_id: int | None


@router.post("/datasets/{id}/sessions/{night}/filter", response=SessionFilterOut)
def set_session_filter(request, id: int, night: date, body: SessionFilterIn):  # noqa: A002
    """Say which filter a whole session used (owner 2026-10-10). Stored as
    your correction for each sub, so it regroups them into that filter's dataset, finds flats for that filter
    and measures them again. Clear the box to go back to what the headers say."""
    from apps.accounts.roles import is_viewer
    from apps.catalogue.services.corrections import CorrectionError, set_value

    from .matching import update_match
    from .tasks import queue_measure

    if is_viewer(request.user):
        raise ApiError(403, "forbidden", "Read-only users can't change subs.")
    lights = _session_lights(id, night)
    if not lights:
        raise ApiError(404, "not_found", "That session has no subs.")
    try:
        n = set_value([f.pk for f in lights], "filter", body.filter.strip() or None, request.user)
    except CorrectionError as e:
        raise ApiError(422, "invalid_value", str(e)) from None
    moved = list(Frame.objects.filter(pk__in=[f.pk for f in lights]))
    for f in moved:
        cm = CalibrationMatch.objects.filter(frame=f).first()
        if cm is not None and cm.pinned:  # a flat chosen for the old filter no longer applies
            cm.pinned, cm.pending_flat_set = False, None
            cm.save(update_fields=["pinned", "pending_flat_set"])
        update_match(f)
        queue_measure(f, force=True)
    return SessionFilterOut(updated=n, dataset_id=moved[0].dataset_id if moved else None)


def _frames_in(m: Frame) -> int | None:
    """How many flats went into a library master, when its header says (NCOMBINE, or PixInsight's)."""
    snap = m.headers.first() if hasattr(m, "headers") else None
    kw = (snap.keywords or {}) if snap else {}
    for k in ("NCOMBINE", "IMAGECOUNT"):
        v = kw.get(k)
        v = v.get("value") if isinstance(v, dict) else v
        try:
            return int(float(v))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return None


def _flat_sets(f0: Frame, night: date) -> list[FlatSetChoice]:
    """Every flat set from this camera at this frame size, nearest in time first (002 C10, owner 2026-10-10). Other filters are listed too, marked, because a
    session's filter may itself be wrong."""
    from datetime import UTC, datetime, time

    from apps.catalogue.models import CalibrationSet

    from .matching import dims
    from .models import BuiltMaster
    from .tasks import is_processed_rgb

    size = dims(f0)
    rgb = is_processed_rgb(f0)
    when = datetime.combine(night, time(22), tzinfo=UTC)
    out = []
    for cs in CalibrationSet.objects.filter(type=FrameType.FLAT, camera=f0.camera or "").order_by(
        "-session_start_utc"
    )[:200]:
        first = Frame.objects.filter(calibration_set=cs).prefetch_related("headers").first()
        if first is None or (size and dims(first) and dims(first) != size) or is_processed_rgb(first) != rgb:
            continue
        hours = (cs.session_start_utc - when).total_seconds() / 3600
        days = round(hours / 24)
        bits = [
            "same day"
            if days == 0
            else f"{abs(days)} day{'s' if abs(days) != 1 else ''} {'after' if days > 0 else 'before'}",
            f"{cs.frame_count} frames",
        ]
        same = (cs.filter_norm or "").casefold() == (f0.filter_norm or "").casefold()
        if not same:
            bits.append(f"filter {cs.filter_norm or 'none'}, not {f0.filter_norm or 'none'}")
        if first.telescope:
            bits.append(first.telescope)
        bm = (
            BuiltMaster.objects.filter(calibration_set=cs, state="done")
            .exclude(frame=None)
            .order_by("-pk")
            .first()
        )
        built = bm is not None
        look = bm.frame_id if bm else first.pk
        out.append(
            (
                abs(hours),
                FlatSetChoice(
                    set_id=cs.pk,
                    label=f"Flats {cs.filter_norm or ''} {cs.session_start_utc:%-d %b %Y %H:%M}".replace(
                        "  ", " "
                    ),
                    note=" · ".join(bits),
                    built=built,
                    sha=look,
                    thumb=frame_thumb(look),
                    filter=cs.filter_norm or "",
                    night=cs.session_start_utc.date(),
                    days=days,
                    frames=cs.frame_count,
                    telescope=first.telescope or "",
                    same_filter=same,
                ),
            )
        )
    ranked = [c for _, c in sorted(out, key=lambda x: x[0])]
    # every set of the session's filter; a few of the others, for a session whose filter is itself wrong
    return [c for c in ranked if c.same_filter][:40] + [c for c in ranked if not c.same_filter][:20]


@router.post("/datasets/{id}/sessions/{night}/calibration", response=RecalibrationOut)
def change_session_calibration(request, id: int, night: date, body: SessionCalibrationIn):  # noqa: A002
    """Use these masters for this session only (002-DR-07): pinned so a later rematch keeps them, then the
    session is calibrated and graded again. Human verdicts stay."""
    from .models import Master, MasterState
    from .tasks import queue_measure

    lights = _session_lights(id, night)
    if not lights:
        raise ApiError(404, "not_found", "That session has no subs.")
    for sha in (body.dark, body.flat):
        if sha and not Frame.objects.filter(pk=sha, frame_type__startswith="master_").exists():
            raise ApiError(422, "invalid", "Choose one of the listed masters.")
    if body.flat_set is not None:
        # a flat set rather than a master: use its master when built, else build it and apply it when done
        from apps.catalogue.models import CalibrationSet

        from .calibration import request_build
        from .models import BuiltMaster

        cs = get_object_or_404(CalibrationSet, pk=body.flat_set, type=FrameType.FLAT)
        done = (
            BuiltMaster.objects.filter(calibration_set=cs, state="done")
            .exclude(frame=None)
            .order_by("-pk")
            .first()
        )
        if done is not None:
            body.flat = done.frame_id
        else:
            if not BuiltMaster.objects.filter(calibration_set=cs, state__in=["queued", "running"]).exists():
                request_build(cs, force=True, priority=PRIORITY_LIVE)
            for f in lights:
                cm, _ = CalibrationMatch.objects.get_or_create(
                    frame=f, defaults={"state": MatchState.AWAITING}
                )
                cm.pending_flat_set, cm.pinned = cs, True
                cm.state, cm.reason = (
                    MatchState.AWAITING,
                    f"Waiting for flats ({cs.session_start_utc:%-d %b}) to be built.",
                )
                cm.save()
            return RecalibrationOut(pending=len(lights), sessions={str(night): len(lights)}, queued=0)
    for f in lights:
        cm, _ = CalibrationMatch.objects.get_or_create(frame=f)
        cm.dark_id = body.dark or cm.dark_id
        cm.flat_id = body.flat or cm.flat_id
        cm.state, cm.pinned, cm.reason, cm.weak = MatchState.MATCHED, True, "", False
        cm.pending_flat_set = None
        cm.dark_note = "Chosen by you" if body.dark else cm.dark_note
        cm.flat_note = "Chosen by you" if body.flat else cm.flat_note
        cm.save()
        queue_measure(f, force=True)
    Master.objects.filter(
        dataset_id=id, state=MasterState.CURRENT, members__frame__in=lights, members__included=True
    ).distinct().update(
        state=MasterState.STALE, state_reason=f"Calibration changed for the {night:%-d %b} session."
    )
    return RecalibrationOut(pending=0, sessions={str(night): len(lights)}, queued=len(lights))


class SolvingOut(Schema):
    available: bool
    catalogue_dir: str
    solved: int
    failed: int
    waiting: int
    queued: int = 0


def _solving(queued: int = 0) -> SolvingOut:
    from .solving import available, catalogue_dir

    measured = SubMeasurement.objects.filter(
        state=MeasureState.DONE, frame__frame_type=FrameType.LIGHT, frame__status=FrameStatus.CATALOGUED
    )
    solved = PlateSolve.objects.filter(state="solved").count()
    failed = PlateSolve.objects.filter(state="failed").count()
    return SolvingOut(
        available=available(),
        catalogue_dir=str(catalogue_dir()),
        solved=solved,
        failed=failed,
        waiting=measured.filter(frame__solve__isnull=True).count(),
        queued=queued,
    )


@router.get("/solving", response=SolvingOut)
def solving_status(request):
    return _solving()


@router.post("/solving/backfill", response=SolvingOut)
def solving_backfill(request):
    """Solve every measured light that hasn't been (009 P9): a low-priority job shown in Activity."""
    from substation.api import is_admin

    from .solving import backfill_solves

    if not is_admin(request.user):
        raise ApiError(403, "admin_only", "Only an admin can change this.")
    enqueue(backfill_solves, dedupe_key="backfill-solves")
    return _solving(queued=1)


@router.get("/review/count", response=dict[str, int])
def review_count(request):
    """The same subs /review lists, counted without building them (it's polled by every page)."""
    n = 0
    qs = (
        Frame.objects.filter(
            frame_type=FrameType.LIGHT,
            status=FrameStatus.CATALOGUED,
            dataset__isnull=False,
            grade__isnull=False,
        )
        .select_related("grade")
        .prefetch_related("verdicts")
    )
    for f in qs:
        e = effective(f, list(f.verdicts.all()), f.grade)
        if not e.manual and (e.verdict in ("reject", "down") or f.grade.near_threshold):
            n += 1
    return {"count": n}


__all__ = ["router", "timezone", "Verdict"]


class ViewOut(Schema):
    ready: bool
    generating: bool = False
    failed: bool = False  # the last attempt to draw it failed; `note` says why
    full: str | None = None
    inspector: str | None = None
    note: str = ""


@router.get("/frames/{sha256:sha256}/view", response=ViewOut)
def full_view_status(request, sha256: str):
    """The 100% view and aberration inspector (owner 2026-10-10): ready, or being made now (a few seconds)."""
    from .tasks import full_paths

    f = get_object_or_404(Frame, pk=sha256)
    full, inspect = full_paths(f)
    if full.exists() and inspect.exists():
        return ViewOut(
            ready=True,
            full=f"/api/v1/frames/{sha256}/view/full",
            inspector=f"/api/v1/frames/{sha256}/view/inspector",
        )

    from .api_masters import look_progress

    return ViewOut(ready=False, **look_progress(f"full:{sha256}", "No 100% view yet."))


@router.post("/frames/{sha256:sha256}/view", response=ViewOut)
def make_view(request, sha256: str):
    """Draw the 100% view now (a few seconds), for a sub that doesn't have one."""
    from substation.tasks import enqueue

    from .tasks import full_view

    get_object_or_404(Frame, pk=sha256)
    enqueue(full_view, sha256, dedupe_key=f"full:{sha256}")
    return ViewOut(ready=False, generating=True, note="Drawing the 100% view…")


@router.get("/frames/{sha256:sha256}/view/{kind}", response={200: None, 404: None})
def full_view_file(request, sha256: str, kind: Literal["full", "inspector"]):
    from .tasks import full_paths

    f = get_object_or_404(Frame, pk=sha256)
    full, inspect = full_paths(f)
    p = full if kind == "full" else inspect
    if not p.exists():
        return HttpResponse(status=404)
    return FileResponse(p.open("rb"), content_type="image/jpeg")


@router.get("/frames/{sha256:sha256}/annotations", response=AnnotationsOut)
def frame_annotations(request, sha256: str):
    """The named objects in a solved sub's field, placed on its preview (009 amendment 2026-10-12)."""
    from .annotations import for_solve

    f = get_object_or_404(Frame, pk=sha256)
    ps = PlateSolve.objects.filter(frame=f).select_related("frame").first()
    if ps is None or ps.state != "solved":
        return AnnotationsOut(solved=False, note=ps.reason if ps else "Not plate solved yet.")
    return AnnotationsOut(solved=True, objects=[AnnotationOut(**o) for o in for_solve(ps)])
