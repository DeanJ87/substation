"""Search from the header (007-DR-26): collections, datasets, nights and files by what you'd type. On the catalogue
router. No `from __future__ import annotations` here: see substation.api."""

import re
from datetime import date, timedelta

from django.db.models import Q

from apps.catalogue.api import router
from apps.catalogue.models import Collection, Copy, Dataset, FrameStatus, Night
from substation.api import Schema

_DESIGNATION = re.compile(r"^([a-z]+)\s*(\d+)$", re.I)  # "ngc7635" and "ngc 7635" find the same thing
_DATE = re.compile(r"^\d{4}(-\d{1,2}(-\d{1,2})?)?$")
_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for m in names
}


def night_filter(q: str, today: date | None = None) -> Q | None:
    """Nights as people type them (2026-10-15): "2026-10", "october", "oct 2026", "14 october", "oct 14th",
    "14/10", "14/10/2026", "yesterday", "last night", "tonight". None when the text isn't a date."""
    today = today or date.today()
    t = q.strip().lower().replace(",", " ")
    if _DATE.match(t):
        prefix = "-".join(p.zfill(2) if i else p for i, p in enumerate(t.split("-")))
        return Q(date__startswith=prefix)
    if t in ("today", "tonight"):
        return Q(date=today)
    if t in ("yesterday", "last night"):
        return Q(date=today - timedelta(days=1))
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?", t)
    if m:  # day first, as written in the UK
        return _slashed_night(m)
    return _worded_night(t)


def _slashed_night(m: re.Match[str]) -> Q | None:
    """ "14/10" or "14.10.26" (day first): that day of that month, in that year when one is given (two digits
    mean this century). None when the day or month is out of range."""
    dd, mm, yy = int(m.group(1)), int(m.group(2)), m.group(3)
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None
    out = Q(date__month=mm, date__day=dd)
    return out & Q(date__year=int(yy) + (2000 if len(yy) == 2 else 0)) if yy else out


def _worded_night(t: str) -> Q | None:
    """A month name with an optional day ("14th", "14") and year ("2026"), in any order. None when any other
    word appears or no month is named."""
    month: int | None = None
    day: int | None = None
    year: int | None = None
    for w in (w for w in re.split(r"\s+", t) if w):
        w2 = re.sub(r"(st|nd|rd|th)$", "", w)
        if w in _MONTHS and month is None:
            month = _MONTHS[w]
        elif w2.isdigit() and len(w2) == 4 and year is None:
            year = int(w2)
        elif w2.isdigit() and 1 <= int(w2) <= 31 and day is None:
            day = int(w2)
        else:
            return None  # another word: not a date
    if month is None:
        return None
    out = Q(date__month=month)
    if day:
        out &= Q(date__day=day)
    if year:
        out &= Q(date__year=year)
    return out


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
    """The token, a designation with and without its space, and a filter's canonical name ("Ha" finds "Hα")."""
    from apps.ingest.fields import normalise_filter

    m = _DESIGNATION.match(token)
    forms = [token, f"{m[1]} {m[2]}", f"{m[1]}{m[2]}"] if m else [token]
    canon = normalise_filter(token, {}) if len(token) >= 2 else None
    if canon and canon != token:
        forms.append(canon)
    return forms


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
    when = night_filter(q)
    if when is not None:
        seen: dict[date, int] = {}
        for n in Night.objects.filter(when).order_by("-date"):
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
