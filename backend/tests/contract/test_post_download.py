"""A processed version (GraXpert, BlurXTerminator, NoiseXTerminator) downloads as its linear file, for a browser set
to download rather than open in place (2026-10-15)."""

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Dataset
from apps.processing.models import Master

pytestmark = pytest.mark.django_db


def test_a_done_stage_downloads_and_others_do_not(admin_client, tmp_path):
    ds = Dataset.objects.create(group_key="m42ha", target="M 42", filter_norm="Hα", display_name="M 42 · Hα")
    f = tmp_path / "nxt.fit"
    f.write_bytes(b"SIMPLE  =                    T")
    stages = [
        {"step": "noisex", "state": "done", "path": str(f)},
        {"step": "blurx", "state": "skipped", "path": ""},
    ]
    now = datetime.now(UTC).isoformat()
    m = Master.objects.create(
        dataset=ds,
        version=2,
        state="current",
        report={"post_runs": [{"run": 1, "started_at": now, "finished_at": now, "stages": stages}]},
    )
    r = admin_client.get(f"/api/v1/stacks/{m.pk}/post/1/0/download")
    assert r.status_code == 200 and "attachment" in r["Content-Disposition"]
    assert (
        "M42_Hα_master_v2_noisex.fit" in r["Content-Disposition"] or "noisex.fit" in r["Content-Disposition"]
    )
    assert admin_client.get(f"/api/v1/stacks/{m.pk}/post/1/1/download").status_code == 404
