"""Spec 010 US6 (2026-10-24): stitched mosaics and stacked-together masters go through the same post-processing
chain as a dataset's master: automatically after combining when the chain is on, or on request from the card;
runs are kept on the combined master and shown in the same viewer. A canvas too big for the worker is refused
with the reason, not a crash."""

from __future__ import annotations

import stat
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from django.test import Client

from apps.catalogue.models import Collection
from apps.libraries.models import InstallationSettings
from apps.processing import postprocess
from apps.processing.models import CombinedMaster
from substation.tasks.models import Task

pytestmark = pytest.mark.django_db
TOKEN = "test-helper-token"


def _gx(tmp_path: Path) -> Path:
    """A stand-in GraXpert that copies its input to `-output`.fits (as test_postprocess's)."""
    gx = tmp_path / "gx"
    gx.write_text(
        '#!/bin/sh\nsrc="$1"; while [ "$1" ]; do [ "$1" = "-output" ] && out="$2"; shift; done; cp "$src" "$out.fits"\n'
    )
    gx.chmod(gx.stat().st_mode | stat.S_IEXEC)
    return gx


def _settings(**post) -> None:
    s = InstallationSettings.load()
    s.processing = {"post": {"rc_astro": "/nope/rc", **post}}
    s.save()


def _combined(tmp_path: Path, method: str = "stitch") -> CombinedMaster:
    col = Collection.objects.create(name="Soul")
    out = tmp_path / "combined_Ha_v1.fit"
    data = np.random.default_rng(1).normal(0.02, 0.002, (60, 90)).astype(np.float32)
    fits.PrimaryHDU(data).writeto(out)
    return CombinedMaster.objects.create(
        collection=col, filter_norm="Hα", version=1, method=method, state="current", output_path=str(out)
    )


def test_a_combined_master_runs_the_chain_and_keeps_its_runs(tmp_path):
    _settings(graxpert=str(_gx(tmp_path)))
    cm = _combined(tmp_path)
    before = Path(cm.output_path).read_bytes()
    r = postprocess.postprocess_combined.call(cm.pk)
    assert r["run"] == 1 and r["done"] == 2  # GraXpert background and GraXpert denoise; BXT isn't here
    run = CombinedMaster.objects.get(pk=cm.pk).report["post_runs"][-1]
    done = [s for s in run["stages"] if s["state"] == "done"]
    assert done[0]["preview"] and done[0]["full"] and done[0]["stats"]
    assert run["original_stats"] and Path(cm.output_path).read_bytes() == before  # never touched
    assert Path(done[0]["path"]).parent.parent.name == "combined_Ha_v1_post1"


def test_the_combined_post_api(admin_client, standard_client, tmp_path):
    _settings(graxpert=str(_gx(tmp_path)))
    cm = _combined(tmp_path)
    assert admin_client.get(f"/api/v1/combined/{cm.pk}/post").json()["runs"] == []
    # starting a run is for admins
    assert (
        standard_client.post(f"/api/v1/combined/{cm.pk}/post", content_type="application/json").status_code
        == 403
    )
    r = admin_client.post(f"/api/v1/combined/{cm.pk}/post", content_type="application/json")
    assert r.status_code == 200 and r.json()["queued"]
    assert Task.objects.filter(name__endswith="postprocess_combined", args__0=cm.pk).count() == 1
    admin_client.post(
        f"/api/v1/combined/{cm.pk}/post", content_type="application/json"
    )  # asking twice queues it once
    assert Task.objects.filter(name__endswith="postprocess_combined", args__0=cm.pk).count() == 1
    postprocess.postprocess_combined.call(cm.pk)
    out = admin_client.get(f"/api/v1/combined/{cm.pk}/post").json()
    stage = next(s for s in out["runs"][0]["stages"] if s["state"] == "done")
    assert stage["full"].startswith(f"/api/v1/combined/{cm.pk}/post/1/")
    for url in (stage["preview"], stage["full"], stage["download"]):
        assert admin_client.get(url).status_code == 200
    assert admin_client.get(f"/api/v1/combined/{cm.pk}/post/9/0/full").status_code == 404


def test_a_deleted_combined_master_cant_be_post_processed(admin_client, tmp_path):
    cm = _combined(tmp_path)
    CombinedMaster.objects.filter(pk=cm.pk).update(state="deleted", output_path="")
    assert (
        admin_client.post(f"/api/v1/combined/{cm.pk}/post", content_type="application/json").status_code
        == 409
    )


@pytest.mark.parametrize("on", [True, False])
def test_combining_queues_post_processing_when_the_chain_is_on(tmp_path, on):
    from apps.processing.combine import _after_combine

    _settings(enabled=on)
    cm = _combined(tmp_path)
    _after_combine([cm], cm.collection_id)
    assert Task.objects.filter(name__endswith="postprocess_combined", args__0=cm.pk).exists() is on


def test_size_limits_are_plain_reasons(tmp_path, monkeypatch):
    src = tmp_path / "m.fits"
    fits.PrimaryHDU(np.zeros((10, 10), dtype=np.float32)).writeto(src)
    cfg = {"steps": [{"step": "background", "enabled": True}], "max_megapixels": 1000}
    out = tmp_path / "post"
    assert postprocess.image_size(src) == (10, 10, 1)
    assert postprocess.size_problem(src, out, cfg) == ""
    monkeypatch.setattr(postprocess, "image_size", lambda p: (70_000, 1_000, 1))
    assert "can't be wider or taller" in postprocess.size_problem(src, out, cfg)
    monkeypatch.setattr(postprocess, "image_size", lambda p: (40_000, 40_000, 1))
    assert "1,600 megapixels" in postprocess.size_problem(src, out, cfg)
    monkeypatch.setattr(postprocess, "image_size", lambda p: (20_000, 20_000, 3))  # 400 MP, 4.8 GB a stage
    monkeypatch.setattr(postprocess, "available_memory", lambda: 8 * 1024**3)
    assert "Not enough memory" in postprocess.size_problem(src, out, cfg)
    monkeypatch.setattr(postprocess, "available_memory", lambda: None)  # unknown: not checked

    class Usage:
        free = 2 * 1024**3

    monkeypatch.setattr(postprocess.shutil, "disk_usage", lambda p: Usage())
    assert "Not enough disk space" in postprocess.size_problem(src, out, cfg)


def test_a_mosaic_too_big_records_why_and_doesnt_crash(tmp_path, monkeypatch):
    _settings(graxpert=str(_gx(tmp_path)))
    cm = _combined(tmp_path)
    monkeypatch.setattr(postprocess, "image_size", lambda p: (40_000, 40_000, 1))
    r = postprocess.postprocess_combined.call(cm.pk)
    assert r["result"] == "too large"
    run = CombinedMaster.objects.get(pk=cm.pk).report["post_runs"][-1]
    assert run["stages"][0]["state"] == "failed" and "megapixels" in run["stages"][0]["reason"]
    assert not list(tmp_path.glob("combined_Ha_v1_post1/step*"))  # no tool ran


def test_a_helper_takes_a_combined_master(settings, tmp_path):
    from substation.tasks import enqueue

    settings.SUBSTATION_HELPER_TOKEN = TOKEN
    helper = Client(HTTP_X_HELPER_TOKEN=TOKEN)
    cm = _combined(tmp_path)
    enqueue(postprocess.postprocess_combined, cm.pk)
    job = helper.post("/api/v1/helper/claim", {"host": "mac"}, content_type="application/json").json()
    assert job["kind"] == "combined" and job["master_id"] == cm.pk and "Hα mosaic v1" in job["name"]
    assert job["master_file"] == "combined_Ha_v1.fit"
    got = helper.get(f"{job['master_url']}?host=mac")
    assert b"".join(got.streaming_content)[:6] == b"SIMPLE"
    stage = tmp_path / "stage.fits"
    fits.PrimaryHDU(np.full((60, 90), 0.03, dtype=np.float32)).writeto(stage)
    tid = job["task_id"]
    helper.post(
        f"/api/v1/helper/tasks/{tid}/stage/0?host=mac&step=background",
        data=stage.read_bytes(),
        content_type="application/octet-stream",
    )
    done = helper.post(
        f"/api/v1/helper/tasks/{tid}/done?host=mac",
        {
            "stages": [
                {
                    "step": "background",
                    "label": "Background extracted",
                    "state": "done",
                    "tool": "graxpert",
                    "file_name": "combined_Ha_v1_background.fits",
                }
            ]
        },
        content_type="application/json",
    )
    assert done.status_code == 204
    run = CombinedMaster.objects.get(pk=cm.pk).report["post_runs"][-1]
    assert run["run"] == 1 and run["helper"] == "mac" and run["stages"][0].get("full")


def test_a_helper_isnt_given_a_canvas_too_big_for_the_server(settings, tmp_path, monkeypatch):
    from substation.tasks import enqueue
    from substation.tasks.models import TaskStatus

    settings.SUBSTATION_HELPER_TOKEN = TOKEN
    helper = Client(HTTP_X_HELPER_TOKEN=TOKEN)
    cm = _combined(tmp_path)
    enqueue(postprocess.postprocess_combined, cm.pk)
    monkeypatch.setattr(postprocess, "size_problem", lambda *a: "Too large to post-process: test.")
    r = helper.post("/api/v1/helper/claim", {"host": "mac"}, content_type="application/json")
    assert r.status_code == 204
    t = Task.objects.get(name__endswith="postprocess_combined")
    assert t.status == TaskStatus.FAILED and "Too large" in (t.error or "")
    assert CombinedMaster.objects.get(pk=cm.pk).report["post_runs"][-1]["stages"][0]["state"] == "failed"
