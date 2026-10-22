"""020-DR-15 against the real siril-cli: the sequence semantics the progressive stacks rely on, then a whole build.

Marked `siril` (run in the worker image). What the build assumes of Siril 1.4:
- `select` / `unselect` take 1-based positions in the sequence, not file numbers (a sub that fails registration
  is left out of r_sub_, so the two differ);
- `stack … -filter-incl` stacks exactly the selected images, and repeated `select` runs add up;
- `-norm=addscale` normalises onto a selected image when the sequence's reference isn't selected, so a channel
  that doesn't hold the registration reference keeps its own levels;
- every registered sub is on the reference's framing, so any subset stacks aligned with any other."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from apps.engine import parse
from apps.engine.siril import Siril

from .synthetic import star_field

pytestmark = pytest.mark.siril

SIZE = 256
SELECTED = re.compile(r"Using selected images filter \((\d+)/(\d+) of the sequence\)")


def _noise(a: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)[40:-40, 40:-40]
    a = a * 65535 if np.nanmedian(a) < 2 else a
    m = np.nanmedian(a)
    return float(1.4826 * np.nanmedian(np.abs(a - m)))


def _level(a: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)[40:-40, 40:-40]
    m = float(np.nanmedian(a))
    return m * 65535 if m < 2 else m


def _offset(a: np.ndarray, b: np.ndarray) -> tuple[int, int]:
    """The integer shift between two images, by phase correlation of their (median-subtracted) centres."""
    a = np.nan_to_num(np.asarray(a, dtype=np.float64)[32:-32, 32:-32])
    b = np.nan_to_num(np.asarray(b, dtype=np.float64)[32:-32, 32:-32])
    a, b = a - np.median(a), b - np.median(b)
    r = np.fft.fft2(a) * np.conj(np.fft.fft2(b))
    c = np.abs(np.fft.ifft2(r / (np.abs(r) + 1e-12)))
    dy, dx = np.unravel_index(int(np.argmax(c)), c.shape)
    h, w = c.shape
    return (int(dy - h if dy > h // 2 else dy), int(dx - w if dx > w // 2 else dx))


@pytest.fixture
def siril(tmp_path):
    s = Siril(workdir=str(tmp_path))
    s.start()
    yield s
    s.close()


def _stack(siril: Siril, runs: list[tuple[int, int]], n: int, out: Path) -> tuple[int, int]:
    """Select `runs` of positions the way the build does and stack with -filter-incl; (stacked, of)."""
    assert siril.run(f"unselect r_sub_ 1 {n}").ok
    for a, b in runs:
        assert siril.run(f"select r_sub_ {a} {b}").ok
    r = siril.run(f"stack r_sub_ rej n -norm=addscale -weight=wfwhm -filter-incl -out={out} -32b", quiet=True)
    got = next(SELECTED.search(line) for line in r.log if SELECTED.search(line))
    assert int(fits.getheader(out.with_suffix(".fit"))["STACKCNT"]) == int(got.group(1))
    return int(got.group(1)), int(got.group(2))


def test_select_takes_positions_and_stacks_only_the_selection(siril, tmp_path):
    """Nine subs: 1–4 one channel (background 1000), 5–9 another (3000); sub 3 has no stars and fails
    registration; the reference is sub 7, in the second channel."""
    from apps.finished.progression import _runs

    for k in range(9):
        path = tmp_path / f"sub_{k + 1:05d}.fit"
        if k == 2:
            noise = np.random.default_rng(5).normal(1000, 10, (SIZE, SIZE))
            fits.PrimaryHDU(noise.astype(np.uint16)).writeto(path)
            continue
        star_field(
            path, n=40, seed=100 + k, field_seed=7, size=SIZE, shift=(3.0 * k, -2.0 * k),
            background=1000 if k < 4 else 3000,
        )  # fmt: skip
    siril.run(f"cd {tmp_path}")
    siril.run("setref sub_ 7")
    r = siril.run("register sub_", timeout=600, quiet=True)
    assert any("1 failed, 8 registered" in line for line in r.log)
    seq = parse.seq_images(tmp_path / "r_sub_.seq")
    assert [im["filenum"] for im in seq] == [1, 2, 4, 5, 6, 7, 8, 9]  # the failed sub leaves a gap
    position = {im["filenum"]: k for k, im in enumerate(seq, start=1)}
    n = len(seq)

    # file numbers are not positions: selecting by file number past the end is refused
    siril.run(f"unselect r_sub_ 1 {n}")
    assert not siril.run("select r_sub_ 9 9", check=False).ok

    first = [position[i] for i in (1, 2, 4)]  # the first channel, the reference not among them
    assert _stack(siril, _runs(first[:2]), n, tmp_path / "a12") == (2, 8)
    assert _stack(siril, _runs(first), n, tmp_path / "a_all") == (3, 8)
    second = [position[i] for i in (5, 6, 7, 8, 9)]
    assert _stack(siril, _runs(second[:2]), n, tmp_path / "b12") == (2, 8)
    assert _stack(siril, _runs(second), n, tmp_path / "b_all") == (5, 8)
    # two runs (a gap in the positions) add up
    assert _stack(siril, [(1, 1), (4, 5)], n, tmp_path / "gap") == (3, 8)

    img = {k: fits.getdata(tmp_path / f"{k}.fit") for k in ("a12", "a_all", "b12", "b_all")}
    ref = fits.getdata(tmp_path / f"r_sub_{7:05d}.fit")
    # each channel keeps its own level: addscale normalised onto one of the selected subs
    assert abs(_level(img["a12"]) - 1000) < 30 and abs(_level(img["a_all"]) - 1000) < 30
    assert abs(_level(img["b12"]) - 3000) < 30 and abs(_level(img["b_all"]) - 3000) < 30
    # every stack is on the reference's framing
    for name, a in img.items():
        assert _offset(a, ref) == (0, 0), name
    # more subs, less noise
    assert _noise(img["b_all"]) < 0.8 * _noise(img["b12"])


# -- the whole build -------------------------------------------------------------------------------------------


@pytest.fixture
def real_siril(settings, tmp_path, monkeypatch):
    """The build's engine is the real one; every command and its log is kept."""
    from apps.engine import siril as engine_mod

    settings.WORK_DIR = tmp_path / "work"
    settings.STATION_ROOT = tmp_path / "station"
    seen: list[tuple[str, list[str]]] = []
    real_run = Siril.run

    def run(self, command, *a, **k):  # noqa: ANN001, ANN202
        r = real_run(self, command, *a, **k)
        seen.append((command, r.log))
        return r

    monkeypatch.setattr(Siril, "run", run)
    engine_mod._close()
    engine_mod._engine = None
    yield seen
    engine_mod._close()
    engine_mod._engine = None


@pytest.mark.django_db
def test_a_real_build_stacks_each_prefix_aligned_with_falling_noise(tmp_path, real_siril):
    from PIL import Image

    from apps.finished import progression as pg
    from apps.finished.models import Progression, ProgressionState
    from tests.unit.progression_data import finished, subs

    fp, project = finished(tmp_path)
    cal = tmp_path / "cal"
    nights = [date(2026, 9, 2) + timedelta(days=i) for i in range(4)]
    ha = subs(project, "Hα", [(d, 2) for d in nights], cal_dir=cal)
    oiii = subs(project, "OIII", [(d, 2) for d in nights], cal_dir=cal, stars=50)
    # the calibrated subs become one star field, pointed a little differently each time
    for k, f in enumerate(ha + oiii):
        star_field(
            Path(f.measurement.calibrated_path), n=60, seed=300 + k, field_seed=11, size=SIZE,
            shift=(1.5 * k, -1.0 * k), background=1000 if f in ha else 600,
        )  # fmt: skip

    assert pg.build_progression.call(fp.pk) == {"result": "done", "checkpoints": 4}
    prog = Progression.objects.get(project=fp)
    assert prog.state == ProgressionState.DONE and prog.mapping == "HOO"

    cmds = [c for c, _log in real_siril]
    assert sum(c.startswith("register ") for c in cmds) == 1
    # every select the build sent was accepted, and each stack took exactly its checkpoint's subs
    for c, log in real_siril:
        if c.startswith(("select ", "unselect ")):
            assert any("Selection update finished" in line for line in log), (c, log)
    stacked = [
        int(next(SELECTED.search(line) for line in log if SELECTED.search(line)).group(1))
        for c, log in real_siril
        if c.startswith("stack ")
    ]
    want = [ck["filters"][c]["subs"] for ck in prog.checkpoints for c in ("Hα", "OIII")]
    assert stacked == want == [2, 2, 4, 4, 6, 6, 8, 8]

    files = [pg.image_path(fp.pk, ck) for ck in prog.checkpoints]
    pics = [np.asarray(Image.open(f).convert("L"), dtype=np.float64) for f in files]
    assert len({p.shape for p in pics}) == 1  # one crop for all
    for p in pics[:-1]:
        assert _offset(p, pics[-1]) == (0, 0)  # the stars stay put
    # noise on the sky the full stack shows as background (an 8-bit MAD is too coarse to tell 6 subs from 8)
    full = pics[-1][40:-40, 40:-40]
    sky = np.abs(full - np.median(full)) < 3 * max(1.0, _noise(pics[-1]))
    noise = [float(np.std(p[40:-40, 40:-40][sky])) for p in pics]
    assert all(a > b for a, b in zip(noise, noise[1:], strict=False)) and noise[0] > 1.4 * noise[-1], noise
    level = [_level(p) for p in pics]
    assert max(level) - min(level) < 12, level
