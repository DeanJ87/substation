"""004-DR-23: a dataset whose subs wander over more than half a field is stacked as a mosaic."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Copy, Frame
from apps.libraries.models import Library
from apps.processing.masters import mosaic_reason
from apps.processing.models import PlateSolve

pytestmark = pytest.mark.django_db


def _frames(tmp_path, centres, name="Light_IC 4605_10.0s_{i}.fit"):
    lib = Library.objects.create(name="cap", mount_path=str(tmp_path))
    now = datetime.now(UTC)
    out = []
    for i, centre in enumerate(centres):
        f = Frame.objects.create(sha256=f"{i:064x}", size_bytes=1, format="fits", first_seen_at=now)
        Copy.objects.create(
            frame=f,
            library=lib,
            rel_path=f"s/{name.format(i=i)}",
            st_dev=1,
            st_ino=i,
            st_size=1,
            st_mtime_ns=1,
            first_seen_at=now,
            last_seen_at=now,
        )
        if centre:
            PlateSolve.objects.create(
                frame=f,
                state="solved",
                ra_deg=centre[0],
                dec_deg=centre[1],
                fov_w_deg=4.0,
                fov_h_deg=2.25,
                rotation_deg=0,
                scale_arcsec=3.7,
            )
        out.append(f)
    return out


def test_a_wandering_field_is_a_mosaic(tmp_path):
    fs = _frames(tmp_path, [(247.2, -26.1), (245.6, -27.1), (246.9, -24.9), (246.3, -26.4)])
    assert mosaic_reason(fs).startswith("Mosaic: the subs' centres spread")


def test_a_dithered_field_is_not(tmp_path):
    fs = _frames(tmp_path, [(83.82, -5.39), (83.83, -5.40), (83.81, -5.38), (83.82, -5.41)])
    assert mosaic_reason(fs) is None


def test_unsolved_seestar_mosaic_subs_by_name(tmp_path):
    fs = _frames(tmp_path, [None] * 4, name="Light_mosaic_IC 4605_10.0s_IRCUT_{i}.fit")
    assert mosaic_reason(fs) == "Mosaic: Seestar mosaic subs"
