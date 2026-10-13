"""A master never mixes row orders: frames saved bottom-up are turned to match the set before stacking (NGC 7822
flats, 2026-10-13: the same flats in FITS and XISF made a mirrored master)."""

from __future__ import annotations

import numpy as np
from astropy.io import fits

from apps.processing.calibration import one_row_order


def test_frames_in_another_row_order_are_flipped_to_match(tmp_path):
    img = np.arange(12, dtype=np.float32).reshape(3, 4)
    fits.PrimaryHDU(img, header=fits.Header([("ROWORDER", "TOP-DOWN")])).writeto(tmp_path / "raw_00001.fit")
    fits.PrimaryHDU(img[::-1]).writeto(tmp_path / "raw_00002.fit")  # bottom-up: the same frame, other way up
    fits.PrimaryHDU(img, header=fits.Header([("ROWORDER", "TOP-DOWN")])).writeto(tmp_path / "raw_00003.fit")
    assert one_row_order(tmp_path, "raw_") == 1
    fixed = fits.open(tmp_path / "raw_00002.fit")[0]
    assert fixed.header["ROWORDER"] == "TOP-DOWN" and np.array_equal(fixed.data, img)
    assert one_row_order(tmp_path, "raw_") == 0  # once only
