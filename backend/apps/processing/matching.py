"""Matching lights to calibration masters (spec 002 US1, FR-008 to FR-010; v2 amendment).

Dark: master dark with the light's exposure, gain, offset, binning and camera, temperature within the
tolerance (master SET-TEMP, else CCD-TEMP, against the light's CCD-TEMP); closest temperature, then newest.
Flat: master flat with the same filter, camera and binning, on or before the light's night; the latest.
More than `weak_flat_days` apart is a weak match (used, flagged). A master that lacks a value the rule needs
is not used; if that leaves nothing, the light waits, and the reason names what's missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from apps.catalogue.models import Frame, FrameStatus, FrameType

from .config import processing_settings
from .models import CalibrationMatch, MatchState


@dataclass
class Match:
    dark: Frame | None
    flat: Frame | None
    reason: str
    dark_note: str = ""
    flat_note: str = ""
    weak: bool = False
    no_calibration: bool = False
    flat_only: bool = False  # 8-bit colour lights: a colour flat and no dark

    @property
    def ok(self) -> bool:
        return self.no_calibration or (self.flat is not None and (self.dark is not None or self.flat_only))


def _temp(f: Frame) -> float | None:
    return f.set_temp_c if f.set_temp_c is not None else f.ccd_temp_c


def _same(a: object, b: object) -> bool:
    return a == b


def _night(f: Frame) -> date | None:
    if f.night is not None:
        return f.night.date
    return f.date_obs_utc.date() if f.date_obs_utc else None


def _fmt_t(t: float) -> str:
    return f"{t:g} °C".replace("-", "−")


def masters(kind: str) -> list[Frame]:
    return list(
        Frame.objects.filter(frame_type=kind, status=FrameStatus.CATALOGUED)
        .select_related("night")
        .prefetch_related("headers")
    )


def dims(f: Frame) -> tuple[int, int] | None:
    """Width and height from the header snapshot ("6024:4024" or "6000:4000:3"), when known."""
    snaps = list(f.headers.all())
    parts = [p for p in (snaps[0].geometry if snaps else "").split(":") if p.isdigit()]
    return (int(parts[0]), int(parts[1])) if len(parts) >= 2 else None


def is_colour_master(f: Frame) -> bool:
    """A master with three colour planes (built from 8-bit colour frames): it suits 8-bit colour lights only."""
    snaps = list(f.headers.all())
    parts = (snaps[0].geometry if snaps else "").split(":")
    return len(parts) >= 3 and parts[2] == "3"


def _windows() -> dict[str, tuple]:
    from .models import MasterWindow

    return {w.frame_id: (w.valid_from, w.valid_to) for w in MasterWindow.objects.all()}


def same_size(a: Frame, b: Frame) -> bool:
    """A master of another size can't calibrate a light; unknown on either side is allowed."""
    da, db = dims(a), dims(b)
    return da is None or db is None or da == db


def _size(f: Frame) -> str:
    d = dims(f)
    return f" at {d[0]}×{d[1]}" if d else ""


def match_dark(light: Frame, darks: list[Frame], tol: float) -> tuple[Frame | None, str, str]:
    """(dark, note, reason when none)"""
    if light.exptime_s is None:
        return None, "", "the sub has no exposure time"
    exp = [d for d in darks if d.exptime_s is not None and abs(d.exptime_s - light.exptime_s) < 0.01]
    if not exp:
        return None, "", f"no {light.exptime_s:g} s dark"
    if not [d for d in exp if same_size(d, light)]:
        return None, "", f"no {light.exptime_s:g} s dark{_size(light)}"
    exp = [d for d in exp if same_size(d, light)]
    same_cam = [d for d in exp if (d.camera or "") == (light.camera or "") or not d.camera]
    same_bin = [d for d in same_cam if (d.xbin or 1) == (light.xbin or 1)]
    if not same_bin:
        return None, "", f"no {light.exptime_s:g} s dark at binning {light.xbin or 1}"
    lt0 = light.ccd_temp_c if light.ccd_temp_c is not None else light.set_temp_c
    # A value only counts as missing if the light has it: DSLRs record neither offset nor temperature.
    missing = [
        d
        for d in same_bin
        if (light.gain is not None and d.gain is None)
        or (light.offset is not None and d.offset is None)
        or (lt0 is not None and _temp(d) is None)
    ]
    usable = [d for d in same_bin if d not in missing]
    if not usable:
        d = missing[0]
        what = [
            w for w, v in (("gain", d.gain), ("offset", d.offset), ("temperature", _temp(d))) if v is None
        ]
        return (
            None,
            "",
            (f"the {light.exptime_s:g} s dark has no {' or '.join(what)}: confirm it in Reconcile"),
        )
    fits = [d for d in usable if d.gain == light.gain and d.offset == light.offset]
    if not fits:
        return None, "", f"no {light.exptime_s:g} s dark at gain {light.gain} and offset {light.offset}"
    lt = light.ccd_temp_c if light.ccd_temp_c is not None else light.set_temp_c
    if lt is None:
        best = sorted(fits, key=lambda d: d.first_seen_at, reverse=True)[0]
        return best, "Exposure, gain and offset match; no sub temperature", ""
    near = [d for d in fits if abs(_temp(d) - lt) <= tol]  # type: ignore[operator]
    if not near:
        temps = ", ".join(sorted({_fmt_t(_temp(d)) for d in fits}))  # type: ignore[arg-type]
        return None, "", f"no {light.exptime_s:g} s dark within {tol:g} °C of {_fmt_t(lt)} (have {temps})"
    best = sorted(near, key=lambda d: (abs(_temp(d) - lt), -d.first_seen_at.timestamp()))[0]  # type: ignore[operator]
    diff = abs(_temp(best) - lt)  # type: ignore[operator]
    return best, "Exact match" if diff < 0.5 else f"{diff:.1f} °C apart", ""


def match_bias(light: Frame, biases: list[Frame]) -> Frame | None:
    """Stands in for a dark on rigs calibrated without darks: same camera and binning, the light's gain when
    both say, then the nearest night."""
    same = [
        b
        for b in biases
        if ((b.camera or "") == (light.camera or "") or not b.camera)
        and (b.xbin or 1) == (light.xbin or 1)
        and same_size(b, light)
    ]
    gain = [b for b in same if light.gain is not None and b.gain == light.gain]
    pool = gain or [b for b in same if b.gain is None or light.gain is None]
    if not pool:
        return None
    night = _night(light)
    return min(pool, key=lambda b: abs((_night(b) - night).days) if night and _night(b) else 10**6)  # type: ignore[operator]


def match_flat(
    light: Frame, flats: list[Frame], weak_days: int | None, later_ok: bool
) -> tuple[Frame | None, str, bool, str]:
    """(flat, note, weak, reason when none)"""
    filt = (light.filter_norm or "").casefold()
    if not filt:
        return None, "", False, "the sub has no filter"
    # a flat belongs to its optical train: same camera and, when both say, the same telescope or lens
    same = [
        f
        for f in flats
        if (f.filter_norm or "").casefold() == filt
        and (f.xbin or 1) == (light.xbin or 1)
        and ((f.camera or "") == (light.camera or "") or not f.camera)
        and (not f.telescope or not light.telescope or f.telescope == light.telescope)
        and same_size(f, light)
    ]
    night = _night(light)
    label = light.filter_norm
    if not same:
        return (
            None,
            "",
            False,
            f"no {label} flat" + (f" for {light.telescope}" if light.telescope else "") + _size(light),
        )
    if night is None:
        best = max(same, key=lambda f: f.first_seen_at)
        return best, "Latest flat (the sub has no date)", False, ""
    before = [f for f in same if _night(f) is not None and _night(f) <= night]  # type: ignore[operator]
    undated = [f for f in same if _night(f) is None]
    if before:
        best = max(before, key=lambda f: _night(f))  # type: ignore[arg-type, return-value]
        days = (night - _night(best)).days  # type: ignore[operator]
    elif later_ok and [f for f in same if f not in undated]:
        best = min((f for f in same if f not in undated), key=lambda f: _night(f))  # type: ignore[arg-type, return-value]
        days = (night - _night(best)).days  # type: ignore[operator]
    elif undated:
        best = max(undated, key=lambda f: f.first_seen_at)
        return best, "Flat with no date: its age is unknown", False, ""  # no evidence, so not weak (002 C19)
    else:
        return None, "", False, f"no {label} flat on or before {night:%-d %b}"
    when = (
        "Same night"
        if days == 0
        else f"{abs(days)} day{'s' if abs(days) != 1 else ''} {'before' if days > 0 else 'after'}"
    )
    weak = weak_days is not None and abs(days) > weak_days
    return best, (f"Weak: {when}" if weak else when), weak, ""


def _pending_flats(cache: dict) -> list[tuple[str, str, int, date]]:
    """Flat sets whose master is still being built: (filter, camera, binning, night). A light waits for one of
    these rather than settling for an older flat (owner 2026-10-11: lights calibrated from the first flat master
    built while the same night's flats were still queued)."""
    if "pending_flats" not in cache:
        from apps.catalogue.models import CalibrationSet

        rows = (
            CalibrationSet.objects.filter(
                type=FrameType.FLAT, built__state__in=["queued", "running"], night__isnull=False
            )
            .values_list("filter_norm", "camera", "xbin", "night__date")
            .distinct()
        )
        cache["pending_flats"] = [((f or "").casefold(), c or "", b or 1, n) for f, c, b, n in rows]
    return cache["pending_flats"]


def _closer_flat_pending(light: Frame, best: Frame | None, cache: dict, later_ok: bool) -> date | None:
    """The night of a flat set still being built that would suit this light better than `best`, if any."""
    night = _night(light)
    filt = (light.filter_norm or "").casefold()
    if night is None or not filt:
        return None
    best_night = _night(best) if best is not None else None
    candidates = [
        n
        for f, cam, b, n in _pending_flats(cache)
        if f == filt and (not cam or cam == (light.camera or "")) and b == (light.xbin or 1)
    ]
    before = [n for n in candidates if n <= night]
    if before:
        n = max(before)
        if best_night is None or best_night > night or n > best_night:
            return n
        return None
    if best is None and later_ok and candidates:
        return min(candidates)
    return None


def match(light: Frame, cache: dict | None = None) -> Match:
    rig = None
    if light.dataset_id and light.dataset:
        from apps.catalogue.services.library import ensure_rig

        rig = ensure_rig(light.dataset)
    if rig is not None and rig.calibration == "none":
        return Match(
            None, None, "", "Calibrated in the camera", "Calibrated in the camera", False, no_calibration=True
        )
    from .tasks import is_processed_rgb

    cfg = processing_settings()["calibration"]
    cache = cache if cache is not None else {}
    windows = cache.setdefault("windows", _windows())
    night = _night(light)

    def usable(pool: list[Frame]) -> list[Frame]:
        """Masters whose validity window (002 C13) covers this light's night."""
        if not windows or night is None:
            return pool
        return [
            f
            for f in pool
            if f.pk not in windows
            or (
                (windows[f.pk][0] is None or night >= windows[f.pk][0])
                and (windows[f.pk][1] is None or night <= windows[f.pk][1])
            )
        ]

    all_flats = usable(cache.setdefault("flats", masters(FrameType.MASTER_FLAT)))
    if is_processed_rgb(light):
        # 8-bit colour: no dark applies, but a colour flat from the same camera corrects vignetting and dust
        colour_flats = [f for f in all_flats if is_colour_master(f)]
        flat, fnote, weak, _ = match_flat(
            light, colour_flats, cfg["weak_flat_days"], cfg["later_flat_fallback"]
        )
        if flat is not None:
            return Match(
                None,
                flat,
                "",
                "No dark: 8-bit colour image",
                f"{fnote} · colour flat (approximate)",
                weak,
                flat_only=True,
            )
        note = "8-bit colour image, not raw: used uncalibrated (no 8-bit colour flat to divide by)"
        return Match(None, None, "", note, note, False, no_calibration=True)
    darks = usable(cache.setdefault("darks", masters(FrameType.MASTER_DARK)))
    flats = [f for f in all_flats if not is_colour_master(f)]
    dark, dnote, dwhy = match_dark(light, darks, cfg["temp_tolerance_c"])
    if dark is None and rig is not None and rig.calibration == "flats":
        dark = match_bias(light, usable(cache.setdefault("biases", masters(FrameType.MASTER_BIAS))))
        dnote, dwhy = (
            ("Master bias (rig uses no darks)", "")
            if dark
            else (
                "",
                f"no master bias for {light.camera or 'this camera'}"
                + (f" at gain {light.gain}" if light.gain is not None else "")
                + _size(light),
            )
        )
    if dark is None and light.ccd_temp_c is None and cfg.get("bias_for_uncooled", False):
        # an uncooled camera (a DSLR records no sensor temperature): with no dark at this exposure and ISO, bias
        # and flat are the usual calibration; said on every sub that gets it (owner 2026-10-13, the A7 III)
        from .tasks import planes

        bias = match_bias(light, usable(cache.setdefault("biases", masters(FrameType.MASTER_BIAS))))
        # a raw (one-layer) bias can't calibrate a light saved as colour planes: Siril refuses ("Images must have
        # same dimensions", 47 A7 III subs, 2026-10-13)
        if bias is not None and planes(bias) == planes(light):
            dark, dnote, dwhy = bias, "Master bias: no dark at this exposure and ISO (uncooled camera)", ""
        elif bias is not None:
            dwhy = (
                f"no {light.exptime_s:g} s dark, and the bias is raw while these subs are saved as colour images: "
                "calibrate them with darks or a bias saved the same way"
            )
    flat, fnote, weak, fwhy = match_flat(light, flats, cfg["weak_flat_days"], cfg["later_flat_fallback"])
    waiting = _closer_flat_pending(light, flat, cache, cfg["later_flat_fallback"])
    if waiting is not None:
        flat, fnote, weak = None, "", False
        fwhy = f"waiting for the {waiting:%-d %b} {light.filter_norm} flats to be built"
    why = [w for w in (dwhy, fwhy) if w]
    return Match(
        dark, flat, ("Awaiting calibration: " + "; ".join(why) + ".") if why else "", dnote, fnote, weak
    )


def update_match(light: Frame, cache: dict | None = None) -> CalibrationMatch | None:
    """Store the light's match. Returns it, or None for frames that aren't catalogued lights."""
    if light.frame_type != FrameType.LIGHT or light.status != FrameStatus.CATALOGUED:
        CalibrationMatch.objects.filter(frame=light).delete()
        return None
    existing = CalibrationMatch.objects.filter(frame=light).first()
    if existing is not None and existing.pinned:
        # keep what the user chose, but fill what they didn't: choosing a flat for a session left subs with no
        # dark pinned and waiting forever, with no reason shown (NGC 7000 Panel 2, 2026-10-13)
        if existing.pending_flat_set_id or (existing.dark_id and existing.flat_id):
            return existing
        m = match(light, cache)
        if not existing.dark_id and m.dark:
            existing.dark, existing.dark_note = m.dark, m.dark_note
        if not existing.flat_id and m.flat:
            existing.flat, existing.flat_note = m.flat, m.flat_note
        if existing.dark_id and existing.flat_id:
            existing.state, existing.reason = MatchState.MATCHED, ""
        elif existing.state != MatchState.MATCHED:
            existing.reason = m.reason
        existing.save()
        return existing
    m = match(light, cache)
    cm, _ = CalibrationMatch.objects.update_or_create(
        frame=light,
        defaults={
            "state": MatchState.MATCHED if m.ok else MatchState.AWAITING,
            "dark": m.dark,
            "flat": m.flat,
            "reason": m.reason,
            "dark_note": m.dark_note,
            "flat_note": m.flat_note,
            "weak": m.weak,
        },
    )
    return cm
