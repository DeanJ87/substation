"""Spec 017: the lights waiting for calibration, as what to shoot, and the darks as a NINA sequence."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime

import pytest

from apps.catalogue.models import Dataset, Frame, FrameStatus, FrameType, Night
from apps.processing.models import CalibrationMatch, MatchState

pytestmark = pytest.mark.django_db
T = datetime(2026, 10, 11, 22, tzinfo=UTC)


def _light(i: int, ds: Dataset, night: Night, reason: str, exp=120.0, temp=-10.0, **kw) -> Frame:
    f = Frame.objects.create(
        sha256=f"{i:064x}",
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
        dataset=ds,
        night=night,
        camera="ATR2600M",
        telescope="Askar 71F",
        exptime_s=exp,
        gain=120,
        offset=30,
        xbin=1,
        set_temp_c=temp,
        filter_norm=kw.pop("filter_norm", "OIII"),
        **kw,
    )
    CalibrationMatch.objects.create(frame=f, state=MatchState.AWAITING, reason=reason)
    return f


def test_waiting_lights_become_a_list_of_what_to_shoot(admin_client):
    ds = Dataset.objects.create(
        group_key="m81", target="M 81", filter_norm="OIII", display_name="M 81 · OIII"
    )
    night = Night.objects.create(site_key="55,-1.7", date=date(2026, 10, 11))
    for i in range(3):
        _light(
            i,
            ds,
            night,
            "Awaiting calibration: no 120 s dark within 2 °C of -10 °C (have 0 °C); no OIII flat.",
        )
    _light(9, ds, night, "Awaiting calibration: no 300 s dark at gain 120 and offset 30.", exp=300)
    _light(10, ds, night, "Awaiting calibration: the 60 s dark has no gain: confirm it in Reconcile.", exp=60)
    _light(
        11, ds, night, "Awaiting calibration: waiting for the 11 Oct Ha flats to be built.", filter_norm="Ha"
    )
    r = admin_client.get("/api/v1/calibration/shopping").json()
    darks = [n for n in r["needs"] if n["kind"] == "dark"]
    flats = [n for n in r["needs"] if n["kind"] == "flat"]
    assert [(d["exptime_s"], d["temp_c"], d["subs"]) for d in darks] == [(120, -10, 3), (300, -10, 1)]
    assert flats == [
        {**flats[0], "filter": "OIII", "telescope": "Askar 71F", "subs": 3, "nights": ["2026-10-11"]}
    ]
    others = {o["reason"]: o["subs"] for o in r["others"]}
    assert others == {
        "the 60 s dark has no gain: confirm it in Reconcile": 1,
        "waiting for the 11 Oct Ha flats to be built": 1,
    }


def test_the_darks_export_as_a_nina_sequence(admin_client):
    ds = Dataset.objects.create(group_key="m81", target="M 81", filter_norm="L", display_name="M 81 · L")
    night = Night.objects.create(site_key="55,-1.7", date=date(2026, 10, 11))
    _light(1, ds, night, "Awaiting calibration: no 600 s dark within 2 °C of -20 °C.", exp=600, temp=-20)
    _light(2, ds, night, "Awaiting calibration: no 120 s dark within 2 °C of 0 °C.", exp=120, temp=0)
    r = admin_client.get("/api/v1/calibration/shopping/nina.xml?frames=25")
    assert r.status_code == 200 and "substation-calibration.xml" in r["Content-Disposition"]
    root = ET.fromstring(r.content)
    rows = root.findall("CaptureSequence")
    assert [
        (x.findtext("ExposureTime"), x.findtext("ImageType"), x.findtext("TotalExposureCount")) for x in rows
    ] == [
        ("600", "DARK", "25"),  # coldest first
        ("120", "DARK", "25"),
    ]
    assert rows[0].findtext("Gain") == "120" and rows[0].findtext("Offset") == "30"
    assert b"-20 \xc2\xb0C" in r.content  # the set point, in the row's comment
    csv = admin_client.get("/api/v1/calibration/shopping.csv").content.decode()
    assert csv.splitlines()[0].startswith("kind,camera") and "600" in csv


def test_binned_lights_are_not_on_the_list(admin_client):
    """2026-10-15: 385 binned second-Hα subs still counted, as a row with no datasets."""
    ds = Dataset.objects.create(group_key="m42", target="M 42", filter_norm="Ha", display_name="M 42 · Ha")
    night = Night.objects.create(site_key="55,-1.7", date=date(2026, 1, 10))
    f = _light(1, ds, night, "Awaiting calibration: no 120 s dark within 2 °C of 0 °C.", temp=0)
    Frame.objects.filter(pk=f.pk).update(status=FrameStatus.BINNED)
    assert admin_client.get("/api/v1/calibration/shopping").json()["needs"] == []
