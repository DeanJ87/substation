"""Spec 010: the finishing chain builds the documented command lines, and skips a tool that isn't installed
rather than failing the master."""

from __future__ import annotations

import stat
from pathlib import Path

from apps.processing.config import DEFAULTS
from apps.processing.postprocess import command, run_chain


def test_command_lines_match_the_tools_documented_flags(tmp_path: Path):
    src, out = tmp_path / "m.fits", tmp_path / "s" / "m_background.fits"
    bg = command(
        {"step": "background", "correction": "Division", "smoothing": 0.2}, "graxpert", "gx", src, out, True
    )
    assert bg[:3] == ["gx", str(src), "-cli"] and "-cmd" in bg and "background-extraction" in bg
    assert bg[bg.index("-correction") + 1] == "Division" and bg[bg.index("-output") + 1] == str(
        out.with_suffix("")
    )
    bxt = command({"step": "deconvolve", "sharpen_stars": 0.3}, "rc_astro", "rc", src, out, False)
    assert bxt[:3] == ["rc", "bxt", str(src)] and "--engine" in bxt and bxt[bxt.index("--depth") + 1] == "32F"
    assert bxt[bxt.index("--sharpen-stars") + 1] == "0.3"
    dn = command({"step": "denoise", "amount": 0.4}, "graxpert", "gx", src, out, True)
    assert "denoising" in dn and dn[dn.index("-strength") + 1] == "0.4"


def test_missing_tools_are_skipped_with_a_reason(tmp_path: Path):
    master = tmp_path / "master.fits"
    master.write_bytes(b"")
    cfg = {**DEFAULTS["post"], "graxpert": "/nope/gx", "rc_astro": "/nope/rc"}
    stages = run_chain(master, cfg, tmp_path / "post")
    assert [s["state"] for s in stages] == ["skipped", "skipped", "skipped"]  # starless is off by default
    assert "isn't installed" in stages[0]["reason"] and master.exists()


def test_a_tool_runs_on_the_previous_stage(tmp_path: Path):
    # a stand-in GraXpert that copies its input to `-output`.fits
    gx = tmp_path / "gx"
    gx.write_text(
        '#!/bin/sh\nsrc="$1"; while [ "$1" ]; do [ "$1" = "-output" ] && out="$2"; shift; done; cp "$src" "$out.fits"\n'
    )
    gx.chmod(gx.stat().st_mode | stat.S_IEXEC)
    master = tmp_path / "master.fits"
    master.write_bytes(b"SIMPLE")
    cfg = {**DEFAULTS["post"], "graxpert": str(gx), "rc_astro": "/nope/rc"}
    stages = run_chain(master, cfg, tmp_path / "post")
    assert stages[0]["state"] == "done" and Path(stages[0]["path"]).read_bytes() == b"SIMPLE"
    assert stages[1]["state"] == "skipped"  # BlurXTerminator isn't here
    assert (
        stages[2]["state"] == "done" and stages[2]["input"] == Path(stages[0]["path"]).name
    )  # GraXpert denoise
    assert master.read_bytes() == b"SIMPLE"  # the master is never touched


def test_a_master_this_worker_cant_see_is_a_plain_reason(tmp_path: Path):
    stages = run_chain(tmp_path / "elsewhere" / "master.fits", DEFAULTS["post"], tmp_path / "post")
    assert stages[0]["state"] == "failed" and "isn't visible to this worker" in stages[0]["reason"]


def test_an_unreadable_master_is_a_plain_reason(tmp_path: Path):
    import os

    if os.getuid() == 0:  # root reads anything
        return
    master = tmp_path / "master.fits"
    master.write_bytes(b"SIMPLE")
    master.chmod(0)
    try:
        stages = run_chain(master, DEFAULTS["post"], tmp_path / "post")
        assert stages[0]["state"] == "failed" and "can't read the master" in stages[0]["reason"]
    finally:
        master.chmod(0o644)


def test_a_read_only_output_folder_is_a_plain_reason(tmp_path: Path):
    import os

    if os.getuid() == 0:
        return
    master = tmp_path / "master.fits"
    master.write_bytes(b"SIMPLE")
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o555)
    try:
        stages = run_chain(master, DEFAULTS["post"], ro / "post")
        assert stages[0]["state"] == "failed" and "can't write beside the master" in stages[0]["reason"]
    finally:
        ro.chmod(0o755)


def test_a_tool_that_cant_execute_fails_its_step_not_the_chain(tmp_path: Path):
    gx = tmp_path / "gx"
    gx.write_text("not a program")  # present but not executable
    master = tmp_path / "master.fits"
    master.write_bytes(b"SIMPLE")
    cfg = {**DEFAULTS["post"], "graxpert": str(gx), "rc_astro": "/nope/rc"}
    stages = run_chain(master, cfg, tmp_path / "post")
    assert stages[0]["state"] == "failed" and "Couldn't start graxpert" in stages[0]["reason"]
    assert len(stages) == 3 and master.read_bytes() == b"SIMPLE"


def test_a_tool_that_writes_nothing_fails_its_step(tmp_path: Path):
    gx = tmp_path / "gx"
    gx.write_text("#!/bin/sh\necho 'model not downloaded' >&2\nexit 0\n")
    gx.chmod(gx.stat().st_mode | stat.S_IEXEC)
    master = tmp_path / "master.fits"
    master.write_bytes(b"SIMPLE")
    stages = run_chain(
        master, {**DEFAULTS["post"], "graxpert": str(gx), "rc_astro": "/nope/rc"}, tmp_path / "p"
    )
    assert stages[0]["state"] == "failed" and "model not downloaded" in stages[0]["reason"]


def test_an_unlicensed_rc_astro_is_not_ready_and_graxpert_denoises(tmp_path: Path):
    from apps.processing import postprocess

    rc = tmp_path / "rc-astro"
    rc.write_text("#!/bin/sh\necho 'BlurXTerminator: A license is required to use this software'\n")
    rc.chmod(rc.stat().st_mode | stat.S_IEXEC)
    gx = tmp_path / "gx"
    gx.write_text(
        '#!/bin/sh\nsrc="$1"; while [ "$1" ]; do [ "$1" = "-output" ] && out="$2"; shift; done; cp "$src" "$out.fits"\n'
    )
    gx.chmod(gx.stat().st_mode | stat.S_IEXEC)
    postprocess._licensed.clear()
    ready = postprocess.readiness({"graxpert": str(gx), "rc_astro": str(rc)})
    assert not ready["rc_astro"]["ready"] and "isn't activated" in ready["rc_astro"]["reason"]
    master = tmp_path / "master.fits"
    master.write_bytes(b"SIMPLE")
    stages = run_chain(
        master, {**DEFAULTS["post"], "graxpert": str(gx), "rc_astro": str(rc)}, tmp_path / "post"
    )
    assert [s["state"] for s in stages] == ["done", "skipped", "done"]
    assert "isn't activated" in stages[1]["reason"] and stages[2]["tool"] == "graxpert"


def test_activating_rc_astro_from_the_web_records_what_it_said(tmp_path: Path, db):
    from apps.libraries.models import InstallationSettings
    from apps.processing import postprocess

    rc = tmp_path / "rc-astro"
    rc.write_text(
        '#!/bin/sh\nif [ "$1" = license ]; then printf -- "- BlurXTerminator: Activated (permanent)\\n'
        '- NoiseXTerminator: Activated (permanent)\\n"; touch "$(dirname "$0")/ok"; exit 0; fi\n'
        '[ -f "$(dirname "$0")/ok" ] || echo "A license is required to use this software"\n'
    )
    rc.chmod(rc.stat().st_mode | stat.S_IEXEC)
    s = InstallationSettings.load()
    s.processing = {"post": {"rc_astro": str(rc), "graxpert": "/nope"}}
    s.save()
    postprocess._licensed.clear()
    assert postprocess.activate_rc_astro.call("nope")["note"].startswith("That doesn't look like")
    r = postprocess.activate_rc_astro.call("VGCP-JAYM")
    assert r["rc_astro"] and "BlurXTerminator" in r["note"]
    st = InstallationSettings.load().processing["post_tools"]
    assert st["rc_astro"]["ready"] and not st["graxpert"]["ready"]


def test_registration_edges_are_trimmed_before_the_tools(tmp_path: Path):
    import numpy as np
    from astropy.io import fits

    from apps.processing.postprocess import edge_box, trim_edges

    a = np.full((100, 150), 500.0, dtype=np.float32)
    a[:6, :] = 0  # a night that didn't reach the top
    a[:, 140:] = 0  # nor the right
    a[90:, :20] = 0  # a ragged corner
    box0 = edge_box(a)
    assert box0 is not None
    t, b, lft, r = box0
    assert t >= 6 and r <= 140 and (b <= 90 or lft >= 20)
    assert edge_box(np.full((50, 50), 1.0)) is None
    src = tmp_path / "m.fits"
    fits.PrimaryHDU(a).writeto(src)
    box = trim_edges(src, tmp_path / "t.fits")
    t = fits.getdata(tmp_path / "t.fits")
    assert box is not None and (t > 0).mean() > 0.97 and fits.getdata(src).shape == (100, 150)
