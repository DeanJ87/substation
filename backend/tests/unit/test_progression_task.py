"""020-DR-15: building cumulative progressive stacks, with Siril replaced by a fake that really averages files."""

from __future__ import annotations

import contextlib
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from apps.finished import progression as pg
from apps.finished.models import Progression, ProgressionState

from .progression_data import finished, subs, write_sub

pytestmark = pytest.mark.django_db
D0 = date(2026, 9, 2)


class Result:
    def __init__(self, ok: bool = True) -> None:
        self.ok, self.log = ok, list[str]()


class FakeSiril:
    """Registration copies each sub as r_sub_NNNNN (they're already aligned); select and unselect keep positions;
    stack averages the selected registered subs into -out."""

    version = "fake"

    def __init__(self) -> None:
        self.cmds: list[str] = []
        self.cwd = Path(".")
        self.selected: set[int] = set()
        self.n = 0
        self.stacked: list[list[int]] = []

    def run(self, cmd: str, timeout: int = 600, check: bool = True, on_line=None, quiet: bool = False):  # noqa: ANN001
        from astropy.io import fits

        self.cmds.append(cmd)
        if cmd.startswith("cd "):
            self.cwd = Path(cmd[3:])
        elif cmd == "register sub_":
            subs_ = sorted(self.cwd.glob("sub_*.fit"))
            for s in subs_:
                (self.cwd / f"r_{s.name}").write_bytes(s.read_bytes())
            nums = [int(s.stem.split("_")[1]) for s in subs_]
            (self.cwd / "r_sub_.seq").write_text("".join(f"I {n} 1\n" for n in nums))
            self.n = len(nums)
            self.selected = set(range(1, self.n + 1))
        elif cmd.startswith(("select ", "unselect ")):
            a, b = map(int, cmd.split()[2:4])
            span = set(range(a, b + 1))
            self.selected = self.selected | span if cmd.startswith("select") else self.selected - span
        elif cmd.startswith("stack "):
            assert "-filter-incl" in cmd
            out = Path(re.search(r"-out=(\S+)", cmd).group(1))  # type: ignore[union-attr]
            pos = sorted(self.selected)
            self.stacked.append(pos)
            data = np.mean([fits.getdata(self.cwd / f"r_sub_{p:05d}.fit") for p in pos], axis=0)
            fits.PrimaryHDU(data.astype(np.float32)).writeto(out.with_suffix(".fit"), overwrite=True)
        return Result()


@pytest.fixture
def siril(monkeypatch, settings, tmp_path):
    settings.WORK_DIR = tmp_path / "work"
    settings.STATION_ROOT = tmp_path / "station"
    from apps.engine import siril as engine_mod

    holder: dict[str, FakeSiril] = {}

    def engine() -> FakeSiril:
        holder["eng"] = holder.get("eng") or FakeSiril()
        return holder["eng"]

    monkeypatch.setattr(engine_mod, "engine", engine)
    monkeypatch.setattr(engine_mod, "heavy_memory", lambda *a, **k: contextlib.nullcontext())
    return holder


def _hoo(tmp_path, nights: int = 4, per: int = 2):
    fp, project = finished(tmp_path)
    cal = tmp_path / "cal"
    n = [D0 + timedelta(days=i) for i in range(nights)]
    ha = subs(project, "Hα", [(d, per) for d in n], cal_dir=cal)
    oiii = subs(project, "OIII", [(d, per) for d in n], cal_dir=cal, stars=50)
    return fp, ha, oiii


def test_a_build_registers_once_and_stacks_each_checkpoints_prefix(tmp_path, siril, monkeypatch):
    from apps.processing import previews

    fp, ha, _oiii = _hoo(tmp_path)
    seen: list[dict] = []
    real = previews.compose_fixed

    def spy(planes, params, rgb):  # noqa: ANN001, ANN202
        seen.append(dict(params))
        return real(planes, params, rgb)

    monkeypatch.setattr(previews, "compose_fixed", spy)
    assert pg.build_progression.call(fp.pk) == {"result": "done", "checkpoints": 4}
    eng = siril["eng"]
    assert sum(c.startswith("register") for c in eng.cmds) == 1
    ref = max(range(len(ha)), key=lambda i: (ha[i].measurement.stars, ha[i].pk)) + 1
    assert f"setref sub_ {ref}" in eng.cmds  # Hα with the most stars, by its position
    # channel by channel in capture order: Hα is 1–8, OIII 9–16; each checkpoint stacks a prefix of each
    assert eng.stacked == [
        [1, 2], [9, 10], [1, 2, 3, 4], [9, 10, 11, 12], [1, 2, 3, 4, 5, 6], [9, 10, 11, 12, 13, 14],
        list(range(1, 9)), list(range(9, 17)),
    ]  # fmt: skip
    stacks = [c for c in eng.cmds if c.startswith("stack")]
    assert " rej n " in stacks[0] and " rej w 3 3 " in stacks[2]  # no rejection from two subs
    assert all(
        "-weight=noise" in c for c in stacks
    )  # never sharpness: it all but drops a sub from a small stack

    prog = Progression.objects.get(project=fp)
    assert prog.state == ProgressionState.DONE and prog.mapping == "HOO" and len(prog.checkpoints) == 4
    files = [pg.image_path(fp.pk, ck) for ck in prog.checkpoints]
    assert all(f.is_file() for f in files)
    assert {f.name for f in pg.cache_dir(fp.pk).iterdir()} == {f.name for f in files}
    assert len(seen) == 4 and all(s == seen[-1] for s in seen)  # the full stack's stretch for every one
    assert not (Path(tmp_path) / "work" / "progression" / f"fp{fp.pk}").exists()

    # the noise falls checkpoint by checkpoint, the signal stays put
    plateau = [np.asarray(Image.open(f).convert("L"), dtype=float)[20:40, 25:55] for f in files]
    noise = [p.std() for p in plateau]
    assert noise == sorted(noise, reverse=True) and noise[0] > 1.5 * noise[-1]
    level = [p.mean() for p in plateau]
    assert max(level) - min(level) < 12


def test_a_second_build_with_the_same_subs_runs_no_siril(tmp_path, siril):
    fp, _ha, _oiii = _hoo(tmp_path, nights=2)
    pg.build_progression.call(fp.pk)
    siril.clear()
    assert pg.build_progression.call(fp.pk)["result"] == "cached"
    assert "eng" not in siril  # Siril never started
    prog = pg.start(fp)
    assert prog.state == ProgressionState.DONE  # nothing queued either


def test_a_sub_pruned_from_the_cache_is_calibrated_again(tmp_path, siril, monkeypatch):
    from apps.processing import tasks

    fp, ha, _oiii = _hoo(tmp_path, nights=2)
    gone = ha[1]
    Path(gone.measurement.calibrated_path).unlink()
    done: list[str] = []

    def batch(items, tmp):  # noqa: ANN001, ANN202
        rng = np.random.default_rng(1)
        for frame, _cm, _src, out in items:
            write_sub(out, rng)
            done.append(frame.pk)
        return []

    monkeypatch.setattr(tasks, "calibrate_batch", batch)
    monkeypatch.setattr(tasks, "source_path", lambda f: Path("/raw.fit"))
    from apps.processing.models import CalibrationMatch

    CalibrationMatch.objects.create(frame=gone, state="matched")
    assert pg.build_progression.call(fp.pk)["result"] == "done"
    assert done == [gone.pk]
    assert len(siril["eng"].stacked[-2]) == 4  # the recalibrated sub is in the full Hα stack
