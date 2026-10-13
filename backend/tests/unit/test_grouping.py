"""T045: OBJECT target/panel parsing, dataset keys and display names (research R10)."""

import pytest

from apps.catalogue.services.grouping import DatasetKey, display_name, split_object
from apps.ingest.fields import normalise_filter


@pytest.mark.parametrize(
    ("obj", "target", "panel"),
    [
        ("NGC 7000 Panel 3", "NGC 7000", 3),
        ("Heart Nebula Panel 2", "Heart Nebula", 2),
        ("Heart Nebula panel 12", "Heart Nebula", 12),
        ("M 101", "M 101", None),
        ("  M 31  ", "M 31", None),
        ("Panel 3", "Panel 3", None),  # nothing before "Panel": keep as the target
    ],
)
def test_split_object(obj, target, panel):
    assert split_object(obj) == (target, panel)


def test_dataset_key_distinguishes_every_grouping_field():
    base = dict(
        target="NGC 7000",
        panel=3,
        filter_norm="Hα",
        camera="ATR2600M",
        telescope="Askar 71F",
        xbin=1,
        ybin=1,
        gain=120,
        offset=80,
    )
    k = DatasetKey(**base)
    assert DatasetKey(**base).group_key == k.group_key
    for field, other in [
        ("panel", 2),
        ("filter_norm", "OIII"),
        ("gain", 100),
        ("offset", 30),
        ("xbin", 2),
        ("camera", "ASI2600MM"),
        ("telescope", "RedCat 51"),
    ]:
        assert DatasetKey(**{**base, field: other}).group_key != k.group_key
    assert DatasetKey(**{**base, "panel": None}).group_key != k.group_key


def test_display_name():
    assert display_name("NGC 7000", 3, "Hα") == "NGC 7000 · Panel 3 · Hα"
    assert display_name("M 101", None, "L") == "M 101 · L"


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("Halpha", "Hα"),
        ("HAlpha", "Hα"),
        ("Ha", "Hα"),
        ("H-alpha", "Hα"),
        ("OIII", "OIII"),
        ("O3", "OIII"),
        ("SII", "SII"),
        ("S2", "SII"),
        ("Oxygen-III", "OIII"),
        ("Sulphur-II", "SII"),
        ("Sulfur II", "SII"),
        ("Luminance", "L"),
        ("Lum", "L"),
        ("Red", "R"),
        ("G", "G"),
        ("Ha ", "Hα"),
        ("  oiii", "OIII"),
        ("UV/IR Cut", "UV/IR Cut"),
    ],
)
def test_filter_normalisation(raw, norm):
    assert normalise_filter(raw, {}) == norm


def test_user_aliases_win():
    assert normalise_filter("Ha 3nm", {"ha 3nm": "Hα"}) == "Hα"
    assert normalise_filter("Halpha", {"halpha": "Ha (custom)"}) == "Ha (custom)"
