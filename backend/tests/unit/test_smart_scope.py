"""Spec 006: a Seestar is recognised by TELESCOP or INSTRUME, whatever its firmware writes."""

import pytest

from apps.catalogue.services.library import is_smart_scope, smart_name


@pytest.mark.parametrize(
    ("telescope", "camera", "smart"),
    [
        ("S30 Pro_db50a4a4", "", True),
        ("S30 Pro_db50a4a4", "imx585", True),
        ("", "ZWO Seestar S30 Pro", True),
        ("S50", None, True),
        ("Askar 71F", "ATR2600M", False),
        ("SkyWatcher S30x", "", False),
    ],
)
def test_seestar_detection(telescope, camera, smart):
    assert is_smart_scope(telescope, camera) is smart


def test_seestar_name():
    assert smart_name("S30 Pro_db50a4a4", "imx585") == "Seestar S30 Pro"
    assert smart_name("", "ZWO Seestar S50") == "Seestar S50"
