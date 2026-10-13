"""Activity names what a job works on first (owner 2026-10-13): "Soul Nebula · Askar + ATR · SII", not only rig."""

from __future__ import annotations

import pytest

from apps.catalogue.models import Collection, Dataset, Rig
from substation.tasks.activity import _object_label

pytestmark = pytest.mark.django_db


def test_a_job_label_leads_with_the_object():
    rig = Rig.objects.create(key="k", name="Askar 71F + ATR2600M", camera="ATR2600M", telescope="Askar 71F")
    col = Collection.objects.create(name="IC 1848 - Soul Nebula")
    d = Dataset.objects.create(group_key="g", target="IC 1848", filter_norm="SII", rig=rig, collection=col)
    assert _object_label(d) == "Soul Nebula · Askar 71F + ATR2600M · SII"
    loose = Dataset.objects.create(group_key="h", target="M 17", filter_norm="LP", rig=rig)
    assert _object_label(loose) == "M 17 · Askar 71F + ATR2600M · LP"


def test_framing_shows_the_finished_master_when_its_preview_lines_up(tmp_path):
    from PIL import Image

    from apps.catalogue.api_library import _master_image
    from apps.processing.models import Master

    d = Dataset.objects.create(group_key="f", target="IC 1848", filter_norm="OIII")
    pv, st, small = tmp_path / "m.jpg", tmp_path / "s.jpg", tmp_path / "t.jpg"
    Image.new("L", (40, 30)).save(pv)
    Image.new("L", (40, 30)).save(st)
    Image.new("L", (20, 30)).save(small)
    runs = [{"run": 1, "stages": [{"state": "done", "preview": str(st)}, {"state": "skipped"}]}]
    m = Master.objects.create(
        dataset=d, version=1, state="current", preview_path=str(pv), report={"post_runs": runs}
    )
    assert _master_image(m) == f"/api/v1/stacks/{m.pk}/post/1/0/preview"
    runs[0]["stages"][0]["preview"] = str(small)  # a trimmed stage wouldn't line up: the master's own preview
    Master.objects.filter(pk=m.pk).update(report={"post_runs": runs})
    m.refresh_from_db()
    assert _master_image(m) == f"/api/v1/stacks/{m.pk}/preview"
