"""A dataset left on another camera's rig (a rig merge later undone) is put back on its own rig."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Dataset, Frame, FrameStatus, FrameType, HeaderSnapshot, Rig
from apps.catalogue.services.library import ensure_rig

pytestmark = pytest.mark.django_db
T = datetime(2025, 11, 25, 22, tzinfo=UTC)


def test_a_sony_dataset_on_the_mono_rig_moves_to_the_sony_rig():
    mono = Rig.objects.create(
        key="Askar 71F|ATR2600M|490.0", name="Askar + ATR", camera="ATR2600M", telescope="Askar 71F"
    )
    sony = Rig.objects.create(
        key="Askar 71F|Sony A7 III|", name="Askar + Sony", camera="Sony A7 III", telescope="Askar 71F"
    )
    d = Dataset.objects.create(
        group_key="k", target="NGC 7635", camera="Sony A7 III", telescope="Askar 71F", rig=mono
    )
    Frame.objects.create(
        sha256="a" * 64,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
        camera="Sony A7 III",
        telescope="Askar 71F",
        dataset=d,
        date_obs_utc=T,
    )
    assert ensure_rig(d) == sony
    assert Dataset.objects.get(pk=d.pk).rig == sony
    mine = Dataset.objects.create(
        group_key="m", target="M 42", camera="ATR2600M", telescope="Askar 71F", rig=mono
    )
    assert ensure_rig(mine) == mono  # its own rig stays


def test_a_focal_length_rounded_differently_is_the_same_rig():
    sony = Rig.objects.create(
        key="Askar 71F|Sony A7 III|489.91642",
        name="Askar + Sony",
        camera="Sony A7 III",
        telescope="Askar 71F",
        focal_mm=489.91642,
    )
    d = Dataset.objects.create(group_key="k2", target="NGC 7635", camera="Sony A7 III", telescope="Askar 71F")
    f = Frame.objects.create(
        sha256="b" * 64,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
        camera="Sony A7 III",
        telescope="Askar 71F",
        dataset=d,
        date_obs_utc=T,
    )
    HeaderSnapshot.objects.create(frame=f, geometry="6000:4000", keywords={"FOCALLEN": {"value": 490.0}})
    assert ensure_rig(d) == sony and Rig.objects.count() == 1


def test_a_frame_whose_dataset_was_removed_regroups_without_failing():
    """A long re-read holds frames loaded earlier; their dataset may be removed meanwhile (2026-10-13)."""
    from apps.catalogue.services.grouping import assign_dataset

    d = Dataset.objects.create(group_key="gone", target="M 1")
    f = Frame.objects.create(
        sha256="c" * 64,
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
        dataset=d,
    )
    stale = Frame.objects.get(pk=f.pk)  # loaded before the dataset goes
    Dataset.objects.filter(pk=d.pk).delete()
    old, _new = assign_dataset(stale)
    assert old is None


def test_a_built_master_takes_its_camera_from_its_header(settings, tmp_path):
    """Sony flats built while filed under another rig stayed labelled with it: the header wins now."""
    import numpy as np
    from astropy.io import fits

    from apps.catalogue.models import CalibrationSet
    from apps.processing.calibration import _register
    from apps.processing.models import BuiltMaster

    settings.MASTERS_DIR = tmp_path
    cs = CalibrationSet.objects.create(
        type=FrameType.FLAT,
        camera="ATR2600M",
        filter_norm="OSC",
        exptime_s=3.2,
        frame_count=3,
        session_start_utc=T,
        session_end_utc=T,
    )
    bm = BuiltMaster.objects.create(calibration_set=cs, state="done", method="", report={})
    out = tmp_path / "master_flat.fit"
    hdr = fits.Header([("INSTRUME", "Sony A7 III"), ("TELESCOP", "Askar 71F")])
    fits.PrimaryHDU(np.ones((4, 6), dtype=np.float32), header=hdr).writeto(out)
    f = _register(bm, cs, out)
    f.refresh_from_db()
    assert f.camera == "Sony A7 III" and f.telescope == "Askar 71F"
