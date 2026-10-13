"""Night and dataset assignment (research R10; T055). Datasets span any number of nights; counts are
recomputed from the frames so they cannot drift."""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db.models import Count, Max, Min, Q, Sum

from apps.catalogue.models import Dataset, DatasetNight, Frame, FrameStatus, FrameType, Night, Verdict

_PANEL = re.compile(r"^(?P<target>.*\S)\s+panel\s+(?P<panel>\d+)$", re.IGNORECASE)


def split_object(obj: str | None) -> tuple[str | None, int | None]:
    """NINA mosaics name panels '<target> Panel <n>'."""
    if obj is None:
        return None, None
    s = obj.strip()
    if not s:
        return None, None
    m = _PANEL.match(s)
    if m:
        return m["target"].strip(), int(m["panel"])
    return s, None


@dataclass(frozen=True)
class DatasetKey:
    target: str
    panel: int | None
    filter_norm: str
    camera: str
    telescope: str
    xbin: int
    ybin: int
    gain: int | None
    offset: int | None

    @property
    def group_key(self) -> str:
        parts = [
            self.target,
            "" if self.panel is None else str(self.panel),
            self.filter_norm,
            self.camera,
            self.telescope,
            f"{self.xbin}x{self.ybin}",
            "" if self.gain is None else str(self.gain),
            "" if self.offset is None else str(self.offset),
        ]
        return "|".join(p.replace("|", "/") for p in parts)


def display_name(target: str, panel: int | None, filter_norm: str) -> str:
    return " · ".join([target, *([f"Panel {panel}"] if panel is not None else []), filter_norm])


def key_for(frame: Frame) -> DatasetKey | None:
    """None when a grouping field the user must provide is missing (target or filter)."""
    if not frame.target or not frame.filter_norm:
        return None
    return DatasetKey(
        target=frame.target,
        panel=frame.panel,
        filter_norm=frame.filter_norm,
        camera=frame.camera or "",
        telescope=frame.telescope or "",
        xbin=frame.xbin or 1,
        ybin=frame.ybin or frame.xbin or 1,
        gain=frame.gain,
        offset=frame.offset,
    )


def resolve_site_key(lat: float | None, lon: float | None) -> str:
    """Reuse an existing site within SAME_SITE_KM; otherwise a new key."""
    from apps.ingest.night import SAME_SITE_KM, distance_km, site_key

    if lat is None or lon is None:
        return "unknown"
    sites = Night.objects.exclude(site_lat=None).values_list("site_key", "site_lat", "site_lon").distinct()
    best = min(
        ((distance_km(lat, lon, a, b), k) for k, a, b in sites if a is not None and b is not None),
        default=None,
    )
    if best is not None and best[0] <= SAME_SITE_KM:
        return best[1]
    return site_key(lat, lon)


def night_for(date, lat: float | None, lon: float | None) -> Night:  # noqa: ANN001
    night, _ = Night.objects.get_or_create(
        site_key=resolve_site_key(lat, lon), date=date, defaults={"site_lat": lat, "site_lon": lon}
    )
    return night


def assign_dataset(frame: Frame) -> tuple[Dataset | None, Dataset | None]:
    """Set frame.dataset for lights. Returns (old, new) so both can be refreshed."""
    # a frame loaded a while ago (a batch of a long re-read) can name a dataset since removed: then it had none
    old = Dataset.objects.filter(pk=frame.dataset_id).first() if frame.dataset_id else None
    new = None
    if frame.frame_type == FrameType.LIGHT and frame.status == FrameStatus.CATALOGUED:
        key = key_for(frame)
        if key is not None:
            new, _ = Dataset.objects.get_or_create(
                group_key=key.group_key,
                defaults={
                    "target": key.target,
                    "panel": key.panel,
                    "filter_norm": key.filter_norm,
                    "camera": key.camera,
                    "telescope": key.telescope,
                    "xbin": key.xbin,
                    "ybin": key.ybin,
                    "gain": key.gain,
                    "offset": key.offset,
                    "display_name": display_name(key.target, key.panel, key.filter_norm),
                },
            )
    frame.dataset = new
    return old, new


def refresh_dataset(ds: Dataset | None) -> None:
    if ds is None:
        return
    lights = Frame.objects.filter(dataset=ds, status=FrameStatus.CATALOGUED, frame_type=FrameType.LIGHT)
    rejected = Q(verdicts__verdict=Verdict.REJECT)
    agg = lights.aggregate(
        n=Count("sha256", distinct=True),
        exp=Sum("exptime_s"),
        first=Min("date_obs_utc"),
        last=Max("date_obs_utc"),
    )
    ds.sub_count = agg["n"] or 0
    ds.integration_s = agg["exp"] or 0.0
    ds.first_utc, ds.last_utc = agg["first"], agg["last"]
    ds.user_rejected_count = lights.filter(rejected).values("sha256").distinct().count()
    ds.save(update_fields=["sub_count", "integration_s", "first_utc", "last_utc", "user_rejected_count"])
    per_night = (
        lights.exclude(night=None)
        .values("night")
        .annotate(
            n=Count("sha256", distinct=True),
            exp=Sum("exptime_s"),
            first=Min("date_obs_utc"),
            last=Max("date_obs_utc"),
        )
    )
    keep = []
    for row in per_night:
        rej = lights.filter(night=row["night"]).filter(rejected).values("sha256").distinct().count()
        dn, _ = DatasetNight.objects.update_or_create(
            dataset=ds,
            night_id=row["night"],
            defaults={
                "sub_count": row["n"],
                "integration_s": row["exp"] or 0.0,
                "first_utc": row["first"],
                "last_utc": row["last"],
                "user_rejected_count": rej,
            },
        )
        keep.append(dn.pk)
    DatasetNight.objects.filter(dataset=ds).exclude(pk__in=keep).delete()
    from .state import update_state

    update_state(ds)
    from apps.processing.effective import recount_grades

    recount_grades(ds)
