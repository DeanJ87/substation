"""Annotations (009 amendment 2026-10-12): Siril's catalogues ship with the app and land objects where they are."""

from __future__ import annotations

from apps.processing.annotations import annotate, catalogue
from apps.processing.solving import corners


def test_the_catalogues_ship_with_the_app():
    names = {o["name"] for o in catalogue()}
    # Messier first, so M31 is listed once (not again as NGC224)
    assert {"M31", "NGC7000", "IC1805", "Sh2-190"} <= names and "NGC224" not in names
    assert len(names) > 15000


def test_m31_field_labels_its_companions_where_they_are():
    # a real solve of the owner's M31 (top-down DSLR, displayed as captured), checked by eye 2026-10-12
    f = {
        "ra": 10.68504,
        "dec": 41.26969,
        "rotation": 86.26,
        "fov_w": 4.0841,
        "fov_h": 2.72273,
        "flipped": False,
    }
    tl, tr, br, bl = corners(f, f)
    objs = {o["name"]: o for o in annotate((f["ra"], f["dec"]), f["fov_w"], [bl, br, tr, tl])}
    assert {"M31", "M32", "M110", "NGC206"} <= set(objs)
    assert abs(objs["M31"]["u"] - 0.5) < 0.02 and abs(objs["M31"]["v"] - 0.5) < 0.02
    # M110 sits up and right of the core in this frame, M32 below-left
    assert objs["M110"]["u"] > 0.55 and objs["M110"]["v"] < 0.4
    assert objs["M32"]["u"] < 0.45 and objs["M32"]["v"] > 0.45


def test_a_master_is_oriented_by_its_own_file_not_a_sub(tmp_path):
    # M81 Hα (2026-10-12): the dataset's first sub was a top-down NINA FITS, the master bottom-up; labels flipped
    from types import SimpleNamespace

    import numpy as np
    from astropy.io import fits

    from apps.processing.solving import master_corners

    sol = {
        "ra_deg": 148.9,
        "dec_deg": 69.07,
        "rotation_deg": 3.5,
        "fov_w_deg": 2.7,
        "fov_h_deg": 1.8,
        "flipped": False,
    }
    bottom_up = tmp_path / "bu.fit"
    fits.PrimaryHDU(np.zeros((4, 4), dtype=np.float32)).writeto(bottom_up)
    top_down = tmp_path / "td.fit"
    h = fits.Header()
    h["ROWORDER"] = "TOP-DOWN"
    fits.PrimaryHDU(np.zeros((4, 4), dtype=np.float32), header=h).writeto(top_down)
    a = master_corners(SimpleNamespace(solve=sol, output_path=str(bottom_up)), frame=object())
    b = master_corners(SimpleNamespace(solve=sol, output_path=str(top_down)), frame=object())
    assert a[0] == b[3] and a[3] == b[0]  # top and bottom swap only for a top-down master file
    assert a[0][1] > a[3][1]  # bottom-up master: top-left is north of bottom-left (unflipped, rotation ~0)


def test_labels_through_a_full_wcs_land_on_their_objects():
    # a simple TAN WCS centred on M81: M81 sits at the reference pixel; north is up on the (bottom-up) preview
    from apps.processing.annotations import annotate_wcs

    W, H, scale = 6224, 4168, 1.58 / 3600
    hdr = {
        "NAXIS1": W,
        "NAXIS2": H,
        "CTYPE1": "RA---TAN",
        "CTYPE2": "DEC--TAN",
        "CRVAL1": 148.888221,
        "CRVAL2": 69.065295,
        "CRPIX1": W / 2 + 0.5,
        "CRPIX2": H / 2 + 0.5,
        "CD1_1": -scale,
        "CD1_2": 0.0,
        "CD2_1": 0.0,
        "CD2_2": scale,
    }
    objs = {o["name"]: o for o in annotate_wcs(hdr, top_down=False)}
    assert abs(objs["M81"]["u"] - 0.5) < 0.005 and abs(objs["M81"]["v"] - 0.5) < 0.005
    assert objs["M82"]["v"] < 0.5  # M82 is north of M81: above it on the preview
    # NGC 3077 is east (left, as CD1_1 < 0) and south of M81: lower left, as shot
    assert objs["NGC3077"]["u"] < 0.5 and objs["NGC3077"]["v"] > 0.5
