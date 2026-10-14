"""004-DR-23: a dataset whose subs wander over more than half a field is stacked as a mosaic."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

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


def test_a_sub_that_crashes_siril_costs_only_itself(tmp_path, monkeypatch):
    """IC 4605, 2026-10-14: a segfault on one sub took the whole mosaic stack down. Each sub is solved on its own."""
    from apps.engine.siril import EngineDied
    from apps.processing import masters
    from apps.processing.masters import _solve_each

    monkeypatch.setattr(masters, "_step", lambda *a, **k: None)
    for i in (1, 2, 4):
        (tmp_path / f"sub_{i:05d}.fit").symlink_to(tmp_path / "cache.fit")
    (tmp_path / "cache.fit").write_bytes(b"cached")

    class Result:
        def __init__(self, ok):
            self.ok = ok

    class FakeSiril:
        loaded = ""
        saved: list[str] = []

        def run(self, cmd, timeout=600, check=True, on_line=None, quiet=False):
            if cmd.startswith("load "):
                self.loaded = cmd.split()[1]
            if cmd.startswith("platesolve"):
                if self.loaded == "sub_00002":
                    raise EngineDied(cmd, [], "Siril stopped (exit -11)")
                return Result(self.loaded != "sub_00004")
            if cmd.startswith("save "):
                self.saved.append(cmd.split()[1])
                (tmp_path / f"{cmd.split()[1]}.fit").write_bytes(b"solved")
            return Result(True)

    eng = FakeSiril()
    order: Any = {1: None, 2: None, 4: None}  # only the sub numbers matter here
    solved, unsolved = _solve_each(eng, tmp_path, order, cast(Any, None))
    assert solved == [1] and unsolved == [2, 4]
    assert (
        not (tmp_path / "sub_00001.fit").is_symlink() and (tmp_path / "cache.fit").read_bytes() == b"cached"
    )
