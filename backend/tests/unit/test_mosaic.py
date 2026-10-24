"""004-DR-23: a dataset whose subs wander over more than half a field is stacked as a mosaic."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
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
    order: Any = {i: SimpleNamespace(frame_id=f"{i:064x}") for i in (1, 2, 4)}  # none solved on arrival
    solved, unsolved = _solve_each(eng, tmp_path, order, cast(Any, None))
    assert solved == [1] and unsolved == [2, 4]
    assert (
        not (tmp_path / "sub_00001.fit").is_symlink() and (tmp_path / "cache.fit").read_bytes() == b"cached"
    )


def test_a_solution_stored_on_arrival_is_written_not_solved_again(tmp_path, monkeypatch):
    """004-DR-26: a sub solved on arrival keeps its whole solution; the mosaic writes it into its own copy."""
    import numpy as np
    from astropy.io import fits

    from apps.processing import masters
    from apps.processing.masters import _solve_each

    monkeypatch.setattr(masters, "_step", lambda *a, **k: None)
    (f,) = _frames(tmp_path, [(246.5, -26.0)])
    wcs = {
        "NAXIS1": 20,
        "NAXIS2": 10,
        "CTYPE1": "RA---TAN",
        "CTYPE2": "DEC--TAN",
        "CRVAL1": 246.5,
        "CRVAL2": -26.0,
    }
    PlateSolve.objects.filter(frame=f).update(wcs=wcs)
    cache = tmp_path / "cache.fit"
    fits.PrimaryHDU(np.zeros((10, 20), dtype=np.float32)).writeto(cache)
    (tmp_path / "sub_00001.fit").symlink_to(cache)

    class NoSolving:
        def run(self, cmd, **kw):
            raise AssertionError(f"Siril was asked to {cmd}")

    solved, unsolved = _solve_each(
        NoSolving(), tmp_path, cast(Any, {1: SimpleNamespace(frame_id=f.pk)}), cast(Any, None)
    )
    assert solved == [1] and unsolved == []
    sub = tmp_path / "sub_00001.fit"
    assert not sub.is_symlink() and fits.getheader(sub)["CRVAL1"] == 246.5
    assert "CRVAL1" not in fits.getheader(cache)  # the cache is never written to


def test_a_failed_stack_keeps_its_folder_and_a_rerun_of_the_same_subs_takes_it(tmp_path, settings):
    """004-DR-27: a failed or cancelled stack keeps what it finished; a rerun from the same subs carries on."""
    from apps.processing.masters import _adopt, _mark_kept, _release_kept, _save_checkpoint

    settings.WORK_DIR = str(tmp_path)
    old = tmp_path / "integrations" / "ds7_v5"
    old.mkdir(parents=True)
    (old / "r_sub_.seq").write_text("registered")
    _save_checkpoint(
        old, {"master": 64, "done": ["inputs", "registered"], "order": {"1": 1}, "frames": {"1": "a"}}
    )
    assert _mark_kept(old, 64)
    new = tmp_path / "integrations" / "ds7_v6"
    m = SimpleNamespace(pk=65, dataset_id=7)
    assert _adopt(new, cast(Any, m), cast(Any, [SimpleNamespace(frame_id="b")])) is None  # different subs
    ck = _adopt(new, cast(Any, m), cast(Any, [SimpleNamespace(frame_id="a")]))
    assert ck is not None and ck["master"] == 65 and "registered" in ck["done"]
    assert (new / "r_sub_.seq").exists() and not old.exists()
    _save_checkpoint(new, {**ck, "kept": 1.0})  # kept long ago
    _release_kept(tmp_path / "other", older_than=masters_kept_for())
    assert not new.exists()


def masters_kept_for():
    from apps.processing.masters import KEPT_FOR

    return KEPT_FOR


def test_one_stray_sub_does_not_make_a_mosaic(tmp_path):
    """M 42 L, 2026-10-15: one 1 s framing test 2.9° away turned 25 subs into a "mosaic"."""
    centres = [(83.82, -5.39)] * 24 + [(86.51, -6.56)]
    fs = _frames(tmp_path, centres)
    assert mosaic_reason(fs) is None


def test_stack_notes_are_ascii_for_fits():
    from apps.processing.masters import fits_ascii

    out = fits_ascii("Mosaic: the subs' centres spread 2.9° across a 1.8° field · Hα × 3 −1")
    assert out.isascii() and "2.9 deg" in out and "Ha x 3 -1" in out


# 004-DR-31: a combined mosaic places its panels by their plate solutions, not by star matching


class _StitchSiril:
    """Siril for a combined mosaic: plate solves panels without a solution (unless told it can't), lays out the
    canvas from the registered sequence it is given, and stacks to the -out name."""

    def __init__(self, work, seq_text, cant_solve=()):
        self.work, self.seq_text, self.cant_solve = work, seq_text, set(cant_solve)
        self.cmds: list[str] = []
        self.loaded = ""

    def run(self, cmd, timeout=600, check=True, on_line=None, quiet=False):
        import numpy as np
        from astropy.io import fits

        self.cmds.append(cmd)
        ok = True
        if cmd.startswith("load "):
            self.loaded = cmd.split()[1]
        elif cmd.startswith("platesolve"):
            ok = self.loaded not in self.cant_solve
        elif cmd.startswith("save "):
            h = fits.Header({"CTYPE1": "RA---TAN", "CRVAL1": 1.0, "CD1_1": 0.001})
            fits.PrimaryHDU(np.zeros((10, 20), np.float32), h).writeto(self.work / f"{cmd.split()[1]}.fit")
        elif cmd.startswith("seqapplyreg"):
            (self.work / "r_m_.seq").write_text(self.seq_text)
            for n in range(1, 10):
                if (self.work / f"m_{n:05d}.fit").exists():
                    fits.PrimaryHDU(np.ones((10, 20), np.float32)).writeto(self.work / f"r_m_{n:05d}.fit")
        elif cmd.startswith("stack "):
            out = cmd.split("-out=")[1]
            fits.PrimaryHDU(np.ones((12, 30), np.float32)).writeto(self.work / f"{out}.fit")
        return SimpleNamespace(ok=ok, log=["log: done"])


def _panel_file(tmp_path, name, wcs_in_header=False):
    import numpy as np
    from astropy.io import fits

    h = fits.Header({"CTYPE1": "RA---TAN", "CRVAL1": 2.0, "CD1_1": 0.001}) if wcs_in_header else None
    p = tmp_path / "masters" / f"{name}.fit"
    p.parent.mkdir(exist_ok=True)
    fits.PrimaryHDU(np.full((10, 20), 5, np.float32), h).writeto(p)
    return p


_WCS = {"NAXIS1": 20, "NAXIS2": 10, "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN", "CRVAL1": 83.8, "CRVAL2": -5.4,
        "CD1_1": 0.001, "CD2_2": 0.001, "ROWORDER": "BOTTOM-UP"}  # fmt: skip

# three panels in a row; the third shares no pixels with the first two (a gap)
_SEQ3 = """S 'r_m_' 1 3 1 5 -1 6 1 0 0
L 1
I 1 1 20,10
I 2 1 20,10
I 3 1 20,10
R0 0 0 0 0 0 0 H 1 0 0 0 1 0 0 0 1
R0 0 0 0 0 0 0 H 1 0 15 0 1 2 0 0 1
R0 0 0 0 0 0 0 H 1 0 60 0 1 4 0 0 1
"""


def test_a_mosaic_is_placed_by_plate_solution_with_the_stored_wcs(tmp_path):
    """Six-panel Heart, 2026-10-24: outer panels share no stars with the reference, so star matching failed. Each
    panel's copy gets its master's stored solution; seqplatesolve + framing max lay out the canvas; no star
    registration; the masters' own files are never written to; every filter is the same size."""
    from astropy.io import fits

    from apps.processing.combine import Panel, _mosaic_all

    work = tmp_path / "work"
    a, b, c = (_panel_file(tmp_path, n) for n in ("p1", "p2", "p3"))
    solve = {"ra_deg": 83.8, "dec_deg": -5.4, "wcs": _WCS}
    p1, p2, p3 = (Panel(i, f"Rig · Hα · Panel {i}", f, solve) for i, f in ((1, a), (2, b), (3, c)))
    eng = _StitchSiril(work, _SEQ3)
    out = _mosaic_all(eng, {10: [p1, p2, p3], 11: [p1]}, p1, work)
    assert not any(cmd.startswith(("register", "platesolve", "convert")) for cmd in eng.cmds)
    assert eng.cmds[:4] == [f"cd {work}", "setref m_ 1", "seqplatesolve m_", "seqapplyreg m_ -framing=max"]
    for n in (1, 2, 3):  # the stored solution, written into the mosaic's own copies
        assert fits.getheader(work / f"m_{n:05d}.fit")["CRVAL1"] == 83.8
    assert "CRVAL1" not in fits.getheader(a)  # the master itself is untouched
    assert out[10].path is not None and out[11].path is not None and out[10].left_out == {}
    assert fits.getdata(out[10].path).shape == fits.getdata(out[11].path).shape == (14, 80)
    assert "Rig · Hα · Panel 3 doesn't overlap" in out[10].notes[0]
    assert out[11].notes == []


def test_a_panel_without_a_stored_solution_is_solved_or_named_with_why(tmp_path):
    from apps.processing.combine import Panel, _mosaic_all

    work = tmp_path / "work"
    a, b, c = (_panel_file(tmp_path, n) for n in ("p1", "p2", "p3"))
    d = _panel_file(tmp_path, "p4", wcs_in_header=True)  # already carries a solution: used as it is
    p1 = Panel(1, "Panel 1", a, {"ra_deg": 83.8, "dec_deg": -5.4, "wcs": _WCS})
    p2 = Panel(2, "Panel 2", b, {"ra_deg": 84.1, "dec_deg": -5.0})  # summary solve only: solved here
    p3 = Panel(3, "Panel 3", c, {"failed": True})
    p4 = Panel(4, "Panel 4", d, {})
    eng = _StitchSiril(work, _SEQ3, cant_solve={"panel_00003"})
    out = _mosaic_all(eng, {10: [p1, p2, p3, p4]}, p1, work)
    assert "platesolve 84.10000,-5.00000 -force -downscale -order=3" in eng.cmds
    assert sum(cmd.startswith("platesolve") for cmd in eng.cmds) == 2  # panels 2 and 3; 1 and 4 had solutions
    assert out[10].left_out == {3: "its master couldn't be plate solved, so there is nothing to place it by"}
    assert out[10].path is not None


def test_a_filter_with_no_placeable_panel_fails_naming_them(tmp_path, monkeypatch):
    from apps.processing import combine
    from apps.processing.combine import Panel, Stitched, _mosaic_all, _place_mosaic

    work = tmp_path / "work"
    a = _panel_file(tmp_path, "p1")
    p1 = Panel(1, "Panel 1", a, {})
    out = _mosaic_all(_StitchSiril(work, _SEQ3, cant_solve={"panel_00001"}), {10: [p1]}, p1, work)
    assert out[10].path is None and out[10].left_out == {
        1: "it has no plate solution and Siril couldn't solve it"
    }
    updates = {}

    class Rows:
        def filter(self, **kw):
            return SimpleNamespace(update=lambda **u: updates.update(u))

    monkeypatch.setattr(combine.CombinedMaster, "objects", Rows())
    cm = SimpleNamespace(pk=10, filter_norm="Hα", inputs=[{"master": 1, "label": "Panel 1"}])
    with pytest.raises(RuntimeError) as err:
        _place_mosaic(cast(Any, cm), {10: out[10]}, tmp_path, 1)
    assert str(err.value) == (
        "Couldn't stitch the Hα mosaic: none of its panels has a plate solution to place it by. "
        "Panel 1: it has no plate solution and Siril couldn't solve it."
    )
    assert updates["inputs"] == [{"master": 1, "label": "Panel 1", "registered": False}]
    assert isinstance(out[10], Stitched)
