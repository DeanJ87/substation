"""Search from the header (007-DR-26): collections, datasets, nights and files by what you'd type. On the catalogue
router. No `from __future__ import annotations` here: see substation.api."""

import re
from datetime import date

from django.db.models import Q

from apps.catalogue.api import router
from apps.catalogue.models import Collection, Copy, Dataset, FrameStatus, Night
from substation.api import Schema

_DESIGNATION = re.compile(r"^([a-z]+)\s*(\d+)$", re.I)  # "ngc7635" and "ngc 7635" find the same thing
_DATE = re.compile(r"^\d{4}(-\d{1,2}(-\d{1,2})?)?$")


class SearchCollection(Schema):
    id: int
    name: str
    objects: str
    datasets: int


class SearchDataset(Schema):
    id: int
    name: str
    subs: int
    collection: str | None


class SearchNight(Schema):
    date: date
    datasets: int


class SearchFile(Schema):
    sha256: str
    name: str
    folder: str
    target: str | None


class SearchOut(Schema):
    collections: list[SearchCollection]
    datasets: list[SearchDataset]
    nights: list[SearchNight]
    files: list[SearchFile]


def _forms(token: str) -> list[str]:
    m = _DESIGNATION.match(token)
    return [token, f"{m[1]} {m[2]}", f"{m[1]}{m[2]}"] if m else [token]


def _all_words(q: str, *fields: str) -> Q:
    """Every word must appear in one of the fields; a catalogue designation matches with or without its space."""
    out = Q()
    for token in q.split():
        any_field = Q()
        for form in _forms(token):
            for f in fields:
                any_field |= Q(**{f"{f}__icontains": form})
        out &= any_field
    return out


@router.get("/search", response=SearchOut)
def search(request, q: str, limit: int = 8):
    q = q.strip()
    limit = max(1, min(limit, 25))
    empty = SearchOut(collections=[], datasets=[], nights=[], files=[])
    if len(q) < 2:
        return empty
    collections = [
        SearchCollection(id=c.pk, name=c.name, objects=c.objects_text or "", datasets=c.datasets.count())
        for c in Collection.objects.filter(_all_words(q, "name", "objects_text")).order_by("name")[:limit]
    ]
    datasets = [
        SearchDataset(
            id=d.pk,
            name=d.display_name,
            subs=d.sub_count,
            collection=d.collection.name if d.collection else None,
        )
        for d in Dataset.objects.filter(_all_words(q, "display_name", "target", "collection__name"))
        .exclude(sub_count=0)
        .select_related("collection")
        .order_by("-sub_count")[:limit]
    ]
    nights: list[SearchNight] = []
    if _DATE.match(q):
        prefix = "-".join(p.zfill(2) if i else p for i, p in enumerate(q.split("-")))
        seen: dict[date, int] = {}
        for n in Night.objects.filter(date__startswith=prefix).order_by("-date"):
            seen[n.date] = seen.get(n.date, 0) + n.frames.values("dataset").distinct().count()
        nights = [SearchNight(date=d, datasets=c) for d, c in list(seen.items())[:limit]]
    files: list[SearchFile] = []
    if len(q) >= 3:
        for c in (
            Copy.objects.filter(present=True, rel_path__icontains=q)
            .exclude(frame__status__in=[FrameStatus.BINNED, FrameStatus.DELETED])
            .select_related("frame")
            .order_by("rel_path")[:limit]
        ):
            folder, _, name = c.rel_path.rpartition("/")
            files.append(SearchFile(sha256=c.frame_id, name=name, folder=folder, target=c.frame.target))
    return SearchOut(collections=collections, datasets=datasets, nights=nights, files=files)
