"""Installation settings (site, filter aliases, calibration, grading and stacking defaults; spec 008) and libraries."""

import os
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.processing.config import _merge, processing_settings
from apps.processing.grading import preview_regrade, regrade_datasets
from substation.api import ApiError, Router, Schema, Status, admin_required, is_admin
from substation.tasks import enqueue
from substation.tasks.models import Worker, WorkerState

from .models import InstallationSettings, Library

settings_router = Router(tags=["settings"])
libraries_router = Router(tags=["libraries"])


class SiteSchema(Schema):
    name: str | None = None
    lat: float | None = None
    lon: float | None = None


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


class LibraryIn(Schema):
    enabled: bool | None = None
    allow_delete: bool | None = None
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
        site=SiteSchema(name=lib.site_name, lat=lib.site_lat, lon=lib.site_lon),
        last_full_sweep_at=lib.last_full_sweep_at,
        frame_count=count,
        sweep_interval_active_s=lib.sweep_interval_active_s,
        sweep_interval_idle_s=lib.sweep_interval_idle_s,
        allow_delete=lib.allow_delete,
        writable=os.access(lib.mount_path, os.W_OK),
    )


def _counted():
    return Library.objects.annotate(
        n=Count("copies__frame", filter=Q(copies__present=True), distinct=True)
    ).order_by("name")


@libraries_router.get("", response=list[LibraryOut])
def list_libraries(request):
    return [_library_out(lib, lib.n) for lib in _counted()]


@libraries_router.patch("/{id}", response=LibraryOut)
@admin_required
def patch_library(request, id: int, body: LibraryIn):  # noqa: A002
    lib = get_object_or_404(Library, pk=id)
    data = body.dict(exclude_unset=True)
    if "enabled" in data and data["enabled"] is not None:
        lib.enabled = data["enabled"]
    if data.get("allow_delete") is not None:
        lib.allow_delete = data["allow_delete"]
    if data.get("site") is not None:
        site = data["site"]
        if site.get("lat") is not None and not -90 <= site["lat"] <= 90:
            raise ApiError(422, "invalid", "Latitude must be between −90 and 90 degrees.")
        if site.get("lon") is not None and not -180 <= site["lon"] <= 180:
            raise ApiError(422, "invalid", "Longitude must be between −180 and 180 degrees.")
        lib.site_name, lib.site_lat, lib.site_lon = site.get("name"), site.get("lat"), site.get("lon")
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


EDITABLE = {"calibration", "grading", "stacking", "notifications", "queue", "post", "paths", "bin", "backup"}
CHOICES = {
    ("stacking", "rejection"): {"winsorized", "sigma", "linear"},
    ("stacking", "weighting"): {"grade", "snr", "equal"},
    ("stacking", "reference"): {"best_fwhm", "most_stars", "manual"},
    ("stacking", "auto"): {"never", "session", "every_n"},
    ("stacking", "format"): {"fits"},  # Siril writes FITS
    ("grading", "profile"): {"standard", "spike"},
    ("queue", "priority_mode"): {"new_first", "in_order"},
}
# measures graded against the session median: [down-weight, reject] and the direction that is bad
LEVELS = {"fwhm": "above", "background": "above", "eccentricity": "above", "stars": "below"}


def _clean_processing(data: dict) -> dict:
    """Validate a partial calibration/grading/stacking change; messages follow the voice guide."""
    out: dict = {}
    for section, values in data.items():
        if section not in EDITABLE or not isinstance(values, dict):
            raise ApiError(422, "invalid", f"“{section}” can't be changed here.")
        if section == "notifications":
            from substation.notify import EVENTS

            for k in ("ntfy", "webhook"):
                if values.get(k) and not str(values[k]).startswith(("http://", "https://")):
                    raise ApiError(422, "invalid", f"The {k} address must start with http:// or https://.")
            if any(e not in EVENTS for e in values.get("events") or []):
                raise ApiError(422, "invalid", "Unknown notification event.")
            import re

            for k, label in (
                ("pushover_user", "Pushover user key"),
                ("pushover_token", "Pushover API token"),
            ):
                v = (values.get(k) or "").strip()
                if v and not re.fullmatch(r"[A-Za-z0-9]{30}", v):
                    raise ApiError(
                        422, "invalid", f"The {label} is 30 letters and digits, as Pushover shows it."
                    )
        if section == "backup":  # spec 014
            import re

            for k, v in values.items():
                if k == "enabled" and not isinstance(v, bool):
                    raise ApiError(422, "invalid", "Backups are on or off.")
                if k == "time" and not (isinstance(v, str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v)):
                    raise ApiError(422, "invalid", "The time is HH:MM, 24-hour.")
                if k == "keep" and not (isinstance(v, int) and 1 <= v <= 365):
                    raise ApiError(422, "invalid", "Keep between 1 and 365 backups.")
                if k == "folder" and not (isinstance(v, str) and (v == "" or v.startswith("/"))):
                    raise ApiError(
                        422, "invalid", "The folder is a path inside the containers, starting with /."
                    )
                if k not in ("enabled", "time", "keep", "folder"):
                    raise ApiError(422, "invalid", f"Unknown backup setting {k}.")
        if section == "bin":
            for k, v in values.items():
                if k not in ("auto_bin_rejected_days", "purge_after_days") or not isinstance(v, int) or v < 0:
                    raise ApiError(422, "invalid", "Days must be a whole number, 0 or more.")
            if values.get("purge_after_days") == 0:
                raise ApiError(422, "invalid", "Keep binned files at least a day before they're deleted.")
        for k, v in values.items():
            if (section, k) in CHOICES and v not in CHOICES[(section, k)]:
                raise ApiError(
                    422,
                    "invalid",
                    f"{k.capitalize()} must be one of {', '.join(sorted(CHOICES[(section, k)]))}.",
                )
            if section == "grading" and k in LEVELS:
                if not (
                    isinstance(v, list)
                    and len(v) == 2
                    and all(isinstance(x, int | float) and x > 0 for x in v)
                ):
                    raise ApiError(
                        422,
                        "invalid",
                        f"{k.upper() if k == 'fwhm' else k.capitalize()} needs a "
                        "down-weight and a reject level, both above zero.",
                    )
                down, reject = v
                if (LEVELS[k] == "above" and reject <= down) or (LEVELS[k] == "below" and reject >= down):
                    raise ApiError(
                        422,
                        "invalid",
                        f"{k.upper() if k == 'fwhm' else k.capitalize()}: reject level must be "
                        f"{LEVELS[k]} the down-weight level.",
                    )
            if (
                section == "calibration"
                and k == "temp_tolerance_c"
                and not (isinstance(v, int | float) and 0.5 <= v <= 10)
            ):
                raise ApiError(422, "invalid", "Dark temperature tolerance must be 0.5–10 °C.")
            if (
                section == "stacking"
                and k == "auto_quiet_hours"
                and not (isinstance(v, int | float) and 0.5 <= v <= 24)
            ):
                raise ApiError(422, "invalid", "Quiet time must be 0.5–24 hours.")
            if section == "stacking" and k == "auto_every_n" and not (isinstance(v, int) and 3 <= v <= 1000):
                raise ApiError(422, "invalid", "N must be 3–1,000.")
            if (
                section == "stacking"
                and k == "sigma"
                and not (
                    isinstance(v, list)
                    and len(v) == 2
                    and all(isinstance(x, int | float) and 0.5 <= x <= 10 for x in v)
                )
            ):
                raise ApiError(422, "invalid", "Sigma low and high must be 0.5–10.")
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


@settings_router.patch("", response=SettingsOut)
@admin_required
def patch_settings(request, body: SettingsIn):  # type: ignore[no-untyped-def]
    s = InstallationSettings.load()
    data = body.dict(exclude_unset=True)
    if "site_lat" in data and data["site_lat"] is not None and not -90 <= data["site_lat"] <= 90:
        raise ApiError(422, "invalid", "Latitude must be between −90 and 90 degrees.")
    if "site_lon" in data and data["site_lon"] is not None and not -180 <= data["site_lon"] <= 180:
        raise ApiError(422, "invalid", "Longitude must be between −180 and 180 degrees.")
    if "filter_aliases" in data and data["filter_aliases"] is not None:
        data["filter_aliases"] = {k.strip().casefold(): v.strip() for k, v in data["filter_aliases"].items()}
    if data.get("worker_count") is not None and not 1 <= data["worker_count"] <= 16:
        raise ApiError(422, "invalid", "Workers must be between 1 and 16.")
    if "siril_heavy_slots" in data:
        heavy = data["siril_heavy_slots"]
        workers = data.get("worker_count") or s.worker_count or settings.SUBSTATION_WORKERS
        if heavy is None or not 1 <= heavy <= min(4, workers):
            raise ApiError(422, "invalid", f"Stacking slots must be 1–{min(4, workers)}.")
    if data.get("siril_threads") is not None and not 1 <= data["siril_threads"] <= (os.cpu_count() or 64):
        raise ApiError(422, "invalid", f"Siril threads must be 1–{os.cpu_count() or 64}.")
    if data.get("siril_mem_ratio") is not None and not 0.05 <= data["siril_mem_ratio"] <= 0.9:
        raise ApiError(422, "invalid", "Memory share must be 5–90%.")
    if data.get("stack_threads") is not None and not 1 <= data["stack_threads"] <= 256:
        raise ApiError(422, "invalid", "Stacking threads must be 1–256.")
    if data.get("stack_mem_ratio") is not None and not 0.1 <= data["stack_mem_ratio"] <= 0.95:
        raise ApiError(422, "invalid", "Stacking memory share must be 10–95%.")
    if data.get("work_budget_gb") is not None and not 5 <= data["work_budget_gb"] <= 20000:
        raise ApiError(422, "invalid", "Work budget must be 5 GB–20 TB.")
    regrade = data.pop("regrade", False)
    change = _clean_processing(data.pop("processing", None) or {})
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
