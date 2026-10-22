"""020-DR-15: what a cumulative progressive stack would build: checkpoints, palette, folding, why not."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from apps.finished import progression as pg
from apps.finished.models import FileRole, FinishedFile, Progression, ProgressionState
from apps.processing.models import MachineGrade

from .progression_data import finished, subs

pytestmark = pytest.mark.django_db
D0 = date(2026, 9, 2)


def days(n: int, start: date = D0) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def test_five_nights_are_five_checkpoints():
    groups = pg.group_nights(days(5))
    assert groups == [[d] for d in days(5)]
    assert pg.label(groups[0]) == "2 Sep"


def test_thirty_nights_are_twelve_contiguous_near_equal_groups():
    nights = days(30, date(2026, 9, 20))
    groups = pg.group_nights(nights)
    assert len(groups) == 12
    assert [d for g in groups for d in g] == nights  # in order, nothing lost or repeated
    assert {len(g) for g in groups} <= {2, 3}
    assert pg.label(groups[0]) == "20–22 Sep"
    assert pg.label([date(2026, 9, 28), date(2026, 10, 2)]) == "28 Sep–2 Oct"
    assert pg.label([date(2026, 10, 3), date(2026, 10, 9)]) == "3–9 Oct"
    assert pg.label([date(2025, 12, 30), date(2026, 1, 2)]) == "30 Dec 2025–2 Jan 2026"


def _by(filters: dict[str, int]) -> dict:
    from types import SimpleNamespace

    return {
        k: [(SimpleNamespace(exptime_s=300, pk=f"{k}{i}"), 1.0) for i in range(n)] for k, n in filters.items()
    }


def test_the_palette_follows_the_filters():
    assert pg.default_mapping(_by({"Hα": 4, "OIII": 4, "SII": 3}), set()) == ("SHO", ["Hα", "OIII", "SII"])
    assert pg.default_mapping(_by({"Hα": 4, "OIII": 4}), set()) == ("HOO", ["Hα", "OIII"])
    assert pg.default_mapping(_by({"L": 9, "R": 3, "G": 3, "B": 3}), set()) == ("RGB", ["R", "G", "B"])
    assert pg.default_mapping(_by({"IRCUT": 5}), {"IRCUT"}) == ("OSC", ["IRCUT"])
    assert pg.default_mapping(_by({"L": 5, "Hα": 2}), set()) == ("MONO", ["L"])
    # one OIII sub is no channel: the largest filter alone, in grey
    assert pg.default_mapping(_by({"Hα": 4, "OIII": 1}), set()) == ("MONO", ["Hα"])
    assert pg.rgb_of("SHO", []) == ("SII", "Hα", "OIII") and pg.rgb_of("HOO", []) == ("Hα", "OIII", "OIII")


def test_early_nights_fold_into_the_first_checkpoint_until_every_channel_has_two_subs(tmp_path):
    fp, project = finished(tmp_path)
    n = days(5)
    subs(project, "Hα", [(n[0], 3), (n[1], 2), (n[2], 2), (n[3], 2), (n[4], 2)])
    subs(project, "OIII", [(n[1], 1), (n[2], 1), (n[3], 2), (n[4], 2)])
    p = pg.plan(fp)
    assert p["mapping"] == "HOO"
    cks = p["checkpoints"]
    assert [c["order"] for c in cks] == [1, 2, 3]
    assert cks[0]["nights"] == [d.isoformat() for d in n[:3]] and cks[0]["label"] == "2–4 Sep"
    assert cks[0]["filters"] == {
        "Hα": {"subs": 7, "integration_s": 2100},
        "OIII": {"subs": 2, "integration_s": 600},
    }
    assert cks[-1]["subs"] == 11 + 6 and cks[-1]["integration_s"] == 17 * 300  # cumulative
    assert cks[1]["label"] == "5 Sep"
    assert len({c["hash"] for c in cks}) == 3


def test_why_a_progression_cant_be_built(tmp_path):
    fp, project = finished(tmp_path)
    subs(project, "Hα", [(D0, 1)])
    assert pg.availability(fp) == "Needs at least two kept subs."

    subs(project, "Hα", [(D0, 3)], panel=1)
    subs(project, "Hα", [(D0, 3)], panel=2)
    why = pg.availability(fp)  # a mosaic by its shot panels, or by the panels alone
    assert ("mosaic" in why or "panels" in why) and why.endswith(pg.SINGLE_FIELD)


def test_two_pixel_scales_are_not_one_field(tmp_path):
    fp, project = finished(tmp_path)
    subs(project, "Hα", [(D0, 3)], scale=1.5)
    subs(project, "OIII", [(D0, 3)], scale=3.0)
    assert pg.availability(fp) == f"Its subs have more than one pixel scale. {pg.SINGLE_FIELD}"


def test_seestar_mosaic_subs_are_not_one_field(tmp_path):
    fp, project = finished(tmp_path)
    subs(project, "IRCUT", [(D0, 4)], scale=None, name="Light_mosaic_IC 1805_10.0s_IRCUT_{i}.fit")
    assert pg.availability(fp) == f"Mosaic: Seestar mosaic subs. {pg.SINGLE_FIELD}"


def test_an_unavailable_start_says_why_and_queues_nothing(tmp_path):
    from substation.tasks.models import Task

    fp, project = finished(tmp_path)
    subs(project, "Hα", [(D0, 1)])
    prog = pg.start(fp)
    assert prog.state == ProgressionState.UNAVAILABLE and prog.reason == "Needs at least two kept subs."
    assert not Task.objects.exists()


def test_a_start_queues_one_build_below_master_builds(tmp_path):
    from substation.tasks.models import Task

    fp, project = finished(tmp_path)
    cal = tmp_path / "cal"
    subs(project, "Hα", [(D0, 3), (D0 + timedelta(days=1), 3)], cal_dir=cal)
    prog = pg.start(fp, auto=True)
    assert prog.state == ProgressionState.QUEUED and prog.task_id
    t = Task.objects.get()
    assert t.name.endswith("build_progression") and t.priority < 45
    pg.start(fp)  # already queued: still one job
    assert Task.objects.count() == 1


def test_an_automatic_start_waits_when_most_subs_need_calibrating_again(tmp_path):
    from substation.tasks.models import Task

    fp, project = finished(tmp_path)
    subs(project, "Hα", [(D0, 4)])  # no calibrated files in the cache
    prog = pg.start(fp, auto=True)
    assert prog.state == ProgressionState.NONE and "4 of 4 subs would need calibrating again" in prog.reason
    assert not Task.objects.exists()
    assert pg.start(fp).state == ProgressionState.QUEUED  # the button builds it anyway


def test_the_input_hash_follows_the_subs_not_the_file_roles(tmp_path):
    fp, project = finished(tmp_path)
    n = days(3)
    frames = subs(project, "Hα", [(d, 3) for d in n])
    subs(project, "OIII", [(d, 3) for d in n])
    first = pg.plan(fp)["input_hash"]
    assert pg.plan(fp)["input_hash"] == first

    f = FinishedFile.objects.create(
        project=fp, rel_path="exports/a.png", section="exports", size_bytes=1, mtime=1.0
    )
    f.role = FileRole.FINAL
    f.save()
    assert pg.plan(fp)["input_hash"] == first  # a role is not an input

    MachineGrade.objects.filter(frame=frames[0]).update(verdict="reject")
    regraded = pg.plan(fp)["input_hash"]
    assert regraded != first

    subs(project, "OIII", [(n[-1], 1)])
    assert pg.plan(fp)["input_hash"] != regraded


def test_the_reference_is_kept_while_its_sub_is(tmp_path):
    fp, project = finished(tmp_path)
    ha = subs(project, "Hα", [(D0, 4)], stars=100)
    subs(project, "OIII", [(D0, 4)], stars=5000)
    p = pg.plan(fp)
    assert p["reference"] == ha[-1].pk  # most stars in Hα, not in OIII
    Progression.objects.create(project=fp, reference_frame=ha[0].pk)
    assert pg.plan(fp)["reference"] == ha[0].pk
    MachineGrade.objects.filter(frame=ha[0]).update(verdict="reject")
    assert pg.plan(fp)["reference"] == ha[-1].pk


def test_projects_linked_before_progressions_existed_catch_up(tmp_path, monkeypatch):
    """The periodic job starts one for a linked project that never had one, once, with the automatic limits."""
    from substation.tasks.management.commands import supervise

    fp, _ = finished(tmp_path)
    calls = []
    monkeypatch.setattr(pg, "start", lambda proj, auto=False, force=False: calls.append((proj.pk, auto)))
    supervise._auto_progressions()
    assert calls == [(fp.pk, True)]
    Progression.objects.create(project=fp)
    supervise._auto_progressions()
    assert len(calls) == 1  # it has one now: left to the button and to linking
