"""2026-10-14: a frame with no recorded night is dated by its evening (NINA's $$DATEMINUS12$$), and flats whose exposures
differ by the flat wizard's jitter are one set."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from apps.catalogue.models import Frame
from apps.catalogue.services.calibration_sets import assign_calibration_set
from apps.processing.matching import _night

pytestmark = pytest.mark.django_db


def _frame(sha: str, when: datetime, **kw) -> Frame:
    return Frame.objects.create(
        sha256=sha * 64,
        size_bytes=1,
        format="fits",
        status="catalogued",
        first_seen_at=when,
        date_obs_utc=when,
        **kw,
    )


def test_a_frame_with_no_night_belongs_to_its_evening():
    # KStars wrote no site: a flat at 06:25 UTC on 14 Feb belongs to the night of the 13th, not the 14th
    flat = _frame("a", datetime(2026, 2, 14, 6, 25, tzinfo=UTC), frame_type="flat")
    assert _night(flat) == date(2026, 2, 13)
    # Labuan Bajo (120° E): 13:00 UTC is 21:00 local, the night of the same day
    seestar = _frame("b", datetime(2026, 9, 10, 13, 0, tzinfo=UTC), frame_type="light", site_lon=119.9)
    assert _night(seestar) == date(2026, 9, 10)


def test_flats_jittered_by_the_flat_wizard_are_one_set_and_darks_stay_exact():
    common = {"frame_type": "flat", "camera": "ATR2600M", "filter_norm": "L", "gain": 120, "offset": 60}
    a = _frame("c", datetime(2026, 2, 17, 22, 44, tzinfo=UTC), exptime_s=0.00654, **common)
    assign_calibration_set(a)
    a.save()
    b = _frame("d", datetime(2026, 2, 17, 22, 49, tzinfo=UTC), exptime_s=0.00655, **common)
    assign_calibration_set(b)
    assert b.calibration_set_id == a.calibration_set_id
    far = _frame("e", datetime(2026, 2, 17, 23, 4, tzinfo=UTC), exptime_s=0.1411, **common)
    assign_calibration_set(far)
    assert far.calibration_set_id != a.calibration_set_id  # a different panel brightness: its own set
    dark = {"frame_type": "dark", "camera": "ATR2600M", "gain": 120, "offset": 60}
    d1 = _frame("f", datetime(2026, 2, 17, 23, 30, tzinfo=UTC), exptime_s=60.0, **dark)
    assign_calibration_set(d1)
    d1.save()
    d2 = _frame("0", datetime(2026, 2, 17, 23, 31, tzinfo=UTC), exptime_s=61.0, **dark)
    assign_calibration_set(d2)
    assert d2.calibration_set_id != d1.calibration_set_id
