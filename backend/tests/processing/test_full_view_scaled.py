"""A 16-bit camera FITS stored with BZERO (as the Sony A7 III's are) draws at 100%; a view that can't be drawn
says why instead of offering to try again."""

from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits
from django.utils import timezone

from apps.processing.api_masters import look_progress
from apps.processing.previews import full_and_inspector
from substation.tasks.models import Task, TaskStatus


def test_a_bzero_scaled_fits_is_drawn(tmp_path):
    src = tmp_path / "sony.fits"
    fits.PrimaryHDU(np.random.default_rng(1).integers(1000, 4000, (200, 300), dtype=np.uint16)).writeto(src)
    assert "BZERO" in fits.getheader(src)
    full, inspect = tmp_path / "full.jpg", tmp_path / "inspect.jpg"
    full_and_inspector(src, full, inspect, raw=True)
    assert full.stat().st_size > 0 and inspect.stat().st_size > 0


@pytest.mark.django_db
def test_a_failed_view_says_why():
    Task.objects.create(
        name="apps.processing.tasks.full_view",
        queue="process",
        dedupe_key="full:x",
        run_after=timezone.now(),
        enqueued_at=timezone.now(),
        status=TaskStatus.FAILED,
        error="Traceback (most recent call last):\n  ...\nRuntimeError: The capture isn't on disk any more.\n",
    )
    assert look_progress("full:x", "No 100% view yet.") == {
        "failed": True,
        "note": "Couldn't draw the 100% view: The capture isn't on disk any more.",
    }
    assert look_progress("full:y", "No 100% view yet.") == {"note": "No 100% view yet."}
