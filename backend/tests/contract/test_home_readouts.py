"""The Library's readouts (owner 2026-10-13): what needs you, missing calibration, ready to stack, this month."""

from __future__ import annotations

import pytest

from apps.catalogue.models import Dataset

pytestmark = pytest.mark.django_db


def test_the_home_readouts_say_what_to_do_next(admin_client):
    Dataset.objects.create(
        group_key="m81",
        target="M 81",
        filter_norm="L",
        display_name="M 81 · L",
        sub_count=20,
        accepted_count=12,
    )
    r = admin_client.get("/api/v1/library").json()["readouts"]
    assert r["ready_to_stack"]["datasets"] == 1 and r["ready_to_stack"]["top"][0]["new"] == 12
    assert set(r["needs_you"]) == {"review", "reconcile", "stale"}
    assert r["missing_calibration"] == {"subs": 0, "top": []}
    assert set(r["this_month"]) == {"hours", "nights", "last"}
