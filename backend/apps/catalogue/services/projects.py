"""Projects by season (006-DR-20, amendment 2026-10-22): a project is one season of shooting a collection's object.
Seasons come from the nights: runs of nights with no gap of more than 120 days. Merging, splitting, removing and
moving datasets between projects are each recorded as a Change so they can be undone (spec 016).

The merge works on whichever model classes it's given, so the migration that joins old projects by season runs the
same code as the page (`apps` is a migration's app registry, or None for the live models)."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Any

from django.apps import apps as live_apps
from django.utils.dateparse import parse_datetime

log = logging.getLogger(__name__)

GAP_DAYS = 120
# names the old suggester gave; a project named like this is called by its season instead
SUGGESTED = (re.compile(r"^\d+-panel mosaic( \d{4})?$"), re.compile(r"^Single field( \d{4})?( · .+)?$"))
FIELDS = (
    "own_name",
    "season",
    "kind_override",
    "planned_panels",
    "position",
    "goals",
    "needs_review",
    "review_reason",
)

_APPS = {
    "Project": "catalogue",
    "Dataset": "catalogue",
    "DatasetNight": "catalogue",
    "Change": "catalogue",
    "CombinedMaster": "processing",
    "FinishedProject": "finished",
}


class Refused(Exception):
    """Said plainly, for the page; the API answers 409."""


def _m(apps: Any, name: str) -> Any:
    return (apps or live_apps).get_model(_APPS[name], name)


def is_suggested_name(name: str) -> bool:
    return any(p.match(name or "") for p in SUGGESTED)


def label(season: str, own_name: str) -> str:
    return " · ".join(x for x in (season, own_name) if x) or "Project"


def season_label(first: date, last: date) -> str:
    """ "2026", or "2025–26" for a run that goes over New Year."""
    if last.year == first.year:
        return str(first.year)
    return f"{first.year}–{last.year % 100:02d}"


def season_runs(dates: Iterable[date]) -> list[tuple[date, date]]:
    """Runs of nights with no gap of more than GAP_DAYS, first and last night each, in order."""
    runs: list[tuple[date, date]] = []
    for d in sorted(set(dates)):
        if runs and (d - runs[-1][1]).days <= GAP_DAYS:
            runs[-1] = (runs[-1][0], d)
        else:
            runs.append((d, d))
    return runs


class Seasons:
    """The seasons of one collection's nights, and which season a dataset (or a group of them) belongs to: the one
    holding most of its integration (most nights when nothing's integrated yet)."""

    def __init__(self, collection_id: int, apps: Any = None) -> None:
        dn = _m(apps, "DatasetNight")
        ds = _m(apps, "Dataset")
        self.weights: dict[int, dict[date, list[float]]] = defaultdict(
            lambda: defaultdict(lambda: [0.0, 0.0])
        )
        rows = dn.objects.filter(dataset__collection_id=collection_id).values_list(
            "dataset_id", "night__date", "integration_s"
        )
        for d, night, integ in rows:
            w = self.weights[d][night]
            w[0] += integ or 0
            w[1] += 1
        for d, first in ds.objects.filter(collection_id=collection_id, first_utc__isnull=False).values_list(
            "pk", "first_utc"
        ):
            if d not in self.weights:  # no per-night rows yet: its first sub stands in
                self.weights[d][first.date()] = [0.0, 1.0]
        self.runs = season_runs(n for w in self.weights.values() for n in w)

    def _run(self, night: date) -> int:
        return next(i for i, (a, b) in enumerate(self.runs) if a <= night <= b)

    def of(self, dataset_ids: Iterable[int]) -> str:
        """The season label for these datasets together; "" when none of them has a night."""
        tally: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for d in dataset_ids:
            for night, (integ, n) in self.weights.get(d, {}).items():
                t = tally[self._run(night)]
                t[0] += integ
                t[1] += n
        if not tally:
            return ""
        best = max(tally, key=lambda i: (tally[i][0], tally[i][1], -i))
        return season_label(*self.runs[best])


def same_season(a: str, b: str) -> bool:
    """A season keeps its start year as it grows over New Year ("2026" becomes "2026–27")."""
    return a[:4] == b[:4]


def effective_kind(p: Any, apps: Any = None) -> str:
    if p.kind_override:
        return str(p.kind_override)
    if (p.planned_panels or 0) > 1:
        return "mosaic"
    ds = _m(apps, "Dataset")
    panels = ds.objects.filter(project_id=p.pk).exclude(panel=None).values("panel").distinct().count()
    return "mosaic" if panels > 1 else "single"


def _snap(p: Any) -> dict:
    out = {f: getattr(p, f) for f in FIELDS}
    out["pk"] = p.pk
    out["collection_id"] = p.collection_id
    out["done_at"] = p.done_at.isoformat() if p.done_at else None
    return out


def _restore_fields(p: Any, snap: dict) -> None:
    for f in FIELDS:
        if f in snap:
            setattr(p, f, snap[f])
    if "done_at" in snap:
        p.done_at = parse_datetime(snap["done_at"]) if snap["done_at"] else None


def _links(apps: Any, project_ids: Iterable[int]) -> dict[int, list[int]]:
    """Finished image ids linked to each project."""
    through = _m(apps, "FinishedProject").linked_projects.through
    out: dict[int, list[int]] = defaultdict(list)
    for fp, p in through.objects.filter(project_id__in=list(project_ids)).values_list(
        "finishedproject_id", "project_id"
    ):
        out[p].append(fp)
    return out


def finished_names(apps: Any, ids: Iterable[int]) -> list[str]:
    return sorted(_m(apps, "FinishedProject").objects.filter(pk__in=set(ids)).values_list("name", flat=True))


def _record(apps: Any, user: Any, summary: str, count: int, **data: Any) -> Any:
    change = _m(apps, "Change")
    return change.objects.create(
        # a migration's historical user has no is_authenticated; an anonymous request user says False
        user=user if user is not None and getattr(user, "is_authenticated", True) else None,
        kind="project",
        summary=summary[:200],
        count=count,
        data=data,
    )


def goal_conflicts(goal_sets: Iterable[dict]) -> list[str]:
    """Filters whose goals differ between projects, said plainly."""
    seen: dict[str, set[float]] = defaultdict(set)
    for g in goal_sets:
        for f, h in (g or {}).items():
            seen[f].add(float(h))
    return [
        f"{f}: goals of {' and '.join(f'{h:g} h' for h in sorted(hs))}"
        for f, hs in sorted(seen.items())
        if len(hs) > 1
    ]


def merge(
    into_id: int, from_ids: list[int], user: Any, *, apps: Any = None, allow_linked: bool = False
) -> tuple:
    """Move every dataset of the `from_ids` projects into `into_id` and remove them: goals join (the larger per
    filter), planned panels the most, a mosaic stays a mosaic, the target keeps its name. Combined masters and
    finished-image links move to the target first (the combined masters' project link cascades). Refused when an
    absorbed project is linked to a finished image, unless `allow_linked`. Returns (change, warnings)."""
    project = _m(apps, "Project")
    dataset = _m(apps, "Dataset")
    combined = _m(apps, "CombinedMaster")
    through = _m(apps, "FinishedProject").linked_projects.through
    into = project.objects.select_for_update().get(pk=into_id)
    from_ids = [int(x) for x in dict.fromkeys(from_ids) if int(x) != into.pk]
    absorbed = list(project.objects.filter(pk__in=from_ids).order_by("position", "pk"))
    if not absorbed or len(absorbed) != len(from_ids):
        raise Refused("Pick the projects to merge.")
    if any(a.collection_id != into.collection_id for a in absorbed):
        raise Refused("Only projects of the same collection can be merged.")
    links = _links(apps, [into.pk, *from_ids])
    linked = [fp for a in absorbed for fp in links.get(a.pk, [])]
    if linked and not allow_linked:
        names = ", ".join(finished_names(apps, linked))
        raise Refused(f"Linked to a finished image ({names}): merging would change what it was made from.")
    warnings = goal_conflicts([into.goals, *(a.goals for a in absorbed)])
    snapshot: dict[str, Any] = {
        "op": "merge",
        "into": _snap(into),
        "into_links": links.get(into.pk, []),
        "into_datasets": list(
            dataset.objects.filter(project_id=into.pk).values_list("pk", "project_position").order_by("pk")
        ),
        "absorbed": [],
    }
    goals = dict(into.goals or {})
    for a in absorbed:
        for f, h in (a.goals or {}).items():
            goals[f] = max(float(h), float(goals.get(f, 0)))
    start = max(
        [
            -1,
            *(
                p
                for p in dataset.objects.filter(project_id=into.pk).values_list("project_position", flat=True)
                if p is not None
            ),
        ]
    )
    moved = 0
    for a in absorbed:
        rows = list(
            dataset.objects.filter(project_id=a.pk).order_by("project_position", "panel", "filter_norm", "pk")
        )
        snapshot["absorbed"].append(
            {
                **_snap(a),
                "datasets": [[d.pk, d.project_position] for d in rows],
                "finished": links.get(a.pk, []),
                "combined": list(combined.objects.filter(project_id=a.pk).values_list("pk", flat=True)),
            }
        )
        for d in rows:
            start += 1
            dataset.objects.filter(pk=d.pk).update(project_id=into.pk, project_position=start)
            moved += 1
    combined.objects.filter(project_id__in=from_ids).update(project_id=into.pk)
    for fp in set(linked):
        through.objects.get_or_create(finishedproject_id=fp, project_id=into.pk)
    through.objects.filter(project_id__in=from_ids).delete()
    group = [into, *absorbed]
    into.goals = goals
    planned = [p.planned_panels for p in group if p.planned_panels]
    into.planned_panels = max(planned) if planned else None
    into.kind_override = "mosaic" if any(p.kind_override == "mosaic" for p in group) else None
    into.season = into.season or next((a.season for a in absorbed if a.season), "")
    into.needs_review, into.review_reason = False, ""
    into.save()
    project.objects.filter(pk__in=from_ids).delete()
    n = len(absorbed)
    change = _record(
        apps,
        user,
        f"Merged {n} project{'s' if n != 1 else ''} into {label(into.season, into.own_name)}",
        moved,
        **snapshot,
        warnings=warnings,
    )
    return change, warnings


def undo_merge(data: dict) -> str:
    from apps.catalogue.services.changes import CantUndo

    project = _m(None, "Project")
    dataset = _m(None, "Dataset")
    combined = _m(None, "CombinedMaster")
    through = _m(None, "FinishedProject").linked_projects.through
    into = project.objects.filter(pk=data["into"]["pk"]).first()
    if into is None:
        raise CantUndo("The project they were merged into has been removed since.")
    if project.objects.filter(pk__in=[a["pk"] for a in data["absorbed"]]).exists():
        raise CantUndo("Those projects are back already.")
    for a in data["absorbed"]:
        p = project(pk=a["pk"], collection_id=a["collection_id"])
        _restore_fields(p, a)
        p.save(force_insert=True)
        for ds, pos in a["datasets"]:
            dataset.objects.filter(pk=ds, project_id=into.pk).update(project_id=p.pk, project_position=pos)
        combined.objects.filter(pk__in=a["combined"], project_id=into.pk).update(project_id=p.pk)
        for fp in a["finished"]:
            through.objects.get_or_create(finishedproject_id=fp, project_id=p.pk)
    gained = {fp for a in data["absorbed"] for fp in a["finished"]} - set(data["into_links"])
    through.objects.filter(project_id=into.pk, finishedproject_id__in=gained).delete()
    for ds, pos in data.get("into_datasets", []):
        dataset.objects.filter(pk=ds, project_id=into.pk).update(project_position=pos)
    _restore_fields(into, data["into"])
    into.save()
    n = len(data["absorbed"])
    return f"Split {n} project{'s' if n != 1 else ''} out again"


def _split_groups(rows: list, by: str, dataset_ids: list[int] | None, name: str) -> list[tuple[str, list]]:
    """The groups to move out, each with its new project's name."""
    if by == "datasets":
        want = set(dataset_ids or [])
        chosen = [d for d in rows if d.pk in want]
        if not chosen or len(chosen) != len(want):
            raise Refused("Pick datasets of this project to split off.")
        if len(chosen) == len(rows):
            raise Refused("Leave at least one dataset in the project.")
        return [(name.strip(), chosen)]
    if by not in ("rig", "panel"):
        raise Refused("Split by rig, by panel or by the chosen datasets.")
    keyed: dict[Any, list] = defaultdict(list)
    for d in rows:
        keyed[d.rig_id if by == "rig" else d.panel].append(d)
    if len(keyed) < 2:
        raise Refused(f"All its datasets are on one {by}.")
    keep = max(keyed, key=lambda k: sum(d.accepted_integration_s or 0 for d in keyed[k]))
    groups = []
    for k, ds in keyed.items():
        if k == keep:
            continue
        if by == "rig":
            groups.append((ds[0].rig.name if ds[0].rig else "No rig", ds))
        else:
            groups.append((f"Panel {k}" if k else "No panel", ds))
    return groups


def split(p: Any, by: str, dataset_ids: list[int] | None, name: str, user: Any) -> tuple:
    """New projects in the same collection and season for part of `p`'s datasets: by rig or by panel (the group
    with the most integration stays), or the chosen datasets. Goals and finished links stay on `p`.
    Returns (change, new projects, warnings)."""
    project = _m(None, "Project")
    dataset = _m(None, "Dataset")
    rows = list(dataset.objects.filter(project=p).select_related("rig").order_by("project_position", "pk"))
    groups = _split_groups(rows, by, dataset_ids, name)
    warnings = []
    if p.goals:
        warnings.append(f"Goals stay on {p.name}.")
    linked = _links(None, [p.pk]).get(p.pk, [])
    if linked:
        warnings.append(f"{', '.join(finished_names(None, linked))} stays linked to {p.name}.")
    start = p.collection.projects.count()
    made, moved = [], {}
    for i, (title, ds) in enumerate(groups):
        q = project.objects.create(
            collection=p.collection, season=p.season, own_name=title, position=start + i
        )
        for j, d in enumerate(ds):
            moved[str(d.pk)] = d.project_position
            dataset.objects.filter(pk=d.pk).update(project=q, project_position=j)
        made.append(q)
    what = {"rig": "by rig", "panel": "by panel", "datasets": ""}[by]
    change = _record(
        None,
        user,
        f"Split {p.name} {what}".strip(),
        len(moved),
        op="split",
        project=p.pk,
        new=[q.pk for q in made],
        moved=moved,
    )
    return change, made, warnings


def undo_split(data: dict) -> str:
    from apps.catalogue.services.changes import CantUndo

    project = _m(None, "Project")
    dataset = _m(None, "Dataset")
    p = project.objects.filter(pk=data["project"]).first()
    if p is None:
        raise CantUndo("The project they were split from has been removed since.")
    back = 0
    for ds, pos in data["moved"].items():
        back += dataset.objects.filter(pk=int(ds), project_id__in=data["new"]).update(
            project_id=p.pk, project_position=pos
        )
    _drop_if_empty(data["new"])
    return f"Put {back} dataset{'s' if back != 1 else ''} back in {p.name}"


def _drop_if_empty(ids: Iterable[int]) -> None:
    """Remove projects that hold nothing now and nothing points at (no datasets, combined masters or links)."""
    project = _m(None, "Project")
    for q in project.objects.filter(pk__in=list(ids)):
        if not q.datasets.exists() and not q.combined.exists() and not q.finished.exists():
            q.delete()


def impact(p: Any, into: Any = None) -> dict:
    """What a merge, split or removal of `p` would touch: finished images, combined masters, goal conflicts."""
    links = _links(None, [p.pk]).get(p.pk, [])
    return {
        "finished": finished_names(None, links),
        "combined": [f"{c.filter_norm} v{c.version}" for c in p.combined.order_by("filter_norm", "version")],
        "goal_conflicts": goal_conflicts([into.goals, p.goals]) if into is not None else [],
        "datasets": p.datasets.count(),
    }


def remove(p: Any, user: Any) -> tuple:
    """Remove a project: refused while it has combined masters; its datasets stay in the collection, its finished
    links go. Returns (change, warnings)."""
    dataset = _m(None, "Dataset")
    combos = impact(p)["combined"]
    if combos:
        raise Refused(f"It has combined masters ({', '.join(combos)}). Remove those first, or merge it.")
    linked = _links(None, [p.pk]).get(p.pk, [])
    warnings = [f"No longer linked to {', '.join(finished_names(None, linked))}."] if linked else []
    rows = list(dataset.objects.filter(project=p).values_list("pk", "project_position"))
    snap = {**_snap(p), "datasets": rows, "finished": linked}
    name = p.name
    dataset.objects.filter(project=p).update(project=None, project_position=None)
    p.delete()
    change = _record(None, user, f"Removed project {name}", len(rows), op="delete", project=snap)
    return change, warnings


def undo_remove(data: dict) -> str:
    from apps.catalogue.services.changes import CantUndo

    project = _m(None, "Project")
    dataset = _m(None, "Dataset")
    collection = live_apps.get_model("catalogue", "Collection")
    through = _m(None, "FinishedProject").linked_projects.through
    snap = data["project"]
    if project.objects.filter(pk=snap["pk"]).exists():
        raise CantUndo("That project is back already.")
    if not collection.objects.filter(pk=snap["collection_id"]).exists():
        raise CantUndo("Its collection has been removed since.")
    p = project(pk=snap["pk"], collection_id=snap["collection_id"])
    _restore_fields(p, snap)
    p.save(force_insert=True)
    for ds, pos in snap["datasets"]:
        dataset.objects.filter(pk=ds, project=None, collection_id=p.collection_id).update(
            project=p, project_position=pos
        )
    existing = (
        _m(None, "FinishedProject").objects.filter(pk__in=snap["finished"]).values_list("pk", flat=True)
    )
    for fp in existing:
        through.objects.get_or_create(finishedproject_id=fp, project_id=p.pk)
    return f"Brought back {p.name}"


def placements(ids: Iterable[int]) -> dict[str, list]:
    dataset = _m(None, "Dataset")
    return {
        str(pk): [proj, pos]
        for pk, proj, pos in dataset.objects.filter(pk__in=list(ids)).values_list(
            "pk", "project_id", "project_position"
        )
    }


def record_moves(user: Any, summary: str, op: str, before: dict[str, list], **more: Any) -> Any:
    """A change that moved datasets between projects: undoing puts back each one still where this left it."""
    after = placements(int(k) for k in before)
    moved = {k: v for k, v in before.items() if after.get(k) != v}
    return _record(None, user, summary, len(moved), op=op, before=moved, after=after, **more)


def undo_moves(data: dict) -> str:
    project = _m(None, "Project")
    dataset = _m(None, "Dataset")
    alive = set(project.objects.values_list("pk", flat=True))
    back = 0
    for ds, (proj, pos) in data.get("before", {}).items():
        now = data.get("after", {}).get(ds, [None, None])
        if proj is not None and proj not in alive:
            proj, pos = None, None
        back += dataset.objects.filter(pk=int(ds), project_id=now[0], project_position=now[1]).update(
            project_id=proj, project_position=pos
        )
    note = f"Put {back} dataset{'s' if back != 1 else ''} back"
    if data.get("op") in ("create", "sort"):
        _drop_if_empty(data.get("created", []))
    return note


def undo_edit(data: dict) -> str:
    from apps.catalogue.services.changes import CantUndo

    project = _m(None, "Project")
    p = project.objects.filter(pk=data["project"]).first()
    if p is None:
        raise CantUndo("That project has been removed since.")
    _restore_fields(p, data["before"])
    p.save()
    return f"Put back {p.name} as it was"


def undo(data: dict) -> str:
    op = data.get("op")
    if op == "merge":
        return undo_merge(data)
    if op == "split":
        return undo_split(data)
    if op == "delete":
        return undo_remove(data)
    if op == "edit":
        return undo_edit(data)
    return undo_moves(data)


def sort_into_seasons(col: Any, user: Any) -> tuple:
    """Each dataset not in a project joins the collection's project for its season (the first, if there are
    several), else one new project per season. Never split by rig, panel or framing.
    Returns (change, created, joined) with joined = {project id: [dataset ids]}."""
    project = _m(None, "Project")
    seasons = Seasons(col.pk)
    free = list(col.datasets.filter(project=None).order_by("panel", "filter_norm", "pk"))
    before = placements(d.pk for d in free)
    existing = list(col.projects.all())
    created: list = []
    joined: dict[int, list[int]] = defaultdict(list)
    for d in free:
        s = seasons.of([d.pk])
        home = next((p for p in existing if (same_season(p.season, s) if s else not p.season)), None)
        if home is None:
            home = project.objects.create(collection=col, season=s, position=col.projects.count())
            existing.append(home)
            created.append(home)
        last = max(
            [-1, *(x for x in home.datasets.values_list("project_position", flat=True) if x is not None)]
        )
        type(d).objects.filter(pk=d.pk).update(project=home, project_position=last + 1)
        if home not in created:
            joined[home.pk].append(d.pk)
    change = record_moves(
        user,
        f"Sorted {len(free)} dataset{'s' if len(free) != 1 else ''} into seasons",
        "sort",
        before,
        created=[p.pk for p in created],
    )
    return change, created, dict(joined)
