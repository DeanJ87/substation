"""The map (spec 012): places subs were shot, from each light's site, with a count and one picture per place. On the
catalogue router. No `from __future__ import annotations` here: see substation.api."""

import math
from collections import defaultdict
from datetime import date

from django.db.models import Count

from apps.catalogue.api import router
from apps.catalogue.models import Dataset, Frame, FrameStatus, FrameType
from substation.api import Schema

NEAR_DEG = 0.01  # lights within about a kilometre of a place are that place


class MapNight(Schema):
    date: date
    subs: int
    site_key: str | None = None  # opens that night's page at this place


class MapCollection(Schema):
    id: int | None  # None: a dataset not in a collection
    name: str
    subs: int


class MapPlace(Schema):
    key: str
    lat: float
    lon: float
    subs: int
    first: date | None
    last: date | None
    nights: list[MapNight]
    targets: list[str]  # the most-shot collections (or targets) there, most first
    collections: list[MapCollection] = []  # the same, with their ids, for links
    image: str | None  # the best master shot there, else a sub


class MapOut(Schema):
    places: list[MapPlace]


def _picture(dataset_ids: list[int]) -> str | None:
    from apps.catalogue.api_library import _master_image
    from apps.processing.models import Master

    m = (
        Master.objects.filter(dataset_id__in=dataset_ids, deleted_at=None)
        .exclude(preview_path="")
        .order_by("-integration_s")
        .first()
    )
    if m:
        return _master_image(m)
    sha = (
        Frame.objects.filter(dataset_id__in=dataset_ids[:1], frame_type=FrameType.LIGHT)
        .values_list("pk", flat=True)
        .first()
    )
    return f"/api/v1/frames/{sha}/glance" if sha else None


@router.get("/map", response=MapOut)
def map_places(request):
    rows = (
        Frame.objects.filter(frame_type=FrameType.LIGHT, site_lat__isnull=False, site_lon__isnull=False)
        .exclude(status__in=[FrameStatus.BINNED, FrameStatus.DELETED, FrameStatus.IGNORED])
        .exclude(site_lat=0, site_lon=0)
        .values("site_lat", "site_lon", "night__date", "night__site_key", "dataset_id")
        .annotate(n=Count("pk"))
    )
    places: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: -r["n"]):  # the busiest spot anchors its place
        lat, lon = float(r["site_lat"] or 0), float(r["site_lon"] or 0)
        wide = NEAR_DEG / max(math.cos(math.radians(lat)), 0.05)
        p = next(
            (q for q in places.values() if abs(q["at"][0] - lat) < NEAR_DEG and abs(q["at"][1] - lon) < wide),
            None,
        )
        if p is None:
            p = places[f"{lat:.3f},{lon:.3f}"] = {
                "at": (lat, lon),
                "lat": [],
                "lon": [],
                "subs": 0,
                "nights": defaultdict(int),
                "sites": defaultdict(lambda: defaultdict(int)),
                "datasets": defaultdict(int),
            }
        p["lat"].append((r["site_lat"], r["n"]))
        p["lon"].append((r["site_lon"], r["n"]))
        p["subs"] += r["n"]
        if r["night__date"]:
            p["nights"][r["night__date"]] += r["n"]
            p["sites"][r["night__date"]][r["night__site_key"]] += r["n"]
        if r["dataset_id"]:
            p["datasets"][r["dataset_id"]] += r["n"]
    owners = {
        d.pk: (d.collection_id, d.collection.name if d.collection else d.target)
        for d in Dataset.objects.filter(
            pk__in={i for p in places.values() for i in p["datasets"]}
        ).select_related("collection")
    }
    names = {k: v[1] for k, v in owners.items()}
    out = []
    for key, p in places.items():
        mean = lambda xs: sum(v * n for v, n in xs) / sum(n for _, n in xs)  # noqa: E731
        by_target: dict[str, int] = defaultdict(int)
        by_owner: dict[tuple, int] = defaultdict(int)
        for ds, n in p["datasets"].items():
            by_target[names.get(ds, "")] += n
            if ds in owners:
                by_owner[owners[ds]] += n
        nights = sorted(p["nights"].items())
        top = sorted(p["datasets"], key=lambda d: -p["datasets"][d])
        out.append(
            MapPlace(
                key=key,
                lat=round(mean(p["lat"]), 4),
                lon=round(mean(p["lon"]), 4),
                subs=p["subs"],
                first=nights[0][0] if nights else None,
                last=nights[-1][0] if nights else None,
                nights=[
                    MapNight(date=d, subs=n, site_key=max(p["sites"][d].items(), key=lambda kv: kv[1])[0])
                    for d, n in reversed(nights)
                ],
                collections=[
                    MapCollection(id=cid, name=name, subs=n)
                    for (cid, name), n in sorted(by_owner.items(), key=lambda kv: -kv[1])
                    if name
                ][:8],
                targets=[t for t, _ in sorted(by_target.items(), key=lambda kv: -kv[1]) if t][:5],
                image=_picture(top),
            )
        )
    out.sort(key=lambda p: -p.subs)
    return MapOut(places=out)
