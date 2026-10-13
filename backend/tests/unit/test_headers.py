"""T037: header readers against the real-header fixtures; pixel data must never be read."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.ingest.headers import is_image_name, read_header

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "headers"
LIGHT = FIX / "capture/2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf"


@pytest.fixture(autouse=True)
def no_pixel_reads(monkeypatch):
    import numpy as np
    import xisf
    from astropy.io.fits.hdu.base import _BaseHDU

    def boom(*a, **k):
        raise AssertionError("pixel data was read")

    monkeypatch.setattr(xisf.XISF, "read_image", boom)
    monkeypatch.setattr(np, "fromfile", boom)
    monkeypatch.setattr(_BaseHDU, "data", property(boom), raising=False)


def test_nina_light_xisf():
    r = read_header(LIGHT)
    assert r.ok and r.format == "xisf" and len(r.images) == 1
    img = r.primary()
    assert img.geometry == (6224, 4168, 1)
    assert img.sample_format == "UInt16"
    assert img.get("IMAGETYP") == "LIGHT"
    assert img.get("OBJECT") == "NGC 7000 Panel 2"
    assert img.get("FILTER") == "Halpha"
    assert img.get("EXPTIME") == 600.0
    assert img.get("GAIN") == 120
    assert isinstance(img.get("SITELONG"), float)
    assert img.keywords["DATE-OBS"].comment == "Time of observation (UTC)"
    assert r.file_properties["XISF:CreatorApplication"].startswith("N.I.N.A.")


def test_wbpp_master_three_images_integration_first():
    r = read_header(FIX / "masters/Darks/-20c/MasterDark_ATR2600M_-20c_600s.xisf")
    assert r.ok
    assert [i.image_id for i in r.images] == ["integration", "rejection_low", "rejection_high"]
    assert r.integration_index() == 0
    assert r.primary().get("IMAGETYP") == "Master Dark"
    assert r.primary().get("GAIN") is None  # WBPP masters carry no gain (spike phase 1)


def test_stripped_light_has_no_filter_or_exposure():
    r = read_header(FIX / "stripped/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf")
    assert r.ok
    img = r.primary()
    assert img.get("FILTER") is None and img.get("EXPTIME", "EXPOSURE") is None
    assert img.get("OBJECT") == "NGC 7000 Panel 2"


def test_fits_and_compressed_fits():
    plain = read_header(FIX / "capture/fits/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.fits")
    fz = read_header(FIX / "capture/fits/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.fits.fz")
    assert plain.ok and plain.format == "fits"
    assert fz.ok and fz.format == "fits_compressed"
    for r in (plain, fz):
        assert r.primary().get("FILTER") == "Halpha"
        assert r.primary().get("EXPTIME") == 600.0
        assert r.primary().geometry == (2, 2)


def test_truncated_dark_flat_header_still_reads():
    r = read_header(FIX / "capture/2026-09-28/DARK/2026-09-29_05-11-47_Halpha_-19.90_2.00s_0045.xisf")
    assert r.ok and r.primary().get("IMAGETYP") == "DARK" and r.primary().get("OBJECT") == "FlatWizard"


def test_garbage_returns_error_not_exception(tmp_path):
    bad = tmp_path / "broken.xisf"
    bad.write_bytes(b"not an xisf file at all")
    r = read_header(bad)
    assert not r.ok and "XISF" in r.error
    badf = tmp_path / "broken.fits"
    badf.write_bytes(b"\x00" * 100)
    assert not read_header(badf).ok


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.xisf", True),
        ("A.XISF", True),
        ("a.fits", True),
        ("a.fit", True),
        ("a.fts", True),
        ("a.fits.fz", True),
        ("a.fz", True),
        ("._a.xisf", False),
        (".DS_Store", False),
        ("a.jpg", False),
        ("notes.txt", False),
        ("BAD_a.xisf", True),
    ],
)
def test_is_image_name(name, expected):
    assert is_image_name(name) is expected


def test_colour_sub_without_filter_is_inferred_osc():
    from apps.ingest.fields import extract
    from apps.ingest.headers import ImageHeader, Keyword

    img = ImageHeader(index=0, image_id="", geometry=(6000, 4000), sample_format="", image_type="")
    img.keywords = {
        "IMAGETYP": Keyword("Light Frame", ""),
        "BAYERPAT": Keyword("RGGB", ""),
        "ISOSPEED": Keyword(800, ""),
        "EXPTIME": Keyword(180.0, ""),
    }
    out = extract(img)
    assert out["filter"].value == "OSC" and out["filter"].source_detail.startswith("inferred")
    assert out["gain"].value == 800 and out["gain"].source_detail == "ISOSPEED"
    mono = ImageHeader(index=0, image_id="", geometry=(6224, 4168), sample_format="", image_type="")
    mono.keywords = {"IMAGETYP": Keyword("LIGHT", "")}
    assert "filter" not in extract(mono)
