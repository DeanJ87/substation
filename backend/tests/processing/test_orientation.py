"""A master is applied in the light's row order (M81 Hα, Feb 2026: a NINA top-down FITS light calibrated with a
WBPP XISF flat that Siril had written bottom-up, so the OAG shadow and a dust mote landed on the wrong side)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.io import fits

from apps.processing.tasks import _top_down, oriented_master


def _write(p: Path, data: np.ndarray, roworder: str | None) -> Path:
    h = fits.Header()
    if roworder:
        h["ROWORDER"] = roworder
    fits.PrimaryHDU(data=data, header=h).writeto(p)
    return p


def test_a_master_in_the_other_row_order_is_flipped_to_match(tmp_path: Path):
    grad = np.arange(12, dtype=np.float32).reshape(4, 3)  # row 0 differs from the last row
    master = _write(tmp_path / "flat.fit", grad, None)  # Siril's default: bottom-up
    flipped = oriented_master(master, top_down=True)
    assert flipped != master and _top_down(flipped)
    assert np.array_equal(fits.getdata(flipped), np.flipud(grad))
    assert oriented_master(master, top_down=True) == flipped  # cached
    assert oriented_master(master, top_down=False) == master  # already matching: untouched


def test_colour_planes_flip_their_rows_not_their_channels(tmp_path: Path):
    rgb = np.arange(3 * 4 * 2, dtype=np.float32).reshape(3, 4, 2)
    master = _write(tmp_path / "flat_rgb.fit", rgb, "TOP-DOWN")
    out = oriented_master(master, top_down=False)
    assert np.array_equal(fits.getdata(out), rgb[:, ::-1, :])
