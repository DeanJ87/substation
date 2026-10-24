"""Calibration, grading and stacking settings, stored on InstallationSettings.processing, with the defaults
from the specs (002 FR-008, 003 v2 amendment, 004 v2 amendment)."""

from __future__ import annotations

import copy

DEFAULTS: dict = {
    "calibration": {
        "temp_tolerance_c": 2.0,
        "later_flat_fallback": False,
        "weak_flat_days": None,  # opt-in; age alone is not evidence (spec 002, owner amendment)
        # cameras that record no sensor temperature (DSLRs): bias stands in when no dark matches (owner 2026-10-13)
        "bias_for_uncooled": False,  # owner 2026-10-13
        # 002-DR-23: build a master once a calibration session has settled, and retry a blocked one when what it
        # waited for (a bias, a dark flat) has been built
        "auto_build": True,
    },
    "grading": {
        "version": 1,
        "profile": "standard",
        # relative to the session median: [down-weight, reject]
        "fwhm": [1.20, 1.50],
        "stars": [0.70, 0.50],
        "background": [1.20, 1.40],
        # absolute
        "eccentricity": [0.50, 0.65],
        "min_session": 5,
        "use_conditions": True,  # SQM and cloud flag a sub (never reject it alone) when recorded
    },
    # The spike grader (docs/spikes phase 1 and 2), for validation: wFWHM, stars, background, roundness
    "spike_profile": {"wfwhm": 1.5, "stars": 0.6, "background": 2.0, "roundness": 0.85},
    # equipment aliases (rig merges, spec 006 FR-001): header name -> the name it is the same as
    "equipment": {"camera": {}, "telescope": {}, "rig": {}},
    "notifications": {
        "ntfy": "",
        "webhook": "",
        "pushover_user": "",  # 008-DR-13: Pushover user (or group) key and the application's API token
        "pushover_token": "",
        "events": ["master_finished", "job_failed"],
    },
    # 008-DR-05: new subs jump the queue (so tonight's session is graded as it comes in), or everything in order
    "queue": {"priority_mode": "new_first"},
    # the bin (spec 011): rejected subs binned after this many days (0: never), binned files deleted after this
    "bin": {"auto_bin_rejected_days": 30, "purge_after_days": 30},
    # spec 013: suggest archiving a collection once no sub has been shot for this many days (0: never suggest)
    "archive": {"suggest_after_days": 60},
    # spec 014: a daily database backup into a folder the containers can see; empty folder = the station's backups
    "backup": {"enabled": True, "time": "03:30", "keep": 14, "folder": ""},
    # owner 2026-10-12: show files where people can open them, not as downloads. Each entry maps a server path
    # prefix to how it looks from a viewer's machine (e.g. /data/library/organised -> Z:\\Photography\\Deep Sky\\Organised);
    # a browser can override these for itself.
    "paths": {"map": []},
    # spec 010: after a master integrates, an optional chain of finishing tools; the master itself is never touched
    "post": {
        "enabled": False,
        "steps": [
            {"step": "background", "enabled": True, "correction": "Subtraction", "smoothing": 0.1},
            {
                "step": "deconvolve",
                "enabled": True,
                "sharpen_stars": 0.25,
                "adjust_halos": 0.0,
                "sharpen_nonstellar": 0.5,
            },
            {"step": "denoise", "enabled": True, "amount": 0.5},
            {"step": "starless", "enabled": False, "stars_only": True},
        ],
        "graxpert": "",  # executable paths; empty = look on PATH
        "rc_astro": "",
        "gpu": True,
        "timeout_s": 3600,
        # 2026-10-24: a bigger image (a mosaic canvas) is refused with the reason instead of exhausting the worker
        "max_megapixels": 1000,
    },
    # 003 amendment 2026-10-24: how sub previews and glances are stretched. "session": one stretch per night and
    # dataset (the median of its subs'), so frames compare fairly; "sub": each frame on its own. `black_point`
    # moves the shadow clip by that many noise sigmas (+ darker sky, − lighter); `background` is the grey level the
    # sky is drawn at (0.25 = a quarter). Masters keep their own stretch.
    "previews": {"mode": "session", "black_point": 0.0, "background": 0.25},
    "stacking": {
        "rejection": "winsorized",
        "sigma": [3.0, 3.0],
        "weighting": "grade",
        "reference": "best_fwhm",
        "auto": "never",
        "auto_quiet_hours": 3,  # "after each session": no new subs for this long (covers dawn)
        "auto_every_n": 30,  # "every N new subs"
        "format": "fits",
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def processing_settings() -> dict:
    from apps.libraries.models import InstallationSettings

    return _merge(DEFAULTS, InstallationSettings.load().processing or {})
