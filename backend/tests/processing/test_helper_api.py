"""Spec 010 (owner 2026-10-13): post-processing runs on a helper on a faster machine. The helper claims a job with
its token, downloads the master, uploads each stage and says when it's done; SubStation records the run."""

from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits
from django.test import Client

from apps.catalogue.models import Dataset
from apps.processing.models import Master
from apps.processing.postprocess import postprocess_master
from substation.tasks import enqueue
from substation.tasks.models import Task, TaskStatus

pytestmark = pytest.mark.django_db
TOKEN = "test-helper-token"


@pytest.fixture
def helper(settings) -> Client:
    settings.SUBSTATION_HELPER_TOKEN = TOKEN
    return Client(HTTP_X_HELPER_TOKEN=TOKEN)


def _master(tmp_path) -> Master:
    d = Dataset.objects.create(group_key="k", display_name="M 81", target="M 81", filter_norm="Hα")
    out = tmp_path / "master_v1.fit"
    fits.PrimaryHDU(np.full((40, 60), 0.01, dtype=np.float32)).writeto(out)
    return Master.objects.create(dataset=d, version=1, state="current", output_path=str(out))


def test_a_helper_runs_a_job_end_to_end(helper, tmp_path):
    m = _master(tmp_path)
    enqueue(postprocess_master, m.pk)
    tools = {"graxpert": {"ready": True}, "rc_astro": {"ready": True}}
    r = helper.post("/api/v1/helper/claim", {"host": "mac", "tools": tools}, content_type="application/json")
    assert r.status_code == 200
    job = r.json()
    assert job["master_id"] == m.pk and job["settings"]["steps"]
    tid = job["task_id"]
    got = helper.get(f"{job['master_url']}?host=mac")
    assert got.status_code == 200 and b"".join(got.streaming_content)[:6] == b"SIMPLE"
    assert helper.post(
        f"/api/v1/helper/tasks/{tid}/progress?host=mac",
        {"note": "Deconvolved: running RC-Astro", "fraction": 0.4},
        content_type="application/json",
    ).json() == {"cancel": False}
    stage = tmp_path / "stage.fits"
    fits.PrimaryHDU(np.full((40, 60), 0.02, dtype=np.float32)).writeto(stage)
    up = helper.post(
        f"/api/v1/helper/tasks/{tid}/stage/0?host=mac&step=background",
        data=stage.read_bytes(),
        content_type="application/octet-stream",
    )
    assert up.status_code == 204
    done = helper.post(
        f"/api/v1/helper/tasks/{tid}/done?host=mac",
        {
            "stages": [
                {
                    "step": "background",
                    "label": "Background extracted",
                    "state": "done",
                    "tool": "graxpert",
                    "seconds": 2,
                    "file_name": "master_v1_background.fits",
                },
                {"step": "deconvolve", "label": "Deconvolved", "state": "skipped", "reason": "not wanted"},
            ]
        },
        content_type="application/json",
    )
    assert done.status_code == 204
    t = Task.objects.get(pk=tid)
    assert t.status == TaskStatus.SUCCEEDED
    run = Master.objects.get(pk=m.pk).report["post_runs"][-1]
    assert run["helper"] == "mac" and run["stages"][0]["state"] == "done" and run["stages"][0].get("full")
    assert run["original_stats"]


def test_no_token_no_job_and_nothing_to_do_is_204(helper, tmp_path):
    assert (
        Client().post("/api/v1/helper/claim", {"host": "x"}, content_type="application/json").status_code
        == 401
    )
    bad = Client(HTTP_X_HELPER_TOKEN="wrong")
    assert bad.post("/api/v1/helper/claim", {"host": "x"}, content_type="application/json").status_code == 401
    assert (
        helper.post("/api/v1/helper/claim", {"host": "mac"}, content_type="application/json").status_code
        == 204
    )


def test_another_helper_cant_touch_a_claimed_job(helper, tmp_path):
    m = _master(tmp_path)
    enqueue(postprocess_master, m.pk)
    job = helper.post("/api/v1/helper/claim", {"host": "mac"}, content_type="application/json").json()
    r = helper.post(
        f"/api/v1/helper/tasks/{job['task_id']}/progress?host=other", {}, content_type="application/json"
    )
    assert r.status_code == 409


def test_a_helper_shows_in_activity_with_cpu_ram_and_its_tool(helper, tmp_path):
    """Owner 2026-10-13: a helper reports CPU, RAM and progress like a NAS worker."""
    from substation.tasks.activity import activity

    m = _master(tmp_path)
    enqueue(postprocess_master, m.pk)
    idle = {"cpu_pct": 1.0, "rss_bytes": 40 << 20}
    job = helper.post(
        "/api/v1/helper/claim", {"host": "mac", "sample": idle}, content_type="application/json"
    ).json()
    helper.post(
        f"/api/v1/helper/tasks/{job['task_id']}/progress?host=mac",
        {
            "note": "Denoised: running RC-Astro",
            "fraction": 0.7,
            "command": "rc-astro nxt master.fits --depth 32F",
            "sample": {"cpu_pct": 410, "rss_bytes": 3 << 30, "tool_cpu_pct": 400, "tool_rss_bytes": 3 << 30},
        },
        content_type="application/json",
    )
    w = next(w for w in activity(None).workers if w.id == "helper:mac")
    assert w.kind == "helper" and w.host == "mac" and w.engine_label == "RC-Astro"
    assert w.cpu_pct == 410 and w.engine_rss_bytes == 3 << 30 and len(w.history) == 2
    assert w.job and w.job.progress == 0.7
