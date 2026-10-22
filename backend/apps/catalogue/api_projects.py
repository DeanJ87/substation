"""Projects inside a collection (006-DR-20, -24, amendment 2026-10-22): the object is the collection (IC 1805); a
project is one season of shooting it ("2026", "2025–26 · widefield"), with its datasets in order. Merging, splitting,
removing and moving datasets are each undoable (spec 016). On the catalogue router. No
`from __future__ import annotations` here: see substation.api."""

from datetime import date, datetime

from django.db import transaction
from django.db.models import Max, Min
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field

from substation.api import ApiError, Schema, Status

from .api import router
from .api_library import FilterTime
from .models import Collection, Dataset, DatasetNight, Project
from .services import projects as svc


class ProjectOut(Schema):
    id: int
    name: str  # the label, as before: "2026 · Askar"
    label: str
    own_name: str
    season: str
    kind: str  # in force: the owner's choice, else worked out
    kind_auto: str
    kind_override: str | None = None
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
    done: bool = False
    done_at: datetime | None = None
    needs_review: bool = False
    review_reason: str = ""
    change_id: int | None = None  # spec 016: undo it with POST /changes/{id}/undo
    warnings: list[str] = []


class ReviewOut(Schema):
    """Projects of one season held apart when seasons were joined: the owner merges them or keeps them apart."""

    season: str
    project_ids: list[int]
    into: int  # the one with the most integration
    reasons: list[str]
    mergeable: bool


class ProjectsOut(Schema):
    projects: list[ProjectOut]
    unassigned: list[int]
    review: list[ReviewOut] = []


class ProjectIn(Schema):
    name: str = ""
    season: str | None = None  # this year when not given
    kind: str | None = None  # single, mosaic, or automatic when not given
    planned_panels: int | None = None
    dataset_ids: list[int] = []


class ProjectPatch(Schema):
    name: str | None = None
    season: str | None = None
    kind: str | None = None  # single, mosaic or auto
    planned_panels: int | None = None
    goals: dict[str, float | None] | None = None  # spec 019: hours per filter; 0 or null removes one
    done: bool | None = None
    needs_review: bool | None = None


class IdsIn(Schema):
    ids: list[int]


class MergeIn(Schema):
    into: int
    from_: list[int] = Field(..., alias="from")


class SplitIn(Schema):
    by: str  # rig, panel or datasets
    dataset_ids: list[int] = []
    name: str = ""


class ChangedOut(Schema):
    change_id: int | None = None
    warnings: list[str] = []


class MergeOut(ChangedOut):
    project: ProjectOut


class SplitOut(ChangedOut):
    project: ProjectOut
    created: list[ProjectOut]


class SortOut(ChangedOut):
    created: list[ProjectOut]
    joined: list[ProjectOut]
    placed: int


class ImpactOut(Schema):
    finished: list[str]  # finished images linked to it
    combined: list[str]  # its combined masters
    goal_conflicts: list[str]  # with the project given as `into`
    datasets: int


def _out(p: Project, change=None, warnings: list[str] | None = None) -> ProjectOut:  # noqa: ANN001
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
    auto = "mosaic" if (p.planned_panels or 0) > 1 or len(panels) > 1 else "single"
    kind = p.kind_override or auto
    missing = (
        [n for n in range(1, (p.planned_panels or 0) + 1) if n not in panels]
        if kind == Project.Kind.MOSAIC
        else []
    )
    return ProjectOut(
        id=p.pk,
        name=p.name,
        label=p.name,
        own_name=p.own_name,
        season=p.season,
        kind=kind,
        kind_auto=auto,
        kind_override=p.kind_override,
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
        done=p.done_at is not None,
        done_at=p.done_at,
        needs_review=p.needs_review,
        review_reason=p.review_reason,
        change_id=change.pk if change is not None else None,
        warnings=warnings or [],
    )


def _check(kind: str | None, planned: int | None, season: str | None = None) -> None:
    if kind is not None and kind not in (*Project.Kind.values, "auto", ""):
        raise ApiError(422, "invalid", "A project is a single field, a mosaic, or worked out.")
    if planned is not None and not 1 <= planned <= 100:
        raise ApiError(422, "invalid", "Planned panels must be between 1 and 100.")
    if season is not None and len(season.strip()) > 20:
        raise ApiError(422, "invalid", 'A season is a year, or two across New Year: "2026", "2025–26".')


def _refused(e: svc.Refused) -> ApiError:
    return ApiError(409, "refused", str(e))


def _review(col: Collection, projects: list[Project]) -> list[ReviewOut]:
    held: dict[str, list[Project]] = {}
    for p in projects:
        if p.needs_review:
            held.setdefault(p.season[:4], []).append(p)
    out = []
    for group in held.values():
        if len(group) < 2:
            continue
        integ = {
            p.pk: sum(Dataset.objects.filter(project=p).values_list("accepted_integration_s", flat=True))
            for p in group
        }
        into = max(group, key=lambda p: (integ[p.pk], -p.position, -p.pk))
        links = svc._links(None, [p.pk for p in group if p.pk != into.pk])
        out.append(
            ReviewOut(
                season=into.season,
                project_ids=[p.pk for p in group],
                into=into.pk,
                reasons=sorted({p.review_reason for p in group if p.review_reason}),
                mergeable=not any(links.values()),
            )
        )
    return out


@router.get("/collections/{id}/projects", response=ProjectsOut)
def list_projects(request, id: int):  # noqa: A002
    col = get_object_or_404(Collection, pk=id)
    projects = list(col.projects.all())
    return ProjectsOut(
        projects=[_out(p) for p in projects],
        unassigned=list(col.datasets.filter(project=None).values_list("pk", flat=True)),
        review=_review(col, projects),
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
    """A new project for a season (this year unless said), with an optional name."""
    col = get_object_or_404(Collection, pk=id)
    _check(body.kind, body.planned_panels, body.season)
    season = (body.season if body.season is not None else str(timezone.localdate().year)).strip()
    with transaction.atomic():
        before = svc.placements(body.dataset_ids)
        p = Project.objects.create(
            collection=col,
            own_name=body.name.strip(),
            season=season,
            kind_override=body.kind if body.kind in Project.Kind.values else None,
            planned_panels=body.planned_panels,
            position=col.projects.count(),
        )
        _assign(p, body.dataset_ids)
        change = svc.record_moves(request.user, f"Added project {p.name}", "create", before, created=[p.pk])
    return Status(201, _out(p, change))


@router.patch("/projects/{id}", response=ProjectOut)
def update_project(request, id: int, body: ProjectPatch):  # noqa: A002
    """Rename, change its season, set its kind (or back to automatic), planned panels, goals; mark it done."""
    p = get_object_or_404(Project, pk=id)
    _check(body.kind, body.planned_panels, body.season)
    change = body.dict(exclude_unset=True)
    before = {**svc._snap(p)}
    if change.get("goals") is not None:
        from .api_library import clean_goals

        p.goals = clean_goals(p.goals, change["goals"])
    if "name" in change:
        p.own_name = (change["name"] or "").strip()
    if "season" in change:
        p.season = (change["season"] or "").strip()
    if "kind" in change:
        p.kind_override = change["kind"] if change["kind"] in Project.Kind.values else None
    if "planned_panels" in change:
        p.planned_panels = change["planned_panels"]
    if change.get("done") is not None:
        p.done_at = (p.done_at or timezone.now()) if change["done"] else None
    if change.get("needs_review") is not None:
        p.needs_review = change["needs_review"]
        if not p.needs_review:
            p.review_reason = ""
    with transaction.atomic():
        p.save()
        after = svc._snap(p)
        diff = {k: before[k] for k in (*svc.FIELDS, "done_at") if before[k] != after[k] and k != "position"}
        recorded = None
        if diff:
            done = "done_at" in diff and len(diff) == 1
            what = (
                (f"Marked {p.name} done" if p.done_at else f"Marked {p.name} not done")
                if done
                else f"Edited {p.name}"
            )
            recorded = svc._record(None, request.user, what, 1, op="edit", project=p.pk, before=diff)
    return _out(p, recorded)


@router.delete("/projects/{id}", response=ChangedOut)
def delete_project(request, id: int):  # noqa: A002
    """The datasets stay in the collection, just not in a project. Refused while it has combined masters; its
    finished-image links go (said in warnings)."""
    p = get_object_or_404(Project, pk=id)
    try:
        with transaction.atomic():
            change, warnings = svc.remove(p, request.user)
    except svc.Refused as e:
        raise _refused(e) from None
    return ChangedOut(change_id=change.pk, warnings=warnings)


@router.put("/projects/{id}/datasets", response=ProjectOut)
def set_project_datasets(request, id: int, body: IdsIn):  # noqa: A002
    p = get_object_or_404(Project, pk=id)
    with transaction.atomic():
        before = svc.placements([*body.ids, *p.datasets.values_list("pk", flat=True)])
        _assign(p, body.ids)
        change = svc.record_moves(request.user, f"Moved datasets in {p.name}", "assign", before)
    return _out(p, change)


@router.put("/collections/{id}/projects/order", response=list[ProjectOut])
def order_projects(request, id: int, body: IdsIn):  # noqa: A002
    col = get_object_or_404(Collection, pk=id)
    mine = set(col.projects.values_list("pk", flat=True))
    if set(body.ids) != mine:
        raise ApiError(422, "invalid", "List every project of this collection once.")
    for i, pk in enumerate(body.ids):
        Project.objects.filter(pk=pk).update(position=i)
    return [_out(p) for p in col.projects.all()]


@router.post("/collections/{id}/projects/suggest", response=SortOut)
def suggest_projects(request, id: int):  # noqa: A002
    """Sort the datasets not in a project into seasons: each joins its season's project, else a new project per
    season. Never split by rig, panel or framing; split a project afterwards if wanted."""
    col = get_object_or_404(Collection, pk=id)
    with transaction.atomic():
        change, created, joined = svc.sort_into_seasons(col, request.user)
    return SortOut(
        created=[_out(p) for p in created],
        joined=[_out(p) for p in Project.objects.filter(pk__in=list(joined))],
        placed=change.count,
        change_id=change.pk,
    )


@router.post("/collections/{id}/projects/merge", response=MergeOut)
def merge_projects(request, id: int, body: MergeIn):  # noqa: A002
    """Merge projects into one (`into` keeps its name): datasets, goals (the larger per filter), combined masters.
    Refused when a project to be absorbed is linked to a finished image."""
    col = get_object_or_404(Collection, pk=id)
    ids = [body.into, *body.from_]
    if Project.objects.filter(pk__in=ids, collection=col).count() != len(set(ids)):
        raise ApiError(422, "invalid", "Only this collection's projects can be merged.")
    try:
        with transaction.atomic():
            change, warnings = svc.merge(body.into, body.from_, request.user)
    except svc.Refused as e:
        raise _refused(e) from None
    return MergeOut(project=_out(Project.objects.get(pk=body.into)), change_id=change.pk, warnings=warnings)


@router.post("/projects/{id}/split", response=SplitOut)
def split_project(request, id: int, body: SplitIn):  # noqa: A002
    """New projects in the same season for part of this one: by rig, by panel, or the chosen datasets."""
    p = get_object_or_404(Project, pk=id)
    try:
        with transaction.atomic():
            change, made, warnings = svc.split(p, body.by, body.dataset_ids, body.name, request.user)
    except svc.Refused as e:
        raise _refused(e) from None
    return SplitOut(project=_out(p), created=[_out(q) for q in made], change_id=change.pk, warnings=warnings)


@router.get("/projects/{id}/impact", response=ImpactOut)
def project_impact(request, id: int, into: int | None = None):  # noqa: A002
    """What merging, splitting or removing this project would touch, for the page to ask first."""
    p = get_object_or_404(Project, pk=id)
    target = get_object_or_404(Project, pk=into) if into else None
    return ImpactOut(**svc.impact(p, target))
