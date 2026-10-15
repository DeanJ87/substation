"""005-DR-29 (W40): the steps split out of the functions that branched eleven to fourteen ways behave as the
code they came from."""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from django.db.models import Q

from apps.catalogue.api_search import _slashed_night, _worded_night, night_filter
from apps.catalogue.scope import Scope, _dates, _near
from apps.engine.siril import _report
from apps.ingest.completeness import FITS_BLOCK, _data_bytes, _read_cards
from apps.ingest.pathcheck import Action
from apps.ingest.patterns import _date_obs, _put_token
from apps.ingest.sweep import SweepResult, _tally
from apps.processing.api import _why_dark, _why_flat
from apps.processing.imaging import FrameStats, _dark_checks, _flat_checks, _qa_frame, qa_set
from apps.processing.matching import _within_windows
from apps.processing.tasks import _calibrate_sequence, _collect_batch


def card(text: str) -> bytes:
    return text.ljust(80).encode("ascii")


def block(*cards: str) -> bytes:
    return b"".join(card(c) for c in cards).ljust(FITS_BLOCK, b" ")


# ---- night text --------------------------------------------------------------------------------------------


def test_slashed_night_is_day_first_and_reads_two_digit_years_as_this_century():
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?", "14/10/26")
    assert m is not None
    assert _slashed_night(m) == Q(date__month=10, date__day=14) & Q(date__year=2026)
    bad = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?", "10/14")
    assert bad is not None and _slashed_night(bad) is None


def test_worded_night_takes_words_in_any_order_and_refuses_other_words():
    assert _worded_night("2026 14th oct") == Q(date__month=10) & Q(date__day=14) & Q(date__year=2026)
    assert _worded_night("october") == Q(date__month=10)
    assert _worded_night("m31 october") is None
    assert _worded_night("14 2026") is None  # no month


def test_night_filter_still_routes_each_form():
    today = date(2026, 10, 15)
    assert night_filter("yesterday", today) == Q(date=date(2026, 10, 14))
    assert night_filter("14.10", today) == Q(date__month=10, date__day=14)
    assert night_filter("oct 14th", today) == Q(date__month=10) & Q(date__day=14)
    assert night_filter("orion", today) is None


# ---- scope -------------------------------------------------------------------------------------------------


def test_dates_combine_a_day_and_a_range():
    s = Scope(date=date(2026, 10, 1), date_to=date(2026, 10, 9))
    assert _dates(s, "night__") == Q(night__date=date(2026, 10, 1)) & Q(night__date__lte=date(2026, 10, 9))
    assert _dates(Scope(), "") == Q()


def test_near_is_a_box_wider_in_longitude_away_from_the_equator():
    p = {"lat": "site_lat", "lon": "site_lon"}
    q = _near(60.0, -2.0, 11.1, p)
    (lat_key, (lo, hi)), (lon_key, (wlo, whi)) = cast(list[Any], q.children)
    assert (lat_key, lon_key) == ("site_lat__range", "site_lon__range")
    assert hi - lo == pytest.approx(0.2)
    assert whi - wlo == pytest.approx(0.4)  # cos 60° halves a degree of longitude
    (_, (lo5, hi5)), _ = cast(list[Any], _near(0.0, 0.0, None, p).children)
    assert hi5 == pytest.approx(5 / 111)


# ---- FITS completeness -------------------------------------------------------------------------------------


def test_read_cards_stops_at_end_and_drops_comments():
    cards: dict[str, str] = {}
    assert _read_cards(block("SIMPLE  = T", "BITPIX  = 16 / bits", "END", "NAXIS   = 9"), cards)
    assert cards == {"SIMPLE": "T", "BITPIX": "16"}
    assert not _read_cards(block("NAXIS   = 2"), cards)


def test_data_bytes_multiplies_the_axes_and_rejects_a_missing_axis():
    assert _data_bytes({"BITPIX": "-32", "NAXIS": "2", "NAXIS1": "10", "NAXIS2": "4"}) == 160
    assert _data_bytes({"BITPIX": "8", "NAXIS": "0"}) == 0
    assert _data_bytes({"BITPIX": "16", "NAXIS": "2", "NAXIS1": "10"}) is None
    assert _data_bytes({"NAXIS": "0"}) is None


# ---- path patterns -----------------------------------------------------------------------------------------


def test_put_token_types_each_kind_and_skips_unreadable_values():
    out: dict[str, Any] = {}
    _put_token(out, "bin", "2x1", "bin")
    _put_token(out, "gain", "120", "int")
    _put_token(out, "exposure", "300.5", "float")
    _put_token(out, "target", " M 31 ", "text")
    _put_token(out, "offset", "lots", "int")  # unreadable: nothing written
    _put_token(out, "date", "2026-10-14", "date")  # sets no field itself
    assert out == {"xbin": 2, "ybin": 1, "gain": 120, "exptime": 300.5, "target": "M 31"}


def test_date_obs_reads_local_time_at_the_site_longitude():
    got = {"date": "2026-10-14", "time": "22-00-00"}
    assert _date_obs(got, 15.0) == datetime(2026, 10, 14, 21, 0, tzinfo=UTC)
    assert _date_obs({**got, "tz": "utc"}, None) == datetime(2026, 10, 14, 22, 0, tzinfo=UTC)
    assert _date_obs(got, None) is None  # local time with no longitude
    assert _date_obs({"date": "2026-02-30", "time": "22-00-00", "tz": "utc"}, None) is None


# ---- sweep and Siril ---------------------------------------------------------------------------------------


def test_tally_counts_each_outcome_and_skips_the_rest():
    r = SweepResult(library="x")
    for a in (Action.QUEUED, Action.QUEUED, Action.MOVED, Action.IGNORED, Action.SKIP):
        _tally(r, a)
    assert (r.queued, r.moved, r.ignored, r.skipped, r.unchanged) == (2, 1, 1, 1, 0)


def test_report_swallows_a_failing_progress_callback():
    seen: list[str] = []
    _report(seen.append, "a")

    def boom(line: str) -> None:
        raise RuntimeError(line)

    _report(boom, "b")  # no exception
    assert seen == ["a"]


# ---- calibration QA ----------------------------------------------------------------------------------------


def stats(median: float, **kw: Any) -> FrameStats:
    base = dict(
        mean=median, mad=1.0, min=0.0, max=1.0, saturated_frac=0.0, zero_rows_frac=0.0, zero_cols_frac=0.0
    )
    base.update(kw)
    return FrameStats(median=median, **base)


def test_flat_checks_warn_on_exposure_and_saturation():
    notes: list[str] = []
    assert _flat_checks(stats(0.05 * 65535, saturated_frac=0.02), "pass", notes) == "warn"
    assert len(notes) == 2
    assert _flat_checks(stats(0.4 * 65535), "pass", []) == "pass"


def test_dark_checks_keep_the_later_unevenness_warning_over_a_leak_reject():
    s = {f"k{i}": stats(500, spots=1, structure=1.0) for i in range(5)}
    s["bad"] = stats(500, spots=40, structure=20.0)
    notes: list[str] = []
    # the order the checks always ran in: the uneven-level warning comes last and its verdict stands
    assert _dark_checks(s["bad"], s, "pass", notes) == "warn"
    assert "light leak. Not used." in notes[0]
    assert _dark_checks(stats(500, spots=40, structure=1.0), s, "pass", []) == "reject"


def test_qa_frame_rejects_truncated_and_bright_darks_outright():
    s = {"a": stats(500), "b": stats(500)}
    assert _qa_frame("dark", stats(500, zero_rows_frac=0.1), s, 500, 1)[0] == "reject"
    verdict, reason = _qa_frame("bias", stats(0.5 * 65535), s, 500, 1)
    assert verdict == "reject" and "bias" in reason
    assert qa_set("dark", s) == {"a": ("pass", ""), "b": ("pass", "")}


# ---- matching and recalibration reasons --------------------------------------------------------------------


def test_within_windows_keeps_open_ends_and_unwindowed_masters():
    a, b, c = (SimpleNamespace(pk=k) for k in "abc")
    windows = {"a": (date(2026, 1, 1), None), "b": (None, date(2025, 1, 1))}
    pool = cast(list[Any], [a, b, c])
    assert _within_windows(pool, windows, date(2026, 5, 1)) == [a, c]
    assert _within_windows(pool, windows, None) == pool
    assert _within_windows(pool, {}, date(2026, 5, 1)) == pool


def test_why_dark_and_flat():
    def fr(**kw: Any) -> Any:
        return SimpleNamespace(
            **{"set_temp_c": None, "ccd_temp_c": None, "night": None, "filter_norm": "Ha", **kw}
        )

    assert _why_dark(fr(set_temp_c=-10.0), fr(set_temp_c=-20.0)) == "a dark at -20 °C instead of -10 °C"
    assert _why_dark(fr(), fr()) == "another dark at the same settings"
    n = date(2026, 10, 10)
    near = fr(night=SimpleNamespace(date=n))
    far = fr(night=SimpleNamespace(date=date(2026, 10, 1)))
    assert _why_flat(far, near, n) == "flats from the same night instead of 9 days away"
    assert _why_flat(near, far, n) == "another flat for the same filter"
    assert _why_flat(fr(), fr(filter_norm="OIII"), None) == "a OIII flat instead of Ha"


# ---- batch calibration -------------------------------------------------------------------------------------


class FakeEngine:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run(self, command: str, **_: Any) -> None:
        self.commands.append(command)


@pytest.mark.parametrize(
    ("dark", "flat", "colour", "rgb", "prefix", "first"),
    [
        (
            Path("d.fit"),
            Path("f.fit"),
            True,
            False,
            "pp_",
            "calibrate light_ -dark=d.fit -flat=f.fit -cc=dark -cfa",
        ),
        (None, Path("f.fit"), True, True, "pp_", "calibrate light_ -flat=f.fit -prefix=pp_"),
        (None, None, True, False, "pp_", "set16bits"),
        (None, None, False, False, "", None),
    ],
)
def test_calibrate_sequence_applies_what_there_is(dark, flat, colour, rgb, prefix, first):
    eng = FakeEngine()
    assert _calibrate_sequence(eng, dark, flat, colour, rgb) == prefix
    if first is None:
        assert eng.commands == []
    else:
        assert eng.commands[0].startswith(first)
    if first == "set16bits":
        assert eng.commands[-1] == "set32bits"


def test_collect_batch_moves_files_copies_links_and_leaves_missing(tmp_path):
    g = tmp_path / "g"
    g.mkdir()
    (g / "pp_light_00001.fit").write_bytes(b"one")
    real = tmp_path / "real.fit"
    real.write_bytes(b"two")
    os.symlink(real, g / "pp_light_00002.fit")
    frames = [SimpleNamespace(pk=i) for i in range(3)]
    dests = [tmp_path / "out" / f"{i}.fit" for i in range(3)]
    group = cast(list[Any], [(frames[i], None, None, dests[i]) for i in range(3)])
    left: list[Any] = []
    _collect_batch(g, "pp_", group, left)
    assert dests[0].read_bytes() == b"one" and not (g / "pp_light_00001.fit").exists()
    assert dests[1].read_bytes() == b"two" and not dests[1].is_symlink()
    assert left == [frames[2]]
