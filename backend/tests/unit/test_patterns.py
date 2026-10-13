"""T068: the path pattern grammar (contracts/path-patterns.md)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.ingest.patterns import PatternError, compile_pattern, match, subject

NINA = "{date}_{time}_{filter}_{temp}_{exposure}s_{seq}"


def test_nina_default_filename():
    c = compile_pattern(NINA, "filename")
    got = match(c, "2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf", site_lon=-1.66)
    assert got is not None
    assert got["filter"] == "Halpha" and got["ccd_temp"] == -20.0 and got["exptime"] == 600.0
    # local 20:05:02 at 1.66° W is 20:11:40 UTC (mean solar time)
    assert abs((got["date_obs"] - datetime(2026, 9, 28, 20, 11, 40, tzinfo=UTC)).total_seconds()) < 1
    assert "seq" not in got


def test_bad_prefix_is_stripped_and_extensions_dropped():
    c = compile_pattern(NINA, "filename")
    assert (
        subject("x/BAD_2026-09-28_20-05-02_Ha_-20.00_600.00s_0027.xisf", "filename")
        == "2026-09-28_20-05-02_Ha_-20.00_600.00s_0027"
    )
    assert subject("a.fits.fz", "filename") == "a"
    got = match(c, "BAD_2026-09-28_20-05-02_Ha_-20.00_600.00s_0027.fits", site_lon=0.0)
    assert got and got["filter"] == "Ha" and got["date_obs"] == datetime(2026, 9, 28, 20, 5, 2, tzinfo=UTC)


def test_folder_layout_and_double_star():
    c = compile_pattern("{target}/{date}/{type}/", "folder")
    got = match(c, "NGC 7000/2026-09-28/LIGHT/a.xisf")
    assert got == {"target": "NGC 7000", "frame_type": "light"}
    assert match(c, "deep/NGC 7000/2026-09-28/LIGHT/a.xisf") is None  # anchored
    c2 = compile_pattern("**/{target}/{date}/{type}/", "folder")
    assert match(c2, "deep/er/NGC 7000/2026-09-28/LIGHT/a.xisf") == {
        "target": "NGC 7000",
        "frame_type": "light",
    }
    assert match(c2, "NGC 7000/2026-09-28/LIGHT/a.xisf") == {"target": "NGC 7000", "frame_type": "light"}


def test_masters_layouts():
    c = compile_pattern("Masters/{camera}/Darks/{settemp}c/", "folder")
    assert match(c, "Masters/ATR2600M/Darks/-10c/masterDark.xisf") == {
        "camera": "ATR2600M",
        "set_temp": -10.0,
    }
    f = compile_pattern("MasterDark_{camera}_{settemp}c_{exposure}s", "filename")
    assert match(f, "MasterDark_ATR2600M_-20c_600s.xisf") == {
        "camera": "ATR2600M",
        "set_temp": -20.0,
        "exptime": 600.0,
    }


def test_typed_tokens_and_overrides():
    c = compile_pattern("{object}_{bin}_g{gain}_o{offset:d}_{exposure:f}", "filename")
    got = match(c, "NGC 7000 Panel 3_2x2_g120_o30_300.5.fits")
    assert got == {
        "object": "NGC 7000 Panel 3",
        "xbin": 2,
        "ybin": 2,
        "gain": 120,
        "offset": 30,
        "exptime": 300.5,
    }
    assert match(compile_pattern("{bin}", "filename"), "1.fits") == {"xbin": 1, "ybin": 1}
    assert match(c, "NGC 7000_2x2_gHIGH_o30_300.fits") is None  # gain must be a number


def test_skip_token_and_utc():
    c = compile_pattern("{*}_{date}{time}{tz}_{filter}", "filename")
    got = match(c, "anything here_20260928200502utc_OIII.fit")
    assert got == {"filter": "OIII", "date_obs": datetime(2026, 9, 28, 20, 5, 2, tzinfo=UTC)}


def test_local_time_without_longitude_gives_no_time():
    got = match(compile_pattern("{date}_{time}_{filter}", "filename"), "2026-09-28_20-05-02_L.fits")
    assert got == {"filter": "L"}


def test_fields_reported():
    assert compile_pattern("{object}/{date}/", "folder").fields() == {"object", "target", "panel"}
    assert "date_obs" in compile_pattern(NINA, "filename").fields()


@pytest.mark.parametrize(
    ("pattern", "kind", "message"),
    [
        ("", "filename", "empty"),
        ("{colour}", "filename", "isn't a field"),
        ("{filter}_{filter}", "filename", "appears twice"),
        ("{filter", "filename", "unmatched brace"),
        ("a/{filter}", "filename", "can't contain"),
        ("x**/{filter}/", "folder", "whole folder name"),
        ("{gain:x}", "filename", "isn't a type"),
        ("plain", "filename", "doesn't capture"),
    ],
)
def test_errors_are_plain_english(pattern, kind, message):
    with pytest.raises(PatternError, match=message):
        compile_pattern(pattern, kind)
