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
