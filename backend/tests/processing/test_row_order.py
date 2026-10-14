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


def test_a_linked_frame_is_replaced_never_written_through(tmp_path):
    """Siril links a FITS it only converts. Turning it must not touch the original it points to (a library file)."""
    import os

    img = np.arange(12, dtype=np.float32).reshape(3, 4)
    library = tmp_path / "library"
    library.mkdir()
    original = library / "light.fits"
    fits.PrimaryHDU(img[::-1]).writeto(original)  # bottom-up
    before = original.read_bytes()
    work = tmp_path / "work"
    work.mkdir()
    fits.PrimaryHDU(img, header=fits.Header([("ROWORDER", "TOP-DOWN")])).writeto(work / "raw_00001.fit")
    os.symlink(original, work / "raw_00002.fit")
    assert one_row_order(work, "raw_") == 1
    assert original.read_bytes() == before  # the library file is untouched
    assert not (work / "raw_00002.fit").is_symlink()


def test_the_cache_never_prunes_what_a_running_stack_just_touched(tmp_path, settings):
    import os
    import time

    from apps.processing.tasks import prune_calibrated

    settings.WORK_DIR = tmp_path
    root = tmp_path / "calibrated" / "ds1"
    root.mkdir(parents=True)
    old, fresh = root / "old.fit", root / "fresh.fit"
    old.write_bytes(b"x" * 100)
    fresh.write_bytes(b"x" * 100)
    os.utime(old, (time.time() - 5 * 3600,) * 2)
    assert prune_calibrated(budget_bytes=50) == 1  # over budget: only the old one goes
    assert fresh.exists() and not old.exists()
