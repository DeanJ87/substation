"""Deleting a collection's record, safely and undoably (amendment 2026-10-22). Deleting never touches the owner's
files: the datasets stay, just not in a collection or project. Refused while its files are moving or while it has
combined masters not yet deleted; recorded as a Change so undoing brings back the collection and its projects with
the same ids."""

from __future__ import annotations

from typing import Any

from django.utils.dateparse import parse_datetime

from apps.catalogue.models import (
    ACTIVE_MOVE_STATES,
    Change,
    Collection,
    CollectionMove,
    Dataset,
    MoveState,
    Project,
)
from apps.catalogue.services import projects as psvc
from apps.catalogue.services.changes import CantUndo, record

Refused = psvc.Refused
FIELDS = ("name", "objects_text", "constellation")


def _live_combined(col: Collection) -> list[str]:
    return [
        f"{c.filter_norm} v{c.version}"
        for c in col.combined.exclude(state="deleted").order_by("filter_norm", "version")
    ]


def _active_move(col: Collection) -> CollectionMove | None:
    return CollectionMove.objects.filter(collection=col, state__in=ACTIVE_MOVE_STATES).order_by("-pk").first()


def _move_state(m: CollectionMove | None) -> str | None:
    if m is None:
        return None
    return "running" if m.state == MoveState.RUNNING else "waiting"


def _unoffered(project_ids: list[int]) -> list[str]:
    """Astro finished images whose every link is to these projects: deleting them leaves the image unlinked, and the
    renderer no longer offers it."""
    from apps.finished.models import FinishedProject

    linked = FinishedProject.objects.filter(linked_projects__in=project_ids, kind="astro").distinct()
    return sorted(fp.name for fp in linked if not fp.linked_projects.exclude(pk__in=project_ids).exists())


def impact(col: Collection) -> dict[str, Any]:
    """What deleting this collection's record would touch, and what stops it."""
    from apps.catalogue.services.archive import where

    projects = list(col.projects.all())
    links = psvc._links(None, [p.pk for p in projects])
    move = _active_move(col)
    combined = _live_combined(col)
    blockers = []
    if move is not None:
        blockers.append("Its files are moving. Cancel the move first.")
    if combined:
        blockers.append(f"It has stitched or stacked masters ({', '.join(combined)}). Delete them first.")
    w = where(col)
    return {
        "datasets": col.datasets.count(),
        "projects": [
            {
                "id": p.pk,
                "label": p.name,
                "done": p.done_at is not None,
                "goals_set": bool(p.goals),
            }
            for p in projects
        ],
        "combined": combined,
        "finished": psvc.finished_names(None, {fp for ids in links.values() for fp in ids}),
        "unoffered": _unoffered([p.pk for p in projects]),
        "move": _move_state(move),
        "location": w.location,
        "libraries": [
            {"name": x["name"], "role": x["role"], "files": x["files"], "bytes": x["bytes"]}
            for x in w.libraries
        ],
        "blockers": blockers,
    }


def _snap(col: Collection) -> dict[str, Any]:
    out: dict[str, Any] = {f: getattr(col, f) for f in FIELDS}
    out["pk"] = col.pk
    out["created_at"] = col.created_at.isoformat() if col.created_at else None
    out["archive_dismissed_at"] = col.archive_dismissed_at.isoformat() if col.archive_dismissed_at else None
    return out


def remove(col: Collection, user: Any) -> tuple[Change, list[str]]:
    """Delete the collection's record and its projects'; the datasets stay, out of any collection. Call inside a
    transaction. Returns (change, warnings)."""
    move = _active_move(col)
    if move is not None:
        raise Refused("Its files are moving. Cancel the move first.")
    combined = _live_combined(col)
    if combined:
        raise Refused(f"It has stitched or stacked masters ({', '.join(combined)}). Delete them first.")
    projects = list(col.projects.all())
    pids = [p.pk for p in projects]
    links = psvc._links(None, pids)
    unoffered = _unoffered(pids)
    warnings = [f"{name}: no longer offered to the renderer." for name in unoffered]
    snaps = []
    for p in projects:
        rows = list(Dataset.objects.filter(project=p).values_list("pk", "project_position"))
        snaps.append({**psvc._snap(p), "datasets": [list(r) for r in rows], "finished": links.get(p.pk, [])})
    dataset_ids = list(Dataset.objects.filter(collection=col).values_list("pk", flat=True))
    snap = _snap(col)
    Dataset.objects.filter(pk__in=dataset_ids).update(collection=None, project=None, project_position=None)
    col.delete()
    change = record(
        user,
        Change.Kind.COLLECTION,
        f"Deleted collection {snap['name']}",
        len(dataset_ids),
        op="delete",
        collection=snap,
        projects=snaps,
        datasets=dataset_ids,
        warnings=warnings,
    )
    return change, warnings


def undo(data: dict) -> str:
    """Bring the collection and its projects back with the same ids; datasets come back only where they are still
    in no collection, finished links only to finished images still there."""
    from apps.catalogue.services.library import refresh_objects
    from apps.finished.models import FinishedProject

    snap = data["collection"]
    if Collection.objects.filter(pk=snap["pk"]).exists():
        raise CantUndo("That collection is back already.")
    col = Collection(pk=snap["pk"])
    for f in FIELDS:
        setattr(col, f, snap.get(f, getattr(col, f)))
    col.archive_dismissed_at = (
        parse_datetime(snap["archive_dismissed_at"]) if snap.get("archive_dismissed_at") else None
    )
    col.save(force_insert=True)
    if snap.get("created_at"):
        Collection.objects.filter(pk=col.pk).update(created_at=parse_datetime(snap["created_at"]))
    free = set(
        Dataset.objects.filter(pk__in=data.get("datasets", []), collection__isnull=True).values_list(
            "pk", flat=True
        )
    )
    Dataset.objects.filter(pk__in=free).update(collection=col)
    through = FinishedProject.linked_projects.through
    alive = set(
        FinishedProject.objects.filter(
            pk__in={fp for p in data.get("projects", []) for fp in p.get("finished", [])}
        ).values_list("pk", flat=True)
    )
    for ps in data.get("projects", []):
        p = Project(pk=ps["pk"], collection=col)
        psvc._restore_fields(p, ps)
        p.save(force_insert=True)
        for ds, pos in ps.get("datasets", []):
            if ds in free:
                Dataset.objects.filter(pk=ds, collection=col, project__isnull=True).update(
                    project=p, project_position=pos
                )
        for fp in ps.get("finished", []):
            if fp in alive:
                through.objects.get_or_create(finishedproject_id=fp, project_id=p.pk)
    if free != set(data.get("datasets", [])):  # some went elsewhere meanwhile: its objects follow what's back
        refresh_objects(col)
    return f"Restored collection {col.name}"
