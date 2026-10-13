"""004 T008/T009: stack scope beyond chosen nights (date range, matching datasets) and subs included or excluded
by hand."""

import json
from datetime import UTC, date, datetime

import pytest

from apps.catalogue.models import Dataset, Frame, FrameStatus, FrameType, Night
from apps.processing.models import MachineGrade, SubMeasurement

pytestmark = pytest.mark.django_db
T = datetime(2026, 9, 1, 21, tzinfo=UTC)
KEY = {"target": "NGC 7000", "filter_norm": "Hα", "camera": "ATR2600M", "telescope": "Askar 71F"}


def ds(key: str, **kw) -> Dataset:
    return Dataset.objects.create(group_key=key, display_name=key, **(KEY | kw))


def sub(d: Dataset, n: int, day: int, verdict: str = "accept") -> Frame:
    night = Night.objects.get_or_create(site_key="s", date=date(2026, 9, day))[0]
    f = Frame.objects.create(
        sha256=f"{d.pk:02d}{n:02d}".ljust(64, "0"),
        size_bytes=1,
        format="fits",
        first_seen_at=T,
        dataset=d,
        night=night,
        status=FrameStatus.CATALOGUED,
        frame_type=FrameType.LIGHT,
        exptime_s=300,
        date_obs_utc=T,
    )
    SubMeasurement.objects.create(frame=f, state="done")
    MachineGrade.objects.create(frame=f, verdict=verdict, reason="")
    return f


def preview(client, d: Dataset, **body):
    return client.post(
        f"/api/v1/datasets/{d.pk}/stacks/preview", json.dumps(body), content_type="application/json"
    )


def test_include_exclude_date_range_and_matching_datasets(admin_client):
    a = ds("a")
    good = [sub(a, i, 3) for i in range(3)]
    bad = sub(a, 9, 4, verdict="reject")
    later = sub(a, 10, 20)
    assert preview(admin_client, a).json()["subs"] == 4
    r = preview(admin_client, a, include=[bad.pk], exclude=[good[0].pk]).json()
    assert r["subs"] == 4 and r["excluded"] == 1
    assert preview(admin_client, a, date_from="2026-09-01", date_to="2026-09-10").json()["subs"] == 3
    b = ds("b")
    sub(b, 1, 5)
    assert preview(admin_client, a, datasets=[b.pk]).json()["subs"] == 5
    other = ds("c", filter_norm="OIII")
    r = preview(admin_client, a, datasets=[other.pk])
    assert r.status_code == 422 and "can't be stacked" in r.json()["message"]
    assert later  # in scope without a range


def test_a_stack_remembers_its_scope(admin_client):
    from apps.processing.masters import choose, scope_of
    from apps.processing.models import Master

    a = ds("a")
    s = [sub(a, i, 3) for i in range(3)]
    r = admin_client.post(
        f"/api/v1/datasets/{a.pk}/stacks", json.dumps({"exclude": [s[0].pk]}), content_type="application/json"
    )
    assert r.status_code == 201
    m = Master.objects.get(pk=r.json()["id"])
    assert m.recipe["exclude"] == [s[0].pk] and m.sub_count == 2
    chosen = {c[0].pk: c for c in choose(a, None, "default", scope_of(m.recipe))}
    assert chosen[s[0].pk][3] == "excluded by you"


def test_stacks_api_contract(admin_client):
    """004 T023: list, partners, rerun, cancel, inputs, detail, preview and download answer as documented."""
    from apps.processing.models import Master
    from substation.tasks.models import Task

    a, b = ds("a"), ds("b")
    s = [sub(a, i, 3) for i in range(3)]
    sub(b, 1, 4)
    Dataset.objects.filter(pk=b.pk).update(sub_count=1)
    partners = admin_client.get(f"/api/v1/datasets/{a.pk}/stack-partners").json()
    assert [p["id"] for p in partners] == [b.pk]
    m = admin_client.post(f"/api/v1/datasets/{a.pk}/stacks", "{}", content_type="application/json").json()
    assert m["state"] == "queued" and Task.objects.filter(name__endswith="integrate").exists()
    listed = admin_client.get(f"/api/v1/datasets/{a.pk}/stacks").json()
    assert [x["id"] for x in listed] == [m["id"]]
    inputs = admin_client.get(f"/api/v1/stacks/{m['id']}/inputs").json()
    assert {i["sha256"] for i in inputs} == {f.pk for f in s}
    assert admin_client.get(f"/api/v1/stacks/{m['id']}/detail").status_code == 200
    assert admin_client.get(f"/api/v1/stacks/{m['id']}/preview").status_code == 404  # not integrated yet
    assert admin_client.get(f"/api/v1/stacks/{m['id']}/download").status_code == 404
    assert admin_client.post(f"/api/v1/stacks/{m['id']}/cancel").json()["state"] == "cancelled"
    again = admin_client.post(f"/api/v1/stacks/{m['id']}/rerun")
    assert again.status_code == 201 and again.json()["version"] == 2
    assert Master.objects.filter(dataset=a).count() == 2


def test_two_masters_compare_on_quality_not_noise(admin_client):
    """004 T006: side by side, with which is better on each measure; noise never decides."""
    from apps.processing.models import Master

    a = ds("a")
    report = {
        "stars": 4000,
        "fwhm_arcsec": 5.6,
        "roundness": 0.9,
        "noise": 2.0,
        "regional": {"zones": {"centre": {"fwhm_px": 3.0}, "bottom_right": {"fwhm_px": 4.3}}},
    }
    m1 = Master.objects.create(
        dataset=a, version=1, state="current", sub_count=40, integration_s=12000, report=report
    )
    m2 = Master.objects.create(
        dataset=a,
        version=2,
        state="current",
        sub_count=60,
        integration_s=18000,
        report=report | {"stars": 5200, "fwhm_arcsec": 5.0, "noise": 1.0},
    )
    r = admin_client.get(f"/api/v1/stacks/compare?a={m1.pk}&b={m2.pk}").json()
    rows = {x["label"]: x for x in r["rows"]}
    assert rows["FWHM"]["better"] == "b" and rows["Stars detected"]["better"] == "b"
    assert rows["Roundness"]["better"] == "same" and rows["Background noise"]["better"] == ""
    assert rows["FWHM bottom right"]["a"] == 4.3
    assert r["summary"].startswith("v2 is better on") and "Noise isn't judged" in r["summary"]


def test_live_progress_from_siril_lines(monkeypatch):
    """004 T004: Siril's progress lines move the master within its step; normalising shows as its own step."""
    from apps.processing import masters
    from apps.processing.models import Master

    notes = []
    monkeypatch.setattr(masters, "report_progress", lambda p, n: notes.append((round(p, 2), n)))
    m = Master.objects.create(dataset=ds("a"), version=3, state="running")
    live = masters._Live(m, "Register", 0.2, 0.6, 40)
    live("progress: 50.00%")
    m.refresh_from_db()
    assert (
        m.step == "Register"
        and abs(m.progress - 0.4) < 1e-6
        and notes[-1] == (0.4, "Master v3: Register 20/40")
    )
    stack = masters._Live(m, "Integrate", 0.6, 0.9, 40)
    stack("log: Normalisation of the sequence...")
    stack("progress: 0.5")
    m.refresh_from_db()
    assert m.step == "Normalise" and abs(m.progress - 0.75) < 1e-6


def test_automatic_stacks(settings):
    """004 T012: after each session (quiet time) or every N new usable subs; never under 3 usable subs."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.libraries.models import InstallationSettings
    from apps.processing.masters import auto_stacks
    from apps.processing.models import Master

    a = ds("a")
    subs = [sub(a, i, 3) for i in range(4)]
    Dataset.objects.update(sub_count=10)
    s = InstallationSettings.load()
    assert auto_stacks() == []  # "never" by default
    s.processing = {"stacking": {"auto": "session", "auto_quiet_hours": 3}}
    s.save()
    now = timezone.now()
    Frame.objects.filter(pk__in=[f.pk for f in subs]).update(date_obs_utc=now - timedelta(hours=1))
    assert auto_stacks(now) == []  # the session may still be going
    assert auto_stacks(now + timedelta(hours=3)) == [a.pk]
    assert Master.objects.get(dataset=a).recipe["options"]["auto"] is True
    assert auto_stacks(now + timedelta(hours=4)) == []  # queued already, and nothing new since
    s.processing = {"stacking": {"auto": "every_n", "auto_every_n": 5}}
    s.save()
    Master.objects.update(state="current")
    b = ds("b")
    Dataset.objects.update(sub_count=10)
    [sub(b, i, 5) for i in range(4)]
    assert auto_stacks() == []  # 4 of 5
    sub(b, 9, 5, verdict="reject")
    assert auto_stacks() == []  # a rejected sub doesn't count
    sub(b, 10, 5)
    assert auto_stacks() == [b.pk]


def test_mosaic_panels_are_never_stacked_together(admin_client):
    """Owner 2026-10-10: Heart panel 1 was stacked with panel 2; panels and framings must match."""
    a, b = ds("p1", panel=1), ds("p2", panel=2)
    sub(a, 1, 3)
    sub(b, 1, 3)
    Dataset.objects.update(sub_count=1)
    assert admin_client.get(f"/api/v1/datasets/{a.pk}/stack-partners").json() == []
    r = preview(admin_client, a, datasets=[b.pk])
    assert r.status_code == 422 and "panel 2, not panel 1" in r.json()["message"]
