"""Projects inside a collection (006-DR-20, -24): the object is the collection (NGC 7000); a project is one way of
shooting it ("6-panel mosaic 2026", "Single panel 2025"), with its datasets in order. On the catalogue router. No
`from __future__ import annotations` here: see substation.api."""

from datetime import date

from django.db import transaction
from django.db.models import Max, Min
from django.shortcuts import get_object_or_404

from substation.api import ApiError, Schema, Status

from .api import router
from .api_library import FilterTime
from .models import Collection, Dataset, DatasetNight, Project


class ProjectOut(Schema):
    id: int
    name: str
    kind: str
    planned_panels: int | None
    position: int
    dataset_ids: list[int]
    panels: list[int]  # panels shot so far
    missing_panels: list[int]  # planned but not shot yet
    first_night: date | None
    last_night: date | None
    accepted_integration_s: float
    goals: dict[str, float] = {}  # spec 019: hours of usable integration wanted, per filter
    filter_time: dict[str, FilterTime] = {}
    rigs: list[str] = []


class ProjectsOut(Schema):
    projects: list[ProjectOut]
    unassigned: list[int]


class ProjectIn(Schema):
    name: str
    kind: str = "single"
    planned_panels: int | None = None
    dataset_ids: list[int] = []


class ProjectPatch(Schema):
    name: str | None = None
    kind: str | None = None
    planned_panels: int | None = None
    goals: dict[str, float | None] | None = None  # spec 019: hours per filter; 0 or null removes one


class IdsIn(Schema):
    ids: list[int]


def _out(p: Project) -> ProjectOut:
    ds = list(p.datasets.select_related("rig").order_by("project_position", "panel", "filter_norm", "pk"))
    split: dict[str, list[float]] = {}
    for d in ds:
        t = split.setdefault(d.filter_norm or "?", [0.0, 0.0, 0.0])
        t[0] += d.integration_s or 0
        t[1] += d.accepted_integration_s or 0
        t[2] += d.rejected_integration_s or 0
    span = DatasetNight.objects.filter(dataset__in=ds).aggregate(
        first=Min("night__date"), last=Max("night__date")
    )
    panels = sorted({d.panel for d in ds if d.panel})
    missing = (
        [n for n in range(1, (p.planned_panels or 0) + 1) if n not in panels]
        if p.kind == Project.Kind.MOSAIC
        else []
    )
    return ProjectOut(
        id=p.pk,
        name=p.name,
        kind=p.kind,
        planned_panels=p.planned_panels,
        position=p.position,
        dataset_ids=[d.pk for d in ds],
        panels=panels,
        missing_panels=missing,
        first_night=span["first"],
        last_night=span["last"],
        accepted_integration_s=sum(d.accepted_integration_s or 0 for d in ds),
        goals=p.goals or {},
        filter_time={
            k: FilterTime(total_s=max(t, a + r), accepted_s=a, rejected_s=r) for k, (t, a, r) in split.items()
        },
        rigs=sorted({d.rig.name for d in ds if d.rig}),
    )


def _check(kind: str | None, planned: int | None) -> None:
    if kind is not None and kind not in Project.Kind.values:
        raise ApiError(422, "invalid", "A project is a single field or a mosaic.")
    if planned is not None and not 1 <= planned <= 100:
        raise ApiError(422, "invalid", "Planned panels must be between 1 and 100.")


@router.get("/collections/{id}/projects", response=ProjectsOut)
def list_projects(request, id: int):  # noqa: A002
    col = get_object_or_404(Collection, pk=id)
    return ProjectsOut(
        projects=[_out(p) for p in col.projects.all()],
        unassigned=list(col.datasets.filter(project=None).values_list("pk", flat=True)),
    )


def _assign(p: Project, ids: list[int]) -> None:
    """Exactly these datasets, in this order (moved in from other projects of the same collection)."""
    found = Dataset.objects.filter(pk__in=ids, collection=p.collection).values_list("pk", flat=True)
    if set(found) != set(ids):
        raise ApiError(422, "invalid", "Only this collection's datasets can be in its projects.")
    Dataset.objects.filter(project=p).exclude(pk__in=ids).update(project=None, project_position=None)
    for i, pk in enumerate(ids):
        Dataset.objects.filter(pk=pk).update(project=p, project_position=i)


@router.post("/collections/{id}/projects", response={201: ProjectOut})
def create_project(request, id: int, body: ProjectIn):  # noqa: A002
    col = get_object_or_404(Collection, pk=id)
    _check(body.kind, body.planned_panels)
    if not body.name.strip():
        raise ApiError(422, "invalid", "Give the project a name.")
    with transaction.atomic():
        p = Project.objects.create(
            collection=col,
            name=body.name.strip(),
            kind=body.kind,
            planned_panels=body.planned_panels,
            position=col.projects.count(),
        )
        _assign(p, body.dataset_ids)
    return Status(201, _out(p))


@router.patch("/projects/{id}", response=ProjectOut)
def update_project(request, id: int, body: ProjectPatch):  # noqa: A002
    p = get_object_or_404(Project, pk=id)
    _check(body.kind, body.planned_panels)
    change = body.dict(exclude_unset=True)
    if change.get("goals") is not None:
        from .api_library import clean_goals

        p.goals = clean_goals(p.goals, change.pop("goals"))
    change.pop("goals", None)
    for k, v in change.items():
        setattr(p, k, v.strip() if isinstance(v, str) else v)
    p.save()
    return _out(p)


@router.delete("/projects/{id}", response={204: None})
def delete_project(request, id: int):  # noqa: A002
    """The datasets stay in the collection, just not in a project."""
    p = get_object_or_404(Project, pk=id)
    Dataset.objects.filter(project=p).update(project=None, project_position=None)
    p.delete()
    return Status(204, None)


@router.put("/projects/{id}/datasets", response=ProjectOut)
def set_project_datasets(request, id: int, body: IdsIn):  # noqa: A002
    p = get_object_or_404(Project, pk=id)
    with transaction.atomic():
        _assign(p, body.ids)
    return _out(p)


@router.put("/collections/{id}/projects/order", response=list[ProjectOut])
def order_projects(request, id: int, body: IdsIn):  # noqa: A002
    col = get_object_or_404(Collection, pk=id)
    mine = set(col.projects.values_list("pk", flat=True))
    if set(body.ids) != mine:
        raise ApiError(422, "invalid", "List every project of this collection once.")
    for i, pk in enumerate(body.ids):
        Project.objects.filter(pk=pk).update(position=i)
    return [_out(p) for p in col.projects.all()]


def suggest_groups(col: Collection) -> list[dict]:
    """Projects for the datasets not in one yet: panels make a mosaic; the rest group by framing (fields that
    overlap by half or more), else by rig; each named with its kind and first year."""
    from apps.processing.solving import framing, overlap

    free = list(col.datasets.filter(project=None).select_related("rig"))
    first = {d.pk: DatasetNight.objects.filter(dataset=d).aggregate(f=Min("night__date"))["f"] for d in free}
    groups: list[dict] = []
    panels = [d for d in free if d.panel]
    if panels:
        n = max(d.panel or 0 for d in panels)
        year = min((first[d.pk] for d in panels if first[d.pk]), default=None)
        groups.append(
            {
                "name": f"{max(n, 2)}-panel mosaic" + (f" {year.year}" if year else ""),
                "kind": "mosaic",
                "planned_panels": max(n, 2),
                "datasets": panels,
            }
        )
    rest = [d for d in free if not d.panel]
    frames = {d.pk: framing(d) for d in rest}
    for d in rest:
        f = frames[d.pk]
        home = next(
            (
                g
                for g in groups[1 if panels else 0 :]
                if f
                and any((of := frames.get(o.pk)) is not None and overlap(f, of) >= 0.5 for o in g["datasets"])
            ),
            None,
        )
        if home is None and not f:
            home = next(
                (
                    g
                    for g in groups[1 if panels else 0 :]
                    if g.get("rig") == (d.rig.pk if d.rig else None)
                    and not any(frames.get(o.pk) for o in g["datasets"])
                ),
                None,
            )
        if home is None:
            year = first[d.pk]
            home = {
                "name": "Single field"
                + (f" {year.year}" if year else "")
                + (f" · {d.rig.name}" if d.rig else ""),
                "kind": "single",
                "planned_panels": None,
                "datasets": [],
                "rig": d.rig.pk if d.rig else None,
            }
            groups.append(home)
        home["datasets"].append(d)
    return groups


@router.post("/collections/{id}/projects/suggest", response=list[ProjectOut])
def suggest_projects(request, id: int):  # noqa: A002
    """Make projects for the datasets not in one yet (006-DR-20); rename or regroup them afterwards."""
    col = get_object_or_404(Collection, pk=id)
    made = []
    with transaction.atomic():
        start = col.projects.count()
        for i, g in enumerate(suggest_groups(col)):
            p = Project.objects.create(
                collection=col,
                name=g["name"],
                kind=g["kind"],
                planned_panels=g["planned_panels"],
                position=start + i,
            )
            ordered = sorted(g["datasets"], key=lambda d: (d.panel or 0, d.filter_norm or "", d.pk))
            _assign(p, [d.pk for d in ordered])
            made.append(p)
    return [_out(p) for p in made]
