"""The migration to projects by season (amendment 2026-10-22), on the IC 1805 shape the old suggester left: a
2-panel mosaic and single fields per rig, over two seasons. A season's projects merge into one, each merge an
undoable Change; groups that would lose something are held apart and flagged instead."""

from __future__ import annotations

from datetime import date
from itertools import count

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

BEFORE = ("catalogue", "0025_project_seasons")


def _targets(executor: MigrationExecutor) -> list[tuple[str, str]]:
    return [BEFORE if app == "catalogue" else (app, name) for app, name in executor.loader.graph.leaf_nodes()]


def test_projects_join_by_season_and_held_groups_are_flagged():
    executor = MigrationExecutor(connection)
    targets = _targets(executor)
    executor.migrate(targets)
    old = executor.loader.project_state(targets).apps
    Collection = old.get_model("catalogue", "Collection")
    Project = old.get_model("catalogue", "Project")
    Dataset = old.get_model("catalogue", "Dataset")
    Night = old.get_model("catalogue", "Night")
    DatasetNight = old.get_model("catalogue", "DatasetNight")
    Rig = old.get_model("catalogue", "Rig")
    Library = old.get_model("libraries", "Library")
    FinishedProject = old.get_model("finished", "FinishedProject")
    CombinedMaster = old.get_model("processing", "CombinedMaster")
    User = old.get_model("auth", "User")
    owner = User.objects.create(username="owner", is_superuser=True)
    n = count()

    def ds(col, project, nights, rig=None, panel=None, hours=1.0):
        k = next(n)
        d = Dataset.objects.create(
            group_key=f"m{k}",
            display_name=f"m{k}",
            target="IC 1805",
            filter_norm="Hα",
            panel=panel,
            rig=rig,
            collection=col,
            project=project,
            project_position=k,
            accepted_integration_s=hours * 3600 * len(nights),
        )
        for day in nights:
            night, _ = Night.objects.get_or_create(site_key="50,-4", date=day)
            DatasetNight.objects.create(dataset=d, night=night, integration_s=hours * 3600)
        return d

    def proj(col, name, kind="single", panels=None, goals=None):
        return Project.objects.create(
            collection=col,
            own_name=name,
            kind=kind,
            planned_panels=panels,
            goals=goals or {},
            position=next(n),
        )

    heart = Collection.objects.create(name="IC 1805")
    askar = Rig.objects.create(key="a", name="Askar 71F + ATR2600M")
    sony = Rig.objects.create(key="s", name="Askar 71F + Sony A73")
    tt = Rig.objects.create(key="t", name="TTArtisan + Sony A73")
    mosaic = proj(heart, "2-panel mosaic 2026", "mosaic", 2, {"Hα": 10})
    single26 = proj(heart, "Single field 2026 · Askar 71F + ATR2600M")
    sony25 = proj(heart, "Single field · Askar 71F + Sony A73")
    tt25 = proj(heart, "Single field · TTArtisan + Sony A73")
    ds(heart, mosaic, [date(2026, 9, 1), date(2026, 9, 2)], askar, 1)
    ds(heart, mosaic, [date(2026, 9, 3), date(2026, 9, 4)], askar, 2)
    ds(heart, single26, [date(2026, 9, 20)], askar)
    ds(heart, sony25, [date(2025, 11, 20), date(2025, 12, 2)], sony, hours=2)
    ds(heart, tt25, [date(2026, 1, 10)], tt)
    cm = CombinedMaster.objects.create(collection=heart, project=single26, filter_norm="Hα", version=1)

    # held: an absorbed project linked to a finished image
    soul = Collection.objects.create(name="IC 1848")
    soul_big = proj(soul, "Single field 2026")
    soul_small = proj(soul, "Single field 2026 · TTArtisan + Sony A73")
    ds(soul, soul_big, [date(2026, 9, 1), date(2026, 9, 2)])
    ds(soul, soul_small, [date(2026, 9, 3)])
    lib = Library.objects.create(name="completed", mount_path="/tmp/c", role="completed")
    fp = FinishedProject.objects.create(
        library=lib, rel_path="Astro/x", kind="astro", subject="IC 1848", name="Soul"
    )
    fp.linked_projects.add(soul_small)
    # held: two named by hand; goals that differ; mosaics of different sizes
    named = Collection.objects.create(name="NGC 7000")
    for name in ("North America", "Pelican"):
        ds(named, proj(named, name), [date(2026, 8, 1)])
    goals = Collection.objects.create(name="M 31")
    for h in (10, 20):
        ds(goals, proj(goals, "Single field 2026", goals={"L": h}), [date(2026, 8, 1)])
    sizes = Collection.objects.create(name="M 33")
    for k in (2, 4):
        ds(sizes, proj(sizes, f"{k}-panel mosaic 2026", "mosaic", k), [date(2026, 8, 1)], panel=1)

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

    from apps.catalogue.models import Change
    from apps.catalogue.models import Dataset as LiveDataset
    from apps.catalogue.models import Project as LiveProject
    from apps.catalogue.services import projects as svc
    from apps.processing.models import CombinedMaster as LiveCombined

    left = {p.season: p for p in LiveProject.objects.filter(collection_id=heart.pk)}
    assert set(left) == {"2026", "2025–26"}
    assert left["2026"].pk == mosaic.pk and left["2026"].own_name == ""
    assert left["2026"].name == "2026" and left["2026"].kind == "mosaic" and left["2026"].planned_panels == 2
    assert left["2026"].goals == {"Hα": 10}
    assert left["2025–26"].pk == sony25.pk and left["2025–26"].kind_override is None
    assert LiveDataset.objects.filter(collection_id=heart.pk, project=None).count() == 0
    assert LiveDataset.objects.filter(project=left["2026"]).count() == 3
    assert LiveCombined.objects.get(pk=cm.pk).project_id == mosaic.pk
    changes = list(Change.objects.filter(kind="project").order_by("pk"))
    assert len(changes) == 2 and all(c.user_id == owner.pk and c.data["op"] == "merge" for c in changes)

    def held(col):
        ps = list(LiveProject.objects.filter(collection_id=col.pk))
        assert len(ps) == 2 and all(p.needs_review for p in ps)
        return ps[0].review_reason

    assert "Soul" in held(soul)
    assert "Named by hand" in held(named)
    assert "Goals differ" in held(goals)
    assert "Mosaics of 2 and 4 panels" in held(sizes)
    assert {p.own_name for p in LiveProject.objects.filter(collection_id=named.pk)} == {
        "North America",
        "Pelican",
    }

    # a merge the migration made undoes like any other: the single field comes back with its own pk
    first = next(c for c in changes if c.data["into"]["pk"] == mosaic.pk)
    svc.undo(first.data)
    back = LiveProject.objects.get(pk=single26.pk)
    assert back.season == "2026" and back.kind_override == "single" and back.datasets.count() == 1
    assert LiveCombined.objects.get(pk=cm.pk).project_id == single26.pk
