"""Installation settings (site, filter aliases, calibration, grading and stacking defaults; spec 008) and libraries."""

import os
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.processing.config import _merge, processing_settings
from apps.processing.grading import preview_regrade, regrade_datasets
from substation.api import ApiError, Router, Schema, Status, admin_required, is_admin
from substation.tasks import enqueue
from substation.tasks.models import Worker, WorkerState

from .access import is_writable, read_only_reason
from .models import InstallationSettings, Library, LibraryRole

settings_router = Router(tags=["settings"])
libraries_router = Router(tags=["libraries"])


class SiteSchema(Schema):
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    region: str = ""  # spec 020: the only place name the render API shares
    bortle: int | None = None  # spec 020: 1-9


class LibraryOut(Schema):
    id: int
    name: str
    mount_path: str
    enabled: bool
    status: str
    site: SiteSchema
    last_full_sweep_at: datetime | None
    frame_count: int
    sweep_interval_active_s: int
    sweep_interval_idle_s: int
    allow_delete: bool = False  # SubStation may move binned files to quarantine and delete them (spec 011)
    writable: bool = False  # the library is mounted so SubStation can write to it
    # why not, naming the setting that mounts it read-write; none when it is writable (specs 011, 013)
    read_only_reason: str | None = None
    role: Literal["", "active", "archive", "completed"] = ""  # spec 013/020: where its collections live
    archive_to: int | None = None  # an active library's archive library


class LibraryIn(Schema):
    enabled: bool | None = None
    allow_delete: bool | None = None
    role: Literal["", "active", "archive", "completed"] | None = None
    archive_to: int | None = None  # sent as null: no archive library
    site: SiteSchema | None = None
    sweep_interval_active_s: int | None = None
    sweep_interval_idle_s: int | None = None


def _library_out(lib: Library, count: int) -> LibraryOut:
    return LibraryOut(
        id=lib.pk,
        name=lib.name,
        mount_path=lib.mount_path,
        enabled=lib.enabled,
        status=lib.status,
        site=SiteSchema(
            name=lib.site_name,
            lat=lib.site_lat,
            lon=lib.site_lon,
            region=lib.site_region,
            bortle=lib.site_bortle,
        ),
        last_full_sweep_at=lib.last_full_sweep_at,
        frame_count=count,
        sweep_interval_active_s=lib.sweep_interval_active_s,
        sweep_interval_idle_s=lib.sweep_interval_idle_s,
        allow_delete=lib.allow_delete,
        writable=is_writable(lib),
        read_only_reason=read_only_reason(lib),
        role=lib.role or "",  # type: ignore[arg-type]
        archive_to=lib.archive_to_id,
    )


def _counted():
    return Library.objects.annotate(
        n=Count("copies__frame", filter=Q(copies__present=True), distinct=True)
    ).order_by("name")


@libraries_router.get("", response=list[LibraryOut])
def list_libraries(request):
    return [_library_out(lib, lib.n) for lib in _counted()]


def _apply_site(lib: Library, site: dict) -> None:
    if site.get("lat") is not None and not -90 <= site["lat"] <= 90:
        raise ApiError(422, "invalid", "Latitude must be between −90 and 90 degrees.")
    if site.get("lon") is not None and not -180 <= site["lon"] <= 180:
        raise ApiError(422, "invalid", "Longitude must be between −180 and 180 degrees.")
    if site.get("bortle") is not None and not 1 <= site["bortle"] <= 9:
        raise ApiError(422, "invalid", "Bortle class must be 1–9.")
    lib.site_name, lib.site_lat, lib.site_lon = site.get("name"), site.get("lat"), site.get("lon")
    lib.site_region, lib.site_bortle = (site.get("region") or "").strip()[:100], site.get("bortle")


def _apply_roles(lib: Library, data: dict) -> None:
    """Spec 013: a library's role and an active library's archive. Only libraries mounted read-write take part, as
    the owner set out: a read-only one can't be archived to or brought back from."""
    if data.get("role") is not None and data["role"] != lib.role:
        # spec 020: a Completed library is only read (and maybe given project.json files), so read-only is fine
        if data["role"] not in ("", LibraryRole.COMPLETED) and (why := read_only_reason(lib)):
            raise ApiError(422, "read_only", why)
        if lib.role == LibraryRole.ARCHIVE:  # no longer an archive: active libraries stop pointing at it
            Library.objects.filter(archive_to=lib).update(archive_to=None)
        lib.role = data["role"]
        if lib.role != LibraryRole.ACTIVE:
            lib.archive_to = None
    if "archive_to" in data:
        lib.archive_to = _archive_target(lib, data["archive_to"])


def _archive_target(lib: Library, target_id: int | None) -> Library | None:
    if target_id is None:
        return None
    if lib.role != LibraryRole.ACTIVE:
        raise ApiError(422, "invalid", "Only an active library has an archive library.")
    target = Library.objects.filter(pk=target_id).first()
    if target is None or target.pk == lib.pk or target.role != LibraryRole.ARCHIVE:
        raise ApiError(422, "invalid", "Choose a library set as an archive.")
    if why := read_only_reason(target):
        raise ApiError(422, "read_only", f"{target.name}: {why}")
    return target


@libraries_router.patch("/{id}", response=LibraryOut)
@admin_required
def patch_library(request, id: int, body: LibraryIn):  # noqa: A002
    lib = get_object_or_404(Library, pk=id)
    data = body.dict(exclude_unset=True)
    if "enabled" in data and data["enabled"] is not None:
        lib.enabled = data["enabled"]
    if data.get("allow_delete") is not None:
        if data["allow_delete"] and (why := read_only_reason(lib)):
            raise ApiError(422, "read_only", why)
        lib.allow_delete = data["allow_delete"]
    _apply_roles(lib, data)
    if data.get("site") is not None:
        _apply_site(lib, data["site"])
    for k in ("sweep_interval_active_s", "sweep_interval_idle_s"):
        if data.get(k) is not None:
            if data[k] < 10:
                raise ApiError(422, "invalid", "Sweep intervals must be at least 10 seconds.")
            setattr(lib, k, data[k])
    lib.save()
    return _library_out(lib, _counted().get(pk=lib.pk).n)


@libraries_router.post("/{id}/rescan", response={202: dict})
def rescan_library(request, id: int):  # noqa: A002
    lib = get_object_or_404(Library, pk=id)
    Library.objects.filter(pk=lib.pk).update(rescan_requested_at=timezone.now())
    return Status(202, {"message": f"Scanning {lib.name}."})


class SettingsOut(Schema):
    site_name: str | None
    site_lat: float | None
    site_lon: float | None
    site_region: str = ""  # spec 020
    site_bortle: int | None = None  # spec 020
    filter_aliases: dict[str, str]
    worker_count: int | None
    siril_heavy_slots: int
    work_budget_gb: float = 150
    siril_threads: int | None = None
    siril_mem_ratio: float | None = None
    siril_mem_effective: float | None = None
    stack_threads: int | None = None  # while stacking (005-DR-16); none: every core
    stack_mem_ratio: float | None = None  # while stacking; none: 0.8
    cores: int = 1  # what a worker container has
    updated_by: str | None
    processing: dict
    cpu_threads: int
    workers_alive: int
    can_edit: bool = False


class SettingsIn(Schema):
    site_name: str | None = None
    site_lat: float | None = None
    site_lon: float | None = None
    site_region: str | None = None
    site_bortle: int | None = None
    filter_aliases: dict[str, str] | None = None
    # calibration, grading and stacking, partial (spec 008); other processing keys are managed elsewhere
    processing: dict | None = None
    regrade: bool = False
    worker_count: int | None = None
    siril_heavy_slots: int | None = None
    work_budget_gb: float | None = None
    siril_threads: int | None = None
    siril_mem_ratio: float | None = None
    stack_threads: int | None = None
    stack_mem_ratio: float | None = None


class SettingsPreviewIn(Schema):
    processing: dict


class RegradePreviewOut(Schema):
    dataset_id: int
    dataset: str
    changes: int
    by_change: dict[str, int]


EDITABLE = {
    "calibration",
    "grading",
    "stacking",
    "notifications",
    "queue",
    "post",
    "paths",
    "bin",
    "backup",
    "archive",
    "previews",
}
CHOICES = {
    ("stacking", "rejection"): {"winsorized", "sigma", "linear"},
    ("stacking", "weighting"): {"grade", "snr", "equal"},
    ("stacking", "reference"): {"best_fwhm", "most_stars", "manual"},
    ("stacking", "auto"): {"never", "session", "every_n"},
    ("stacking", "format"): {"fits"},  # Siril writes FITS
    ("grading", "profile"): {"standard", "spike"},
    ("queue", "priority_mode"): {"new_first", "in_order"},
    ("previews", "mode"): {"session", "sub"},
}
# measures graded against the session median: [down-weight, reject] and the direction that is bad
LEVELS = {"fwhm": "above", "background": "above", "eccentricity": "above", "stars": "below"}


def _invalid(message: str) -> ApiError:
    return ApiError(422, "invalid", message)


def _check_notifications(values: dict) -> None:
    from substation.notify import EVENTS

    for k in ("ntfy", "webhook"):
        if values.get(k) and not str(values[k]).startswith(("http://", "https://")):
            raise _invalid(f"The {k} address must start with http:// or https://.")
    if any(e not in EVENTS for e in values.get("events") or []):
        raise _invalid("Unknown notification event.")
    for k, label in (("pushover_user", "Pushover user key"), ("pushover_token", "Pushover API token")):
        v = (values.get(k) or "").strip()
        if v and not re.fullmatch(r"[A-Za-z0-9]{30}", v):
            raise _invalid(f"The {label} is 30 letters and digits, as Pushover shows it.")


# spec 014: each backup setting and what makes it valid
_BACKUP_RULES: dict[str, tuple[Callable[[object], bool], str]] = {
    "enabled": (lambda v: isinstance(v, bool), "Backups are on or off."),
    "time": (
        lambda v: isinstance(v, str) and bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v)),
        "The time is HH:MM, 24-hour.",
    ),
    "keep": (lambda v: isinstance(v, int) and 1 <= v <= 365, "Keep between 1 and 365 backups."),
    "folder": (
        lambda v: isinstance(v, str) and (v == "" or v.startswith("/")),
        "The folder is a path inside the containers, starting with /.",
    ),
}


def _check_backup(values: dict) -> None:
    for k, v in values.items():
        if k not in _BACKUP_RULES:
            raise _invalid(f"Unknown backup setting {k}.")
        ok, message = _BACKUP_RULES[k]
        if not ok(v):
            raise _invalid(message)


def _check_bin(values: dict) -> None:
    for k, v in values.items():
        if k not in ("auto_bin_rejected_days", "purge_after_days") or not isinstance(v, int) or v < 0:
            raise _invalid("Days must be a whole number, 0 or more.")
    if values.get("purge_after_days") == 0:
        raise _invalid("Keep binned files at least a day before they're deleted.")


def _check_level(k: str, v: object) -> None:
    """A graded measure's [down-weight, reject] pair: both above zero, reject on the bad side of down-weight."""
    name = k.upper() if k == "fwhm" else k.capitalize()
    if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, int | float) and x > 0 for x in v)):
        raise _invalid(f"{name} needs a down-weight and a reject level, both above zero.")
    down, reject = v
    if (LEVELS[k] == "above" and reject <= down) or (LEVELS[k] == "below" and reject >= down):
        raise _invalid(f"{name}: reject level must be {LEVELS[k]} the down-weight level.")


def _number_in(lo: float, hi: float, *, whole: bool = False) -> Callable[[object], bool]:
    kinds = int if whole else int | float
    return lambda v: isinstance(v, kinds) and lo <= v <= hi  # type: ignore[operator]


# single values with a range: (section, key) → (check, message)
_RANGES: dict[tuple[str, str], tuple[Callable[[object], bool], str]] = {
    ("calibration", "temp_tolerance_c"): (
        _number_in(0.5, 10),
        "Dark temperature tolerance must be 0.5–10 °C.",
    ),
    ("stacking", "auto_quiet_hours"): (_number_in(0.5, 24), "Quiet time must be 0.5–24 hours."),
    ("stacking", "auto_every_n"): (_number_in(3, 1000, whole=True), "N must be 3–1,000."),
    ("post", "max_megapixels"): (
        _number_in(50, 10000, whole=True),
        "The largest image to post-process must be 50–10,000 megapixels.",
    ),
    ("previews", "black_point"): (_number_in(-2, 2), "Black point must be −2 to +2."),
    ("previews", "background"): (_number_in(0.1, 0.4), "Sky brightness must be 10–40%."),
    ("stacking", "sigma"): (
        lambda v: isinstance(v, list) and len(v) == 2 and all(_number_in(0.5, 10)(x) for x in v),
        "Sigma low and high must be 0.5–10.",
    ),
}


def _check_archive(values: dict) -> None:
    for k, v in values.items():
        if k != "suggest_after_days" or not isinstance(v, int) or not 0 <= v <= 3650:
            raise _invalid("Days without new subs must be a whole number from 0 to 3,650.")


_SECTION_CHECKS: dict[str, Callable[[dict], None]] = {
    "notifications": _check_notifications,
    "backup": _check_backup,
    "bin": _check_bin,
    "archive": _check_archive,
}


def _check_value(section: str, k: str, v: object) -> None:
    if (section, k) in CHOICES and v not in CHOICES[(section, k)]:
        raise _invalid(f"{k.capitalize()} must be one of {', '.join(sorted(CHOICES[(section, k)]))}.")
    if section == "grading" and k in LEVELS:
        _check_level(k, v)
    if (section, k) in _RANGES:
        ok, message = _RANGES[(section, k)]
        if not ok(v):
            raise _invalid(message)


def _clean_processing(data: dict) -> dict:
    """Validate a partial calibration/grading/stacking change; messages follow the voice guide."""
    out: dict = {}
    for section, values in data.items():
        if section not in EDITABLE or not isinstance(values, dict):
            raise _invalid(f"“{section}” can't be changed here.")
        if section in _SECTION_CHECKS:
            _SECTION_CHECKS[section](values)
        for k, v in values.items():
            _check_value(section, k, v)
        out[section] = values
    return out


def _mem_effective() -> float | None:
    try:
        from apps.engine.siril import limits

        return limits()[1]
    except Exception:  # noqa: BLE001
        return None


def _out(s: InstallationSettings) -> SettingsOut:
    return SettingsOut(
        site_name=s.site_name,
        site_region=s.site_region,
        site_bortle=s.site_bortle,
        site_lat=s.site_lat,
        site_lon=s.site_lon,
        filter_aliases=s.filter_aliases or {},
        worker_count=s.worker_count,
        siril_heavy_slots=s.siril_heavy_slots,
        work_budget_gb=s.work_budget_gb or settings.STACK_WORK_BUDGET_GB,
        siril_threads=s.siril_threads,
        siril_mem_ratio=s.siril_mem_ratio,
        stack_threads=s.stack_threads,
        stack_mem_ratio=s.stack_mem_ratio,
        cores=os.cpu_count() or 1,
        siril_mem_effective=_mem_effective(),
        updated_by=s.updated_by.get_username() if s.updated_by else None,
        processing={k: v for k, v in processing_settings().items() if k in EDITABLE},
        cpu_threads=os.cpu_count() or 1,
        workers_alive=Worker.objects.filter(heartbeat_at__gte=timezone.now() - timedelta(seconds=30))
        .exclude(state=WorkerState.STOPPED)
        .count(),
    )


@settings_router.get("", response=SettingsOut)
def get_settings(request):  # type: ignore[no-untyped-def]
    out = _out(InstallationSettings.load())
    out.can_edit = is_admin(request.user)
    if not out.can_edit and isinstance(out.processing.get("notifications"), dict):
        # keys and private topics are for admins: other users see that a channel is set, not what it is
        out.processing["notifications"] = {
            k: ("set" if v and k != "events" else v) for k, v in out.processing["notifications"].items()
        }
    return out


# installation values with a range: field → (lowest, highest, message); None leaves a field unset
_INSTALL_RANGES: dict[str, tuple[float, float, str]] = {
    "site_lat": (-90, 90, "Latitude must be between −90 and 90 degrees."),
    "site_lon": (-180, 180, "Longitude must be between −180 and 180 degrees."),
    "site_bortle": (1, 9, "Bortle class must be 1–9."),
    "worker_count": (1, 16, "Workers must be between 1 and 16."),
    "siril_mem_ratio": (0.05, 0.9, "Memory share must be 5–90%."),
    "stack_threads": (1, 256, "Stacking threads must be 1–256."),
    "stack_mem_ratio": (0.1, 0.95, "Stacking memory share must be 10–95%."),
    "work_budget_gb": (5, 20000, "Work budget must be 5 GB–20 TB."),
}


def _check_installation(data: dict, s: InstallationSettings) -> None:
    for k, (lo, hi, message) in _INSTALL_RANGES.items():
        if data.get(k) is not None and not lo <= data[k] <= hi:
            raise _invalid(message)
    if "siril_heavy_slots" in data:
        heavy = data["siril_heavy_slots"]
        workers = data.get("worker_count") or s.worker_count or settings.SUBSTATION_WORKERS
        if heavy is None or not 1 <= heavy <= min(4, workers):
            raise _invalid(f"Stacking slots must be 1–{min(4, workers)}.")
    cores = os.cpu_count() or 64
    if data.get("siril_threads") is not None and not 1 <= data["siril_threads"] <= cores:
        raise _invalid(f"Siril threads must be 1–{cores}.")


@settings_router.patch("", response=SettingsOut)
@admin_required
def patch_settings(request, body: SettingsIn):  # type: ignore[no-untyped-def]
    s = InstallationSettings.load()
    data = body.dict(exclude_unset=True)
    _check_installation(data, s)
    if "filter_aliases" in data and data["filter_aliases"] is not None:
        data["filter_aliases"] = {k.strip().casefold(): v.strip() for k, v in data["filter_aliases"].items()}
    if "site_region" in data:  # spec 020: blank, never null
        data["site_region"] = (data["site_region"] or "").strip()[:100]
    regrade = data.pop("regrade", False)
    change = _clean_processing(data.pop("processing", None) or {})
    before = processing_settings()
    affected = (
        [
            r["dataset_id"]
            for r in preview_regrade(change.get("grading") and {"grading": change["grading"]} or {})
        ]
        if regrade and "grading" in change
        else []
    )
    for k, v in data.items():
        setattr(s, k, v)
    if change:
        merged = _merge(s.processing or {}, change)
        if "grading" in change:  # grades record the thresholds version they were made with
            merged.setdefault("grading", {})["version"] = (
                int(processing_settings()["grading"].get("version", 1)) + 1
            )
        s.processing = merged
    s.updated_by = request.user
    s.save()
    if affected:
        enqueue(regrade_datasets, affected, dedupe_key="regrade")
    if "previews" in change and _merge(before["previews"], change["previews"]) != before["previews"]:
        # 003 amendment 2026-10-24: every session's previews redrawn in the background, one job per session
        from apps.processing.tasks import rerender_all_sessions

        enqueue(rerender_all_sessions, dedupe_key="rerender-all-sessions")
    if "calibration" in change:  # tolerance or fallback changed: every light's match is checked again
        from apps.processing.tasks import rematch_lights

        enqueue(rematch_lights, dedupe_key="rematch-lights", fresh=True)
    return _out(s)


class NotifyTestOut(Schema):
    sent: bool
    failed: list[str]


@settings_router.post("/notifications/test", response=NotifyTestOut)
@admin_required
def test_notification(request):  # type: ignore[no-untyped-def]
    from substation.notify import config, send

    cfg = config()
    if not (
        cfg.get("ntfy") or cfg.get("webhook") or (cfg.get("pushover_user") and cfg.get("pushover_token"))
    ):
        raise ApiError(422, "invalid", "Add an ntfy topic, a webhook or Pushover keys first.")
    failed = send("test", "SubStation test", "Test notification.", cfg=cfg)
    return NotifyTestOut(sent=not failed, failed=failed)


@settings_router.post("/preview", response=list[RegradePreviewOut])
@admin_required
def preview_settings(request, body: SettingsPreviewIn):  # type: ignore[no-untyped-def]
    """The datasets a grading change would re-grade, and how their verdicts would change (008-DR-04)."""
    change = _clean_processing(body.processing)
    return preview_regrade({"grading": change["grading"]}) if "grading" in change else []


class SourceUse(Schema):
    field: str
    source: str
    detail: str
    frames: int


@settings_router.get("/sources", response=list[SourceUse])
def sources_in_use(request):
    """Where each value the catalogue uses comes from (008-DR-01): header keyword, path pattern or you, with how many
    files each one decided."""
    from django.db.models import Count

    from apps.catalogue.models import MetadataValue

    rows = (
        MetadataValue.objects.filter(is_winner=True)
        .values("field", "source", "source_detail")
        .annotate(n=Count("id"))
        .order_by("field", "-n")
    )
    return [
        SourceUse(field=r["field"], source=r["source"], detail=r["source_detail"] or "", frames=r["n"])
        for r in rows
    ]
