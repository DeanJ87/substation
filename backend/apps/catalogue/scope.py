"""One scope for every list (spec 018): the same optional inputs (place, nights, rig, camera, filter, collection,
project, dataset, target, free text) mean the same thing on every list endpoint, and one place turns them into a
query for each kind of record."""

from __future__ import annotations

import datetime as dt
import math

from django.db.models import Q, QuerySet
from ninja import Schema


class Scope(Schema):
    site: str | None = None  # a place's site key ("54.99,-1.66")
    lat: float | None = None  # or near a point
    lon: float | None = None
    within_km: float | None = None
    date: dt.date | None = None  # one observing night
    date_from: dt.date | None = None  # a range of nights, either end open
    date_to: dt.date | None = None
    camera: str | None = None
    rig: int | None = None
    telescope: str | None = None
    filter: str | None = None
    collection: int | None = None
    project: int | None = None
    dataset: int | None = None
    target: str | None = None
    q: str | None = None  # free text, as the search bar reads it (names, months, "last night")

    def is_empty(self) -> bool:
        return not any(v not in (None, "") for v in self.dict().values())


# where each input lives, per kind of record: the path from that record to the field
_PATHS: dict[str, dict[str, str]] = {
    "frame": {
        "site": "night__site_key",
        "night": "night__",
        "lat": "site_lat",
        "lon": "site_lon",
        "camera": "camera",
        "rig": "dataset__rig_id",
        "telescope": "telescope",
        "filter": "filter_norm",
        "collection": "dataset__collection_id",
        "project": "dataset__project_id",
        "dataset": "dataset_id",
        "target": "target",
        "text": "dataset__display_name",
        "collection_name": "dataset__collection__name",
        "rig_name": "dataset__rig__name",
        "filter_text": "filter_norm",
    },
    "dataset": {
        "site": "nights__night__site_key",
        "night": "nights__night__",
        "camera": "camera",
        "rig": "rig_id",
        "telescope": "telescope",
        "filter": "filter_norm",
        "collection": "collection_id",
        "project": "project_id",
        "dataset": "pk",
        "target": "target",
        "text": "display_name",
        "collection_name": "collection__name",
        "rig_name": "rig__name",
        "filter_text": "filter_norm",
    },
    "night": {
        "site": "site_key",
        "night": "",
        "lat": "site_lat",
        "lon": "site_lon",
        "camera": "dataset_nights__dataset__camera",
        "rig": "dataset_nights__dataset__rig_id",
        "telescope": "dataset_nights__dataset__telescope",
        "filter": "dataset_nights__dataset__filter_norm",
        "collection": "dataset_nights__dataset__collection_id",
        "project": "dataset_nights__dataset__project_id",
        "dataset": "dataset_nights__dataset_id",
        "target": "dataset_nights__dataset__target",
    },
    # calibration has no dataset or rig of its own: a rig narrows it to the rig's camera ("rig_camera")
    "set": {
        "site": "night__site_key",
        "night": "night__",
        "camera": "camera",
        "rig_camera": "camera",
        "filter": "filter_norm",
        "text": "type",
        "filter_text": "filter_norm",
        "camera_text": "camera",
    },
    "master": {
        "site": "night__site_key",
        "night": "night__",
        "camera": "camera",
        "rig_camera": "camera",
        "telescope": "telescope",
        "filter": "filter_norm",
        "text": "frame_type",
        "filter_text": "filter_norm",
        "camera_text": "camera",
        "telescope_text": "telescope",
    },
}
# a calibration match is about its light: the frame's paths, through `frame__`
_PATHS["match"] = {k: f"frame__{v}" for k, v in _PATHS["frame"].items()}
_PATHS["match"]["night"] = "frame__night__"
# a binned or deleted light keeps the dataset it was in as `binned_dataset` (spec 011): history outlives the files
_PATHS["binned_frame"] = {
    k: v.replace("dataset__", "binned_dataset__").replace("dataset_id", "binned_dataset_id")
    for k, v in _PATHS["frame"].items()
}
# the names free text is matched against, where a kind has them
_TEXTS = ("target", "text", "collection_name", "rig_name", "filter_text", "camera_text", "telescope_text")


def _prefixed(q: Q, prefix: str) -> Q:
    """The same condition, on a related record (night_filter speaks of a Night's own fields)."""
    out = Q()
    out.connector, out.negated = q.connector, q.negated
    for c in q.children:
        if isinstance(c, Q):
            out.children.append(_prefixed(c, prefix))
        else:
            field, value = c  # type: ignore[misc]
            out.children.append((prefix + field, value))
    return out


def apply(qs: QuerySet, scope: Scope | None, kind: str) -> QuerySet:
    """Narrow `qs` (records of `kind`: frame, binned_frame, dataset, night, match, set, master) to the scope. Inputs
    that don't apply to the kind are ignored. Joins through many-valued relations are made distinct."""
    if scope is None or scope.is_empty():
        return qs
    p = _PATHS[kind]
    cond = nights_q(scope, p["night"], p["site"])
    if scope.lat is not None and scope.lon is not None and "lat" in p:
        cond &= _near(scope.lat, scope.lon, scope.within_km, p)
    for key in ("rig", "collection", "project", "dataset"):
        if getattr(scope, key) is not None and key in p:
            cond &= Q(**{p[key]: getattr(scope, key)})
    if scope.rig is not None and "rig_camera" in p:
        cond &= _rig_camera(scope.rig, p["rig_camera"])
    for key in ("camera", "telescope", "filter", "target"):
        if getattr(scope, key) and key in p:
            cond &= Q(**{f"{p[key]}__iexact": getattr(scope, key).strip()})
    if scope.q and scope.q.strip():
        cond &= text_q(scope.q, kind)
    qs = qs.filter(cond)
    many = kind in ("dataset", "night")
    return qs.distinct() if many else qs


def nights_q(scope: Scope, night: str, site: str) -> Q:
    """The scope's place and nights, for records whose night is at `night` ("night__") and place at `site`."""
    cond = Q()
    if scope.site:
        cond &= Q(**{site: scope.site})
    return cond & _dates(scope, night)


def _dates(scope: Scope, night: str) -> Q:
    """The night (one date, or a from/to range, either end optional), reached through `night`."""
    cond = Q()
    if scope.date:
        cond &= Q(**{f"{night}date": scope.date})
    if scope.date_from:
        cond &= Q(**{f"{night}date__gte": scope.date_from})
    if scope.date_to:
        cond &= Q(**{f"{night}date__lte": scope.date_to})
    return cond


def _near(lat: float, lon: float, within_km: float | None, p: dict[str, str]) -> Q:
    """A box round the point, `within_km` (default 5 km) each way: a degree of latitude is about 111 km, and a
    degree of longitude shrinks with the cosine of the latitude (floored so the poles stay finite)."""
    km = within_km or 5.0
    dlat = km / 111.0
    dlon = km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
    return Q(**{f"{p['lat']}__range": (lat - dlat, lat + dlat)}) & Q(
        **{f"{p['lon']}__range": (lon - dlon, lon + dlon)}
    )


def _rig_camera(rig: int, path: str) -> Q:
    """Calibration for a rig: frames from its camera (calibration frames carry no rig of their own)."""
    from apps.catalogue.models import Rig

    camera = Rig.objects.filter(pk=rig).values_list("camera", flat=True).first()
    if not camera:
        return Q(pk__in=[])  # no such rig, or one with no camera: nothing is its calibration
    return Q(**{f"{path}__iexact": camera})


def rig_id(value: int | str | None) -> int | None:
    """A rig named the older way (by its name, as Library stats took it before spec 018) as its id; -1 when none
    has that name, so the scope matches nothing rather than everything."""
    from apps.catalogue.models import Rig

    if value is None or value == "":
        return None
    if isinstance(value, int) or str(value).isdigit():
        return int(value)
    return Rig.objects.filter(name__iexact=str(value).strip()).values_list("pk", flat=True).first() or -1


def without(scope: Scope, *keys: str) -> Scope:
    """The same scope with some inputs left out, for an endpoint that reads those itself."""
    return Scope(**{k: v for k, v in scope.dict().items() if k not in keys})


def text_q(q: str, kind: str) -> Q:
    """Free text: a date as people type it, else a name (target, dataset, collection, rig, filter, camera…)."""
    from apps.catalogue.api_search import night_filter

    p = _PATHS[kind]
    when = night_filter(q)
    if when is not None:
        return _prefixed(when, p["night"])
    t = q.strip()
    out = Q()
    for key in _TEXTS:
        if key in p:
            out |= Q(**{f"{p[key]}__icontains": t})
    return out
