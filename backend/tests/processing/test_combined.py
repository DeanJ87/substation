"""004 T022 / 004-DR-05: combined masters per filter for a collection, with the stale notice."""

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Collection, Dataset
from apps.processing.models import CombinedMaster, Master
from substation.tasks.models import Task

pytestmark = pytest.mark.django_db


def master(col, key, filt, subs, tmp_path, accepted=0.0):
    d = Dataset.objects.create(
        group_key=key,
        display_name=key,
        target="IC 1848",
        filter_norm=filt,
        collection=col,
        accepted_integration_s=accepted,
    )
    out = tmp_path / f"{key}.fit"
    out.write_bytes(b"x")
    return Master.objects.create(
        dataset=d, version=1, state="current", sub_count=subs, integration_s=subs * 600, output_path=str(out)
    )


def test_plan_start_and_stale(admin_client, tmp_path):
    col = Collection.objects.create(name="Soul")
    ha = master(col, "ha", "Hα", 60, tmp_path, accepted=36000)
    master(col, "oiii", "OIII", 40, tmp_path)
    master(col, "oiii2", "OIII", 20, tmp_path)
    plan = admin_client.get(f"/api/v1/collections/{col.pk}/combined").json()
    assert plan["reference"] == ha.pk and sorted(plan["filters"]) == ["Hα", "OIII"] and plan["combined"] == []
    assert len(plan["filters"]["OIII"]) == 2
    r = admin_client.post(f"/api/v1/collections/{col.pk}/combined")
    assert r.status_code == 201 and {c["filter"] for c in r.json()} == {"Hα", "OIII"}
    assert Task.objects.filter(name__endswith="combine.combine").count() == 1
    # once made, a newer master for one of the OIII datasets makes that combined master stale
    CombinedMaster.objects.update(state="current", finished_at=datetime(2026, 10, 2, tzinfo=UTC))
    d = Dataset.objects.get(group_key="oiii2")
    Master.objects.filter(dataset=d).update(state="superseded")
    out = tmp_path / "oiii2b.fit"
    out.write_bytes(b"x")
    Master.objects.create(
        dataset=d, version=2, state="current", sub_count=61, integration_s=61 * 600, output_path=str(out)
    )
    rows = {
        c["filter"]: c for c in admin_client.get(f"/api/v1/collections/{col.pk}/combined").json()["combined"]
    }
    assert rows["OIII"]["stale"] == "OIII combined master is stale: 41 new subs since 2 October."
    assert rows["Hα"]["stale"] == ""


def test_nothing_to_combine_says_why(admin_client):
    col = Collection.objects.create(name="Empty")
    r = admin_client.post(f"/api/v1/collections/{col.pk}/combined")
    assert r.status_code == 422 and "Stack each dataset first" in r.json()["message"]


def test_combined_masters_stay_within_a_project_and_a_pixel_scale(admin_client, tmp_path, monkeypatch):
    """Owner 2026-10-10: combine within a project; never 1.6″/px with 3.7″/px."""
    from apps.catalogue.models import Project
    from apps.processing import combine

    col = Collection.objects.create(name="Helix")
    ha = master(col, "ha", "Hα", 60, tmp_path, accepted=36000)
    lp = master(col, "lp", "LP", 40, tmp_path)
    scales = {ha.dataset_id: 1.58, lp.dataset_id: 3.67}
    monkeypatch.setattr(combine, "_scale", lambda m: scales[m.dataset_id])
    plan = admin_client.get(f"/api/v1/collections/{col.pk}/combined").json()
    assert list(plan["filters"]) == ["Hα"] and "3.67″/px" in plan["left_out"][0]
    p = Project.objects.create(collection=col, own_name="Seestar")
    Dataset.objects.filter(pk=lp.dataset_id).update(project=p)
    plan = admin_client.get(f"/api/v1/collections/{col.pk}/combined?project={p.pk}").json()
    assert list(plan["filters"]) == ["LP"] and plan["left_out"] == []


def test_outside_a_mosaic_masters_of_another_panel_are_left_out(admin_client, tmp_path):
    """Amendment 2026-10-22: a season's project can hold a mosaic's panels beside a single field; only a mosaic
    stitches panels, so a single field's combine leaves the other panels out and says so."""
    from apps.catalogue.models import Project

    col = Collection.objects.create(name="Heart")
    ha = master(col, "ha", "Hα", 60, tmp_path, accepted=36000)
    other = master(col, "ha2", "Hα", 30, tmp_path)
    Dataset.objects.filter(pk=other.dataset_id).update(panel=2)
    p = Project.objects.create(collection=col, season="2026", kind_override="single")
    Dataset.objects.filter(pk__in=[ha.dataset_id, other.dataset_id]).update(project=p)
    plan = admin_client.get(f"/api/v1/collections/{col.pk}/combined?project={p.pk}").json()
    assert [i["master"] for i in plan["filters"]["Hα"]] == [ha.pk]
    assert "panel 2, not none" in plan["left_out"][0]
    Project.objects.filter(pk=p.pk).update(kind_override="mosaic")
    plan = admin_client.get(f"/api/v1/collections/{col.pk}/combined?project={p.pk}").json()
    assert len(plan["filters"]["Hα"]) == 2 and plan["left_out"] == []


def test_registered_sequence_placements(tmp_path):
    """Mosaic: image sizes and translations read from a Siril .seq after framing max."""
    from apps.processing.combine import _placements

    seq = tmp_path / "r_m_.seq"
    seq.write_text("""S 'r_m_' 1 2 1 5 -1 6 1 0 0
L 1
I 1 1 6237,4185
I 2 0 6224,4168
R0 3.6 2.8 0.92 0 0.001 1734 H 1 0 14 0 1 2503 0 0 1
R0 3.1 3.1 0.89 0 0.001 1566 H 1 0 36 0 1 2542 0 0 1
""")
    assert _placements(seq) == {1: (14, 2503, 6237, 4185), 2: (36, 2542, 6224, 4168)}
