"""Grading (spec 003 FR-003, FR-004; v2 amendment): each sub against its own session (dataset and night).

Standard profile (Settings · Grading): FWHM, star count and background relative to the session median, each
with a down-weight and a reject level; eccentricity absolute. The spike profile reproduces the spike grader
(wFWHM 1.5×, stars 0.6×, background 2×, roundness 0.85, reject only) for validation.

wFWHM is Siril's: FWHM + 2·FWHM·(Nmax − N)/Nmax, Nmax the session's highest star count (checked against
Siril's registration output in docs/spikes phase 2).
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass, field

from django.db import transaction

from apps.catalogue.models import Frame, FrameStatus, FrameType
from substation.tasks import PRIORITY_BULK, report_progress, station_task

from .config import processing_settings
from .models import GradeVerdict, MachineGrade, MeasureState, SubMeasurement

SEVERITY: dict[str, int] = {GradeVerdict.ACCEPT: 0, GradeVerdict.DOWN: 1, GradeVerdict.REJECT: 2}


@dataclass
class Sub:
    key: str
    stars: int
    fwhm: float | None  # px
    background: float | None
    eccentricity: float | None
    roundness: float | None
    scale: float | None = None  # arcsec/px


@dataclass
class Grade:
    verdict: str
    weight: float
    reason: str
    near: bool = False
    wfwhm: float | None = None
    notes: list[str] = field(default_factory=list)


def wfwhm(fwhm: float | None, n: int, nmax: int) -> float | None:
    if fwhm is None or nmax <= 0:
        return None
    return fwhm + 2 * fwhm * (nmax - n) / nmax


def _pct(ratio: float) -> int:
    return round(abs(ratio - 1) * 100)


def _fwhm_text(s: Sub) -> str:
    if s.fwhm is None:
        return ""
    return f"{s.fwhm * s.scale:.2f}″" if s.scale else f"{s.fwhm:.2f} px"


Finding = tuple[str, float, str]  # (verdict, weight, reason)


def _medians(subs: list[Sub]) -> dict:
    have = [s for s in subs if s.stars > 0]
    return {
        "fwhm": statistics.median([s.fwhm for s in have if s.fwhm is not None])
        if any(s.fwhm for s in have)
        else None,
        "stars": statistics.median([s.stars for s in have]) if have else 0,
        "background": statistics.median([s.background for s in subs if s.background is not None])  # type: ignore[type-var]
        if any(s.background is not None for s in subs)
        else None,
        "eccentricity": statistics.median([s.eccentricity for s in have if s.eccentricity is not None])
        if sum(1 for s in have if s.eccentricity is not None) >= 5
        else None,
    }


def _check(
    ratio: float,
    levels: list[float],
    higher_is_bad: bool,
    text: Callable[[float, bool], str],
    weight_of: Callable[[float], float],
    found: list[Finding],
) -> bool:
    """Add a finding when the ratio to the session median passes a level; True when it is close to the down-weight
    level without passing it."""
    down, reject = levels
    bad = (lambda r, lv: r > lv) if higher_is_bad else (lambda r, lv: r < lv)
    if bad(ratio, reject):
        found.append((GradeVerdict.REJECT, 0.0, text(ratio, True)))
    elif bad(ratio, down):
        found.append((GradeVerdict.DOWN, weight_of(ratio), text(ratio, False)))
    elif abs(ratio - down) <= 0.1 * down:
        return True
    return False


def _check_eccentricity(s: Sub, levels: list[float], e_med: float | None, found: list[Finding]) -> bool:
    # absolute levels, but never below the session's own elongation plus a margin: a lens or tilt that
    # elongates every star is the rig, not a bad sub; tracking and wind still stand out from their session
    down, reject = levels
    if e_med is not None:
        down, reject = max(down, e_med + 0.08), max(reject, e_med + 0.15)
    e = s.eccentricity or 0.0
    if e > reject:
        found.append(
            (GradeVerdict.REJECT, 0.0, f"Elongated stars (eccentricity {e:.2f}): tracking, wind or tilt.")
        )
    elif e > down:
        found.append(
            (GradeVerdict.DOWN, 0.7, f"Slightly elongated stars (eccentricity {e:.2f}): tracking or wind.")
        )
    elif e > 0.9 * down:
        return True
    return False


def _findings(s: Sub, med: dict, cfg: dict) -> tuple[list[Finding], bool]:
    """What is wrong with one sub against its session, and whether it is close to a level."""
    found: list[Finding] = []
    near = False
    if med["fwhm"] and s.fwhm:
        near |= _check(
            s.fwhm / med["fwhm"],
            cfg["fwhm"],
            True,
            lambda r, rej: (
                f"FWHM {_fwhm_text(s)}, {_pct(r)}% above median: {'seeing or focus' if rej else 'seeing'}."
            ),
            lambda r: (1 / r) ** 2,
            found,
        )
    if med["stars"]:
        near |= _check(
            s.stars / med["stars"],
            cfg["stars"],
            False,
            lambda r, rej: f"Stars {round(r * 100)}% of median: {'cloud' if rej else 'thin cloud or haze'}.",
            lambda r: r,
            found,
        )
    if med["background"] and s.background is not None and med["background"] > 0:
        # a brighter background only means sky glow (moon, twilight, cloud) when the stars suffer with it; with
        # as many stars as usual it is more signal, e.g. a nebula filling the frame on a transparent night
        # (owner 2026-10-10, Soul Nebula Hα)
        star_ratio = s.stars / med["stars"] if med["stars"] else 1.0
        if star_ratio < 0.9:
            near |= _check(
                s.background / med["background"],
                cfg["background"],
                True,
                lambda r, rej: (
                    f"Background {_pct(r)}% above median, stars {round(star_ratio * 100)}%: moonlight, twilight "
                    "or cloud."
                ),
                lambda r: 1 / r,
                found,
            )
    if s.eccentricity is not None:
        near |= _check_eccentricity(s, cfg["eccentricity"], med.get("eccentricity"), found)
    return found, near


def grade_standard(subs: list[Sub], cfg: dict) -> tuple[dict[str, Grade], dict]:
    med = _medians(subs)
    nmax = max((s.stars for s in subs), default=0)
    out: dict[str, Grade] = {}
    for s in subs:
        if s.stars == 0:
            out[s.key] = Grade(GradeVerdict.REJECT, 0.0, "No stars: cloud or closed shutter.")
            continue
        found, near = _findings(s, med, cfg)
        w = wfwhm(s.fwhm, s.stars, nmax)
        if not found:
            out[s.key] = Grade(GradeVerdict.ACCEPT, 1.0, "Within normal range.", near, w)
            continue
        found.sort(key=lambda f: (-SEVERITY[f[0]], f[1]))
        verdict = found[0][0]
        weight = 0.0 if verdict == GradeVerdict.REJECT else max(0.2, min(0.95, min(f[1] for f in found)))
        out[s.key] = Grade(verdict, round(weight, 2), found[0][2], near, w, [f[2] for f in found[1:]])
    return out, {k: v for k, v in med.items()} | {"nmax": nmax}


def grade_spike(subs: list[Sub], p: dict) -> tuple[dict[str, Grade], dict]:
    nmax = max((s.stars for s in subs), default=0)
    w = {s.key: wfwhm(s.fwhm, s.stars, nmax) for s in subs}
    ok = [s for s in subs if s.stars > 0]
    med = {
        "wfwhm": statistics.median([v for s in ok if (v := w[s.key]) is not None]) if ok else None,
        "stars": statistics.median([s.stars for s in ok]) if ok else 0,
        "background": statistics.median([s.background for s in ok if s.background is not None])
        if ok
        else None,
    }
    out = {}
    for s in subs:
        why = []
        if s.stars == 0:
            why.append("No stars found")
        if med["wfwhm"] and w[s.key] and w[s.key] > p["wfwhm"] * med["wfwhm"]:
            why.append(f"wFWHM {w[s.key]:.2f} > {p['wfwhm']}× median {med['wfwhm']:.2f}")
        if med["stars"] and s.stars < p["stars"] * med["stars"]:
            why.append(f"stars {s.stars} < {p['stars']}× median {med['stars']:.0f}")
        if (
            med["background"]
            and s.background is not None
            and s.background > p["background"] * med["background"]
        ):
            why.append(f"background {s.background:.0f} > {p['background']}× median {med['background']:.0f}")
        if s.roundness is not None and s.roundness < p["roundness"]:
            why.append(f"roundness {s.roundness:.2f} < {p['roundness']}")
        out[s.key] = Grade(
            GradeVerdict.REJECT if why else GradeVerdict.ACCEPT,
            0.0 if why else 1.0,
            "; ".join(why) or "Within the spike grader's limits.",
            False,
            w[s.key],
        )
    return out, med | {"nmax": nmax}


def exposure_groups(rows: list, exptime_of) -> list[list]:  # noqa: ANN001
    """A session's subs split by exposure: a 5 s sub has far fewer stars and a darker sky than a 300 s one, so
    each is compared only with subs of its own exposure (DSLR sessions often mix them)."""
    groups: dict[float | None, list] = {}
    for r in rows:
        e = exptime_of(r)
        groups.setdefault(round(e, 1) if e else None, []).append(r)
    return list(groups.values())


def condition_flags(subs: list[tuple[str, float | None, float | None]]) -> dict[str, str]:
    """SQM and cloud, when the capture recorded them, flag a sub but never reject it alone (spec 003 v2
    amendment): SQM 0.3 mag or more below the session's median, or cloud cover above 50%. Returns key → note."""
    sqms = sorted(q for _, q, _ in subs if q is not None)
    med = sqms[len(sqms) // 2] if len(sqms) >= 3 else None
    out = {}
    for key, sqm, cloud in subs:
        notes = []
        if med is not None and sqm is not None and sqm <= med - 0.3:
            notes.append(f"SQM {sqm:.2f}, {med - sqm:.2f} below session: cloud or haze?")
        if cloud is not None and cloud > 50:
            notes.append(f"cloud cover {cloud:.0f}% recorded")
        if notes:
            out[key] = "; ".join(notes).capitalize() + " (flagged, not rejected)."
    return out


def grade_session(dataset_id: int, night_id: int | None) -> int:
    """(Re)grade every measured sub of one dataset on one night, each exposure on its own. Returns subs graded."""
    cfg = processing_settings()
    gcfg = cfg["grading"]
    frames = list(
        Frame.objects.filter(
            dataset_id=dataset_id,
            night_id=night_id,
            frame_type=FrameType.LIGHT,  # type: ignore[misc]
            status=FrameStatus.CATALOGUED,
            measurement__state=MeasureState.DONE,
        )
        .select_related("measurement")
        .prefetch_related("headers")
    )
    flags: dict[str, str] = {}
    if gcfg.get("use_conditions", True):
        from .api import COND, _kw, _num

        conds = [
            (f.sha256, _num(kw, COND["sqm"]), _num(kw, COND["cloud"])) for f in frames for kw in [_kw(f)]
        ]
        flags = condition_flags(conds)
    with transaction.atomic():
        for group in exposure_groups(frames, lambda f: f.exptime_s):
            subs = []
            for f in group:
                m: SubMeasurement = f.measurement
                subs.append(
                    Sub(
                        f.sha256,
                        m.stars or 0,
                        m.fwhm_px,
                        m.background,
                        m.eccentricity,
                        m.roundness,
                        m.pixel_scale,
                    )
                )
            if gcfg.get("profile") == "spike":
                grades, med = grade_spike(subs, cfg["spike_profile"])
            else:
                grades, med = grade_standard(subs, gcfg)
            provisional = len(subs) < gcfg["min_session"]
            for f in group:
                g = grades[f.sha256]
                if f.sha256 in flags:
                    g.near = True
                    g.reason = g.reason if g.verdict != GradeVerdict.ACCEPT else flags[f.sha256]
                    if g.verdict != GradeVerdict.ACCEPT:
                        g.notes.append(flags[f.sha256])
                MachineGrade.objects.update_or_create(
                    frame=f,
                    defaults={
                        "verdict": g.verdict,
                        "weight": g.weight,
                        "reason": g.reason,
                        "provisional": provisional,
                        "near_threshold": g.near,
                        "wfwhm_px": g.wfwhm,
                        "session_medians": med,
                        "thresholds_version": gcfg["version"],
                    },
                )
    from apps.catalogue.models import Dataset

    from .effective import recount_grades

    ds = Dataset.objects.filter(pk=dataset_id).first()
    if ds is not None:
        recount_grades(ds)
    return len(frames)


def _grade(subs: list[Sub], cfg: dict) -> dict[str, Grade]:
    return (
        grade_spike(subs, cfg["spike_profile"])
        if cfg["grading"].get("profile") == "spike"
        else grade_standard(subs, cfg["grading"])
    )[0]


def preview_regrade(changes: dict, dataset_id: int | None = None) -> list[dict]:
    """What saving `changes` to the grading settings would do (spec 008, 008-DR-04): per dataset, how many machine
    verdicts would change and how. Nothing is written; human verdicts are never touched by a re-grade."""
    from collections import Counter, defaultdict

    from apps.catalogue.models import Dataset

    from .config import _merge

    cfg = _merge(processing_settings(), changes)
    rows = SubMeasurement.objects.filter(
        state=MeasureState.DONE,
        frame__dataset__isnull=False,
        frame__frame_type=FrameType.LIGHT,
        frame__status=FrameStatus.CATALOGUED,
    ).values_list(
        "frame_id",
        "frame__dataset_id",
        "frame__night_id",
        "stars",
        "fwhm_px",
        "background",
        "eccentricity",
        "roundness",
        "pixel_scale",
        "frame__grade__verdict",
        "frame__exptime_s",
    )
    if dataset_id is not None:
        rows = rows.filter(frame__dataset_id=dataset_id)
    sessions: dict[tuple, list] = defaultdict(list)
    for r in rows:
        sessions[(r[1], r[2])].append(r)
    by_ds: dict[int, Counter] = defaultdict(Counter)
    for (ds, _night), session_rows in sessions.items():
        for rs in exposure_groups(session_rows, lambda r: r[10]):
            grades = _grade([Sub(r[0], r[3] or 0, r[4], r[5], r[6], r[7], r[8]) for r in rs], cfg)
            for r in rs:
                new, old = grades[r[0]].verdict, r[9]
                if old and new != old:
                    by_ds[ds][f"{old}→{new}"] += 1
    names = {d.pk: d.display_name for d in Dataset.objects.filter(pk__in=by_ds)}
    return sorted(
        (
            {"dataset_id": ds, "dataset": names.get(ds, ""), "changes": sum(c.values()), "by_change": dict(c)}
            for ds, c in by_ds.items()
        ),
        key=lambda x: -x["changes"],
    )


@station_task(queue_name="process", priority=PRIORITY_BULK + 5, max_attempts=2)
def regrade_datasets(dataset_ids: list[int]) -> dict:
    """Re-grade every session of these datasets with the current settings; human verdicts stay as they are."""
    n = 0
    for i, ds in enumerate(dataset_ids):
        for night_id in set(
            Frame.objects.filter(dataset_id=ds, frame_type=FrameType.LIGHT).values_list("night_id", flat=True)
        ):
            n += grade_session(ds, night_id)
        report_progress((i + 1) / max(1, len(dataset_ids)), f"re-grading {len(dataset_ids)} datasets")
    return {"datasets": len(dataset_ids), "subs": n}
