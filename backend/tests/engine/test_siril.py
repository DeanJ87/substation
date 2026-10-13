"""G1: the Siril adapter against the real siril-cli (marked `siril`; run in the worker image)."""

from __future__ import annotations

import pytest

from apps.engine.parse import bgnoise, found_stars, roundness, star_list, stat
from apps.engine.siril import EngineError, Siril

from .synthetic import star_field

pytestmark = pytest.mark.siril


@pytest.fixture
def siril(tmp_path):
    s = Siril(workdir=str(tmp_path))
    s.start()
    yield s
    s.close()


def test_measure_a_star_field(siril, tmp_path):
    star_field(tmp_path / "field.fit", n=150, fwhm=3.0)
    siril.run(f"cd {tmp_path}")
    siril.run("load field")
    r = siril.run("findstar -out=field.lst")
    n, fwhm = found_stars(r.log)
    assert 120 <= n <= 160
    assert fwhm is not None and 2.5 < fwhm < 3.6
    stars = star_list(tmp_path / "field.lst")
    assert len(stars) == n
    assert roundness(stars) > 0.9
    assert bgnoise(siril.run("bgnoise").log) is not None
    st = stat(siril.run("stat").log)
    assert st is not None
    mean, median, sigma = st
    assert 950 < median < 1050


def test_errors_are_raised_and_the_process_survives(siril, tmp_path):
    with pytest.raises(EngineError, match="load"):
        siril.run("load does_not_exist")
    assert not siril.run("notacommand foo", check=False).ok
    assert siril.alive()
    assert siril.run("ping", check=False) is not None


def test_restarts_after_a_crash(siril, tmp_path):
    star_field(tmp_path / "f.fit", n=20)
    siril.proc.kill()
    siril.proc.wait()
    siril.run(f"cd {tmp_path}")  # starts a new process
    assert siril.run("load f").ok
    assert "1.4" in siril.version
