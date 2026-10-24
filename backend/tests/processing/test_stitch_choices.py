"""2026-10-24 amendments: a stitched master's post-processing shows on its card whatever newer tries sit beside it
(010-DR-28); Stitch mosaic and Stack together for chosen filters only, on the canvas every filter shares
(004-DR-34); post-processing runs the steps chosen for that run (010-DR-29); masters drizzled ×2 or binned 2×2
(004-DR-35)."""

from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits

from apps.catalogue.models import Collection, Dataset
from apps.libraries.models import InstallationSettings
from apps.processing import masters, postprocess
from apps.processing.models import CombinedMaster, Master
from substation.tasks.models import Task

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _settings(**post) -> None:
    s = InstallationSettings.load()
    s.processing = {"post": {"rc_astro": "/nope/rc", **post}}
    s.save()


def _gx(tmp_path: Path) -> Path:
    gx = tmp_path / "gx"
    gx.write_text(
        '#!/bin/sh\nsrc="$1"; while [ "$1" ]; do [ "$1" = "-output" ] && out="$2"; shift; done; cp "$src" "$out.fits"\n'
    )
    gx.chmod(gx.stat().st_mode | stat.S_IEXEC)
    return gx


def _combined(tmp_path: Path, version: int = 1, state: str = "current", col=None) -> CombinedMaster:  # noqa: ANN001
    col = col or Collection.objects.create(name="Heart")
    out = tmp_path / f"combined_Ha_v{version}.fit"
    fits.PrimaryHDU(np.random.default_rng(1).normal(0.02, 0.002, (40, 60)).astype(np.float32)).writeto(out)
    return CombinedMaster.objects.create(
        collection=col, filter_norm="Hα", version=version, method="stitch", state=state, output_path=str(out)
    )


# ---- 010-DR-28: the card shows a stitched master's finished runs ----------------------------------------------


def test_the_real_report_shape_lists_its_stages(admin_client, tmp_path):
    """CombinedMaster 15 in production: a helper's run, a stage with its 100% view but no preview, and fields an
    older helper left out or sent as null. The list must come back with every stage, not fail."""
    cm = _combined(tmp_path)
    full = tmp_path / "combined_Ha_v1_background_full.jpg"
    full.write_bytes(b"\xff\xd8jpeg")
    fits_path = tmp_path / "combined_Ha_v1_background.fits"
    fits.PrimaryHDU(np.zeros((4, 4), np.float32)).writeto(fits_path)
    cm.report = {
        "post_runs": [
            {
                "run": 1,
                "helper": "studio-mac",
                "started_at": "2026-10-24T01:00:00+00:00",
                "finished_at": "2026-10-24T02:10:00+00:00",
                "stages": [
                    {
                        "step": "background",
                        "label": "Background extracted",
                        "state": "done",
                        "tool": "graxpert",
                        "seconds": 312.4,
                        "full": str(full),
                        "path": str(fits_path),
                    },
                    {
                        "step": "deconvolve",
                        "label": "Deconvolved",
                        "state": "done",
                        "tool": None,
                        "seconds": None,
                        "reason": None,
                        "params": None,
                        "full": str(full),
                        "preview": str(full),
                        "path": str(fits_path),
                    },  # fmt: skip
                    {
                        "step": "denoise",
                        "label": "Denoised",
                        "state": "skipped",
                        "reason": "RC-Astro isn't activated.",
                    },
                ],
            }
        ]
    }
    cm.save()
    out = admin_client.get(f"/api/v1/combined/{cm.pk}/post").json()
    run = out["runs"][0]
    assert run["run"] == 1 and run["helper"] == "studio-mac" and run["chosen"] is None
    assert [s["step"] for s in run["stages"]] == ["background", "deconvolve", "denoise"]
    bg, dc, dn = run["stages"]
    assert bg["preview"] is None and bg["full"] == f"/api/v1/combined/{cm.pk}/post/1/0/full"
    assert dc["preview"] and dc["tool"] == "" and dc["reason"] == "" and dc["tool_label"] == "BlurXTerminator"
    assert dn["state"] == "skipped" and dn["full"] is None
    assert admin_client.get(bg["full"]).status_code == 200


def test_a_newer_failed_or_deleted_try_doesnt_hide_the_current_master(admin_client, tmp_path):
    col = Collection.objects.create(name="Heart")
    cur = _combined(tmp_path, 1, "current", col)
    _combined(tmp_path, 2, "deleted", col)
    failed = _combined(tmp_path, 3, "failed", col)
    shown = admin_client.get(f"/api/v1/collections/{col.pk}/combined").json()["combined"]
    assert [c["id"] for c in shown] == [failed.pk, cur.pk]


# ---- 004-DR-34: chosen filters only, one canvas -----------------------------------------------------------------


def _master(col, key, filt, panel, tmp_path, accepted=0.0, resolution=None):  # noqa: ANN001
    d = Dataset.objects.create(
        group_key=key,
        display_name=key,
        target="IC 1805",
        filter_norm=filt,
        panel=panel,
        collection=col,
        accepted_integration_s=accepted,
    )
    out = tmp_path / f"{key}.fit"
    out.write_bytes(b"x")
    return Master.objects.create(
        dataset=d,
        version=1,
        state="current",
        sub_count=10,
        integration_s=6000,
        output_path=str(out),
        recipe={"options": {"resolution": resolution}} if resolution else {},
    )


def _mosaic_project(tmp_path):  # noqa: ANN001
    from apps.catalogue.models import Project

    col = Collection.objects.create(name="Heart")
    p = Project.objects.create(collection=col, own_name="2026", kind_override="mosaic")
    ms = [
        _master(col, "ha1", "Hα", 1, tmp_path, accepted=36000),
        _master(col, "ha2", "Hα", 2, tmp_path),
        _master(col, "o1", "OIII", 1, tmp_path),
        _master(col, "o2", "OIII", 2, tmp_path),
    ]
    Dataset.objects.filter(collection=col).update(project=p)
    return col, p, ms


def test_stitching_only_ha_builds_ha_on_the_whole_canvas(admin_client, tmp_path):
    col, p, ms = _mosaic_project(tmp_path)
    r = admin_client.post(
        f"/api/v1/collections/{col.pk}/combined?project={p.pk}&method=stitch",
        {"filters": ["Hα"]},
        content_type=JSON,
    )
    assert r.status_code == 201 and [c["filter"] for c in r.json()] == ["Hα"]
    assert list(CombinedMaster.objects.values_list("filter_norm", flat=True)) == ["Hα"]
    t = Task.objects.get(name__endswith="combine.stitch_mosaic")
    # the canvas is drawn from every panel of every filter, so OIII stitched later lands on the same grid
    assert sorted(t.args[2]) == sorted(m.pk for m in ms)
    # a filter that isn't in the plan says so
    r = admin_client.post(
        f"/api/v1/collections/{col.pk}/combined?project={p.pk}", {"filters": ["SII"]}, content_type=JSON
    )
    assert r.status_code == 422 and "SII" in r.json()["message"]


def test_stack_together_for_chosen_filters(admin_client, tmp_path):
    col = Collection.objects.create(name="Soul")
    _master(col, "ha", "Hα", None, tmp_path, accepted=36000)
    _master(col, "oiii", "OIII", None, tmp_path)
    r = admin_client.post(f"/api/v1/collections/{col.pk}/combined", {"filters": ["OIII"]}, content_type=JSON)
    assert r.status_code == 201 and [c["filter"] for c in r.json()] == ["OIII"]
    assert Task.objects.get(name__endswith="combine.stack_together").args[1] == [r.json()[0]["id"]]


def test_the_canvas_is_the_same_whichever_filters_are_stitched(tmp_path):
    """Stitch Hα alone, with OIII's panels shaping the canvas: the same canvas as stitching both together."""
    from apps.processing.combine import Panel, _mosaic_all

    from ..unit.test_mosaic import _SEQ3, _WCS, _panel_file, _StitchSiril

    solve = {"ra_deg": 83.8, "dec_deg": -5.4, "wcs": _WCS}
    a, b, c = (_panel_file(tmp_path, n) for n in ("ha1", "ha2", "o3"))
    ha = [Panel(1, "Hα · Panel 1", a, solve), Panel(2, "Hα · Panel 2", b, solve)]
    o3 = Panel(3, "OIII · Panel 3", c, solve)

    both_eng = _StitchSiril(tmp_path / "both", _SEQ3)
    both = _mosaic_all(both_eng, {10: ha, 11: [o3]}, ha[0], tmp_path / "both")
    alone_eng = _StitchSiril(tmp_path / "alone", _SEQ3)
    alone = _mosaic_all(alone_eng, {10: ha}, ha[0], tmp_path / "alone", extra=[o3])
    assert set(alone) == {10}  # OIII isn't stacked, it only shapes the canvas
    assert (tmp_path / "alone" / "m_00003.fit").exists()  # but it is laid out with the others
    assert alone[10].path is not None and both[10].path is not None
    assert fits.getdata(alone[10].path).shape == fits.getdata(both[10].path).shape == (14, 80)


def test_mixed_resolutions_are_left_out_with_why(admin_client, tmp_path):
    col, p, ms = _mosaic_project(tmp_path)
    Master.objects.filter(pk=ms[1].pk).update(recipe={"options": {"resolution": "drizzle2"}})
    plan = admin_client.get(f"/api/v1/collections/{col.pk}/combined?project={p.pk}").json()
    assert [i["master"] for i in plan["filters"]["Hα"]] == [ms[0].pk]
    assert "drizzled ×2, not normal resolution" in plan["left_out"][0]


# ---- 010-DR-29: the steps of one run ----------------------------------------------------------------------------


def test_a_run_takes_exactly_the_chosen_steps(admin_client, tmp_path):
    _settings(graxpert=str(_gx(tmp_path)))
    cm = _combined(tmp_path)
    choices = admin_client.get(f"/api/v1/combined/{cm.pk}/post").json()["steps"]
    assert [(c["step"], c["on"]) for c in choices] == [
        ("background", True),
        ("deconvolve", True),
        ("denoise", True),
        ("starless", False),
    ]
    r = admin_client.post(f"/api/v1/combined/{cm.pk}/post", {"steps": ["background"]}, content_type=JSON)
    assert r.status_code == 200
    t = Task.objects.get(name__endswith="postprocess_combined")
    assert [s["step"] for s in t.args[1]["steps"] if s["enabled"]] == ["background"]
    postprocess.postprocess_combined.call(*t.args)
    run = CombinedMaster.objects.get(pk=cm.pk).report["post_runs"][-1]
    assert [s["step"] for s in run["stages"] if s["step"] != "trim"] == ["background"]  # no GraXpert denoise
    assert run["chosen"] == ["background"]
    assert admin_client.get(f"/api/v1/combined/{cm.pk}/post").json()["runs"][0]["chosen"] == ["background"]
    bad = admin_client.post(f"/api/v1/combined/{cm.pk}/post", {"steps": ["sharpen"]}, content_type=JSON)
    assert bad.status_code == 422


def test_a_dataset_master_run_takes_the_chosen_steps_too(admin_client, tmp_path):
    col = Collection.objects.create(name="M 81")
    m = _master(col, "m81", "L", None, tmp_path)
    r = admin_client.post(
        f"/api/v1/stacks/{m.pk}/post", {"steps": ["background", "deconvolve"]}, content_type=JSON
    )
    assert r.status_code == 200
    t = Task.objects.get(name__endswith="postprocess_master")
    assert t.args[1]["chosen_steps"] == ["background", "deconvolve"]
    # without a choice it is Settings' selection, as before
    Task.objects.all().delete()
    admin_client.post(f"/api/v1/stacks/{m.pk}/post", content_type=JSON)
    assert Task.objects.get(name__endswith="postprocess_master").args == [m.pk]


def test_steps_whose_tool_isnt_ready_are_offered_as_unavailable():
    cfg = {"steps": [{"step": "background", "enabled": True}, {"step": "deconvolve", "enabled": True}]}
    tools = {
        "checked_at": "2026-10-24T00:00:00",
        "graxpert": {"ready": True},
        "rc_astro": {"ready": False, "reason": "RC-Astro isn't activated."},
    }
    got = {c["step"]: c for c in postprocess.step_choices(cfg, tools)}
    assert got["background"]["available"] and not got["deconvolve"]["available"]
    assert got["deconvolve"]["reason"] == "RC-Astro isn't activated."
    # before the finisher has reported, every step is offered
    assert all(c["available"] for c in postprocess.step_choices(cfg, {}))


# ---- 004-DR-35: drizzle ×2 and bin 2×2 --------------------------------------------------------------------------


class _RegSiril:
    def __init__(self) -> None:
        self.cmds: list[str] = []

    def run(self, cmd, **kw):  # noqa: ANN001, ANN003
        self.cmds.append(cmd)
        return SimpleNamespace(ok=True, log=[])


def _work(tmp_path: Path, n: int = 3) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    for i in range(1, n + 1):
        fits.PrimaryHDU(np.zeros((8, 8), np.float32)).writeto(work / f"sub_{i:05d}.fit")
    return work


def _m(resolution: str | None, reference: str = "best_fwhm") -> Any:
    return SimpleNamespace(
        pk=1,
        version=1,
        dataset_id=1,
        started_at=None,
        recipe={"options": {"resolution": resolution, "reference": reference}},
    )


@pytest.mark.parametrize(
    ("resolution", "reference", "expected"),
    [
        (
            "drizzle2",
            "best_fwhm",
            [
                "register sub_ -2pass",
                "seqapplyreg sub_ -framing=current -drizzle -scale=2 -pixfrac=1.0 -kernel=square",
            ],
        ),
        (
            "drizzle2",
            "most_stars",
            ["setref sub_ 1", "register sub_ -drizzle -scale=2 -pixfrac=1.0 -kernel=square"],
        ),
        (None, "best_fwhm", ["register sub_ -2pass", "seqapplyreg sub_ -framing=current"]),
        ("bin2", "best_fwhm", ["register sub_ -2pass", "seqapplyreg sub_ -framing=current"]),
    ],
)
def test_registration_commands(tmp_path, monkeypatch, resolution, reference, expected):
    work = _work(tmp_path)
    eng = _RegSiril()
    order = {
        i: SimpleNamespace(frame=SimpleNamespace(measurement=SimpleNamespace(stars=10 - i)))
        for i in (1, 2, 3)
    }
    monkeypatch.setattr(masters, "_save_checkpoint", lambda *a: None)
    masters._register(eng, _m(resolution, reference), work, {"done": []}, cast(Any, order), None)
    assert eng.cmds == expected


def test_a_drizzled_mosaic_is_laid_out_drizzled(tmp_path, monkeypatch):
    work = _work(tmp_path)
    eng = _RegSiril()
    monkeypatch.setattr(masters, "_solve_each", lambda *a: ([1, 2, 3], []))
    masters._register_mosaic(eng, _m("drizzle2"), work, cast(Any, {1: 0, 2: 0, 3: 0}), "Mosaic")
    assert eng.cmds[-1] == "seqapplyreg sub_ -framing=max -drizzle -scale=2 -pixfrac=1.0 -kernel=square"


def test_drizzle_is_refused_when_four_times_the_subs_dont_fit(tmp_path, monkeypatch, settings):
    settings.WORK_DIR = str(tmp_path / "w")
    work = _work(tmp_path, 10)
    size = (work / "sub_00001.fit").stat().st_size
    monkeypatch.setattr(masters, "work_budget_bytes", lambda: size * 10 * 3)  # room for 2×, not 5×
    masters._check_budget(work, 10)  # a normal stack fits
    with pytest.raises(RuntimeError, match="Drizzle ×2 makes every registered sub four times the size"):
        masters._check_budget(work, 10, grow=4)


def test_bin_2x2_averages_and_keeps_the_solution_on_the_coarser_grid(tmp_path):
    cache = tmp_path / "cache.fit"
    data = np.arange(5 * 7, dtype=np.uint16).reshape(5, 7) * 4
    h = fits.Header(
        {
            "XBINNING": 1,
            "XPIXSZ": 3.76,
            "CTYPE1": "RA---TAN-SIP",
            "CRPIX1": 4.5,
            "CRPIX2": 3.5,
            "CD1_1": 0.001,
            "CD2_2": 0.001,
            "A_ORDER": 2,
            "A_0_2": 1e-6,
        }  # fmt: skip
    )
    fits.PrimaryHDU(data, h).writeto(cache)
    link = tmp_path / "sub_00001.fit"
    link.symlink_to(cache)
    masters.bin2x2(link)
    assert not link.is_symlink() and fits.getdata(cache).shape == (5, 7)  # the cache is untouched
    out = fits.getdata(link)
    hdr = fits.getheader(link)
    assert out.shape == (2, 3) and out[0, 0] == round((0 + 4 + 28 + 32) / 4)
    assert hdr["XBINNING"] == 2 and hdr["XPIXSZ"] == pytest.approx(7.52)
    assert hdr["CD1_1"] == pytest.approx(0.002) and hdr["CRPIX1"] == pytest.approx(2.5)
    assert "A_ORDER" not in hdr and hdr["CTYPE1"] == "RA---TAN"


def test_a_stored_solution_is_written_into_a_binned_sub(tmp_path):
    p = tmp_path / "sub_00001.fit"
    fits.PrimaryHDU(np.zeros((5, 10), np.float32)).writeto(p)
    wcs = {"NAXIS1": 20, "NAXIS2": 10, "CTYPE1": "RA---TAN", "CRVAL1": 83.8, "CRPIX1": 10.5, "CD1_1": 0.001}
    assert masters._write_wcs(p, wcs)
    h = fits.getheader(p)
    assert h["CD1_1"] == pytest.approx(0.002) and h["CRPIX1"] == pytest.approx(5.5)


def test_the_master_says_how_it_was_sampled(admin_client, tmp_path):
    col = Collection.objects.create(name="M 81")
    m = _master(col, "m81", "L", None, tmp_path, resolution="drizzle2")
    row = admin_client.get(f"/api/v1/datasets/{m.dataset_id}/stacks").json()[0]
    assert row["resolution"] == "drizzle2" and row["method"].endswith("· Drizzle ×2")
    assert masters.pixel_factor("drizzle2") == 0.5 and masters.pixel_factor("bin2") == 2.0


def test_start_keeps_the_resolution_in_the_recipe(admin_client, monkeypatch, tmp_path):
    col = Collection.objects.create(name="M 81")
    m = _master(col, "m81", "L", None, tmp_path)
    seen = {}

    def fake_start(ds, nights, rule, user, options, scope):  # noqa: ANN001
        seen["options"] = options
        return m

    monkeypatch.setattr(masters, "start", fake_start)
    r = admin_client.post(
        f"/api/v1/datasets/{m.dataset_id}/stacks", {"options": {"resolution": "bin2"}}, content_type=JSON
    )
    assert r.status_code == 201 and seen["options"] == {"resolution": "bin2"}
