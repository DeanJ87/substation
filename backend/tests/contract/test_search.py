"""007-DR-26: search from the header finds collections, datasets, nights and files."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from apps.catalogue.models import Collection, Copy, Dataset, Frame, Night
from apps.libraries.models import Library

pytestmark = pytest.mark.django_db


@pytest.fixture
def library(tmp_path):
    col = Collection.objects.create(name="NGC 7635 - Bubble Nebula", objects_text="NGC 7635 · Sh2-162")
    ds = Dataset.objects.create(
        group_key="k",
        display_name="NGC 7635 - Bubble Nebula · Hα",
        target="NGC 7635",
        filter_norm="Hα",
        collection=col,
        sub_count=3,
    )
    night = Night.objects.create(site_key="55.0,-1.7", date=date(2026, 9, 25))
    lib = Library.objects.create(name="cap", mount_path=str(tmp_path))
    now = datetime.now(UTC)
    f = Frame.objects.create(
        sha256="b" * 64,
        size_bytes=1,
        format="fits",
        first_seen_at=now,
        status="catalogued",
        dataset=ds,
        night=night,
        target="NGC 7635",
    )
    Copy.objects.create(
        frame=f,
        library=lib,
        rel_path="Bubble/LIGHT/Light_Bubble_600s_0042.fits",
        st_dev=1,
        st_ino=1,
        st_size=1,
        st_mtime_ns=1,
        first_seen_at=now,
        last_seen_at=now,
    )
    return col, ds


def test_designation_with_or_without_its_space(admin_client, library):
    col, ds = library
    for q in ("ngc7635", "NGC 7635", "bubble"):
        r = admin_client.get(f"/api/v1/search?q={q}").json()
        assert [c["id"] for c in r["collections"]] == [col.pk], q
        assert [d["id"] for d in r["datasets"]] == [ds.pk], q


def test_nights_by_date_and_files_by_name(admin_client, library):
    r = admin_client.get("/api/v1/search?q=2026-09").json()
    assert r["nights"] == [{"date": "2026-09-25", "datasets": 1}]
    r = admin_client.get("/api/v1/search?q=0042").json()
    assert (
        r["files"][0]["name"] == "Light_Bubble_600s_0042.fits" and r["files"][0]["folder"] == "Bubble/LIGHT"
    )


def test_too_short_finds_nothing(admin_client, library):
    assert admin_client.get("/api/v1/search?q=n").json() == {
        "collections": [],
        "datasets": [],
        "nights": [],
        "files": [],
    }


def test_a_filter_alias_finds_the_filter(admin_client, library):
    """ "Ha" finds the Hα dataset, as the filter is normalised when subs are read."""
    r = admin_client.get("/api/v1/search", {"q": "bubble ha"}).json()
    assert [d["name"] for d in r["datasets"]] == ["NGC 7635 - Bubble Nebula · Hα"]
