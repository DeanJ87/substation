"""Spec 020: finished projects in a Completed library, render tokens, and the render read API."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from django.test import Client
from PIL import Image

from apps.catalogue.models import Collection, Dataset, DatasetNight, Frame, Night, Project
from apps.finished.models import ApiToken, FinishedProject
from apps.finished.scan import scan_all
from apps.libraries.models import InstallationSettings, Library, LibraryRole
from apps.processing.models import MachineGrade, PlateSolve, SkyPosition, SubMeasurement

pytestmark = pytest.mark.django_db
T0 = datetime(2026, 9, 14, 22, 0, tzinfo=UTC)


def _png(path, size=(64, 48), colour=(200, 40, 40)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)


@pytest.fixture
def completed(tmp_path):
    root = tmp_path / "completed"
    proj = root / "Astro" / "IC 1805" / "2026 Heart Nebula"
    _png(proj / "exports" / "heart-final.png")
    _png(proj / "exports" / "heart-starless.png")
    _png(proj / "exports" / "heart-stars.png")
    _png(proj / "exports" / "heart-Ha.png")
    (proj / "project").mkdir(parents=True)
    (proj / "project" / "heart.xisf").write_bytes(b"working file")
    (root / "Misc" / "stuff").mkdir(parents=True)
    lib = Library.objects.create(name="completed", mount_path=str(root), role=LibraryRole.COMPLETED)
    return lib, proj


@pytest.fixture
def heart():
    """A Heart Nebula project: two Hα/OIII panels over two nights, graded."""
    col = Collection.objects.create(
        name="Heart Nebula", objects_text="Heart · IC 1805", constellation="Cassiopeia"
    )
    project = Project.objects.create(collection=col, name="Mosaic 2026", kind="mosaic", planned_panels=2)
    n1 = Night.objects.create(site_key="48,9", date=date(2026, 9, 14), site_lat=47.62, site_lon=8.71)
    n2 = Night.objects.create(site_key="48,9", date=date(2026, 9, 15), site_lat=47.62, site_lon=8.71)
    i = 0
    for panel in (1, 2):
        for flt in ("Hα", "OIII"):
            ds = Dataset.objects.create(
                group_key=f"heart-{panel}-{flt}",
                target="IC 1805",
                panel=panel,
                filter_norm=flt,
                camera="ATR2600M",
                telescope="ED 500",
                display_name=f"IC 1805 · Panel {panel} · {flt}",
                collection=col,
                project=project,
                accepted_count=3,
                down_count=1,
                rejected_count=1,
                accepted_integration_s=4 * 300,
                rejected_integration_s=300,
            )
            for night in (n1, n2):
                DatasetNight.objects.create(dataset=ds, night=night, sub_count=2, integration_s=600)
            for k, verdict in enumerate(("accept", "accept", "accept", "down", "reject")):
                i += 1
                f = Frame.objects.create(
                    sha256=f"{i:064x}",
                    size_bytes=1,
                    format="fits",
                    status="catalogued",
                    frame_type="light",
                    first_seen_at=T0,
                    object="IC 1805",
                    target="IC 1805",
                    panel=panel,
                    filter_norm=flt,
                    exptime_s=300,
                    date_obs_utc=(when := T0 + timedelta(minutes=5 * i)),
                    site_lat=47.6213,
                    site_lon=8.7134,
                    night=n1 if k < 3 else n2,
                    dataset=ds,
                )
                MachineGrade.objects.create(frame=f, verdict=verdict, weight=1.0, reason="test")
                SubMeasurement.objects.create(frame=f, state="done", stars=900 + i, fwhm_arcsec=2.1, snr=30.5)
                PlateSolve.objects.create(
                    frame=f,
                    state="solved",
                    ra_deg=38.2,
                    dec_deg=61.45,
                    scale_arcsec=1.55,
                    fov_w_deg=2.5,
                    fov_h_deg=1.7,
                )
                SkyPosition.objects.create(
                    frame=f,
                    at=when,
                    site_lat=47.6213,
                    site_lon=8.7134,
                    ra_deg=38.2,
                    dec_deg=61.45,
                    source="header",
                    alt_deg=40 + i * 0.1,
                    az_deg=60 + i,
                    hour_angle_h=-2,
                )
    return project


@pytest.fixture
def token():
    _, raw = ApiToken.issue("renderer")
    return raw


def bearer(raw: str) -> Client:
    return Client(HTTP_AUTHORIZATION=f"Bearer {raw}")


def test_scan_finds_the_project_and_reports_folders_that_dont_fit(completed):
    lib, _ = completed
    res = scan_all()[lib.pk]
    assert res.projects == 1
    assert any(path == "Misc" for path, _ in res.not_projects)
    p = FinishedProject.objects.get()
    assert (p.kind, p.subject, p.name) == ("astro", "IC 1805", "2026 Heart Nebula")
    roles = {f.rel_path: (f.role, f.role_filter) for f in p.files.all()}
    assert roles["exports/heart-final.png"] == ("final", "")
    assert roles["exports/heart-starless.png"] == ("starless", "")
    assert roles["exports/heart-stars.png"] == ("stars", "")
    assert roles["project/heart.xisf"] == ("", "")


def test_render_api_refuses_without_a_valid_token(completed, admin_client):
    scan_all()
    assert Client().get("/api/v1/render/projects").status_code == 401
    assert bearer("sst_wrong").get("/api/v1/render/projects").status_code == 401
    tok, raw = ApiToken.issue("old")
    tok.revoked_at = T0
    tok.save()
    assert bearer(raw).get("/api/v1/render/projects").status_code == 401
    # a signed-in session can't use the render API either
    assert admin_client.get("/api/v1/render/projects").status_code == 401


def test_a_render_token_cant_reach_the_rest_of_the_api(token):
    assert bearer(token).get("/api/v1/libraries").status_code in (401, 403)


def test_unlinked_projects_are_not_offered_then_linking_offers_them(completed, heart, token, admin_client):
    scan_all()
    p = FinishedProject.objects.get()
    assert bearer(token).get("/api/v1/render/projects").json()["projects"] == []
    sugg = admin_client.get(f"/api/v1/finished/{p.pk}/suggestions").json()
    assert sugg[0]["project_id"] == heart.pk
    assert any("IC1805" in r for r in sugg[0]["reasons"])
    r = admin_client.put(
        f"/api/v1/finished/{p.pk}/links",
        data=json.dumps({"project_ids": [heart.pk]}),
        content_type="application/json",
    )
    assert r.status_code == 200, r.content
    listed = bearer(token).get("/api/v1/render/projects").json()
    assert [x["id"] for x in listed["projects"]] == [str(p.pk)]
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    assert bearer(token).get("/api/v1/render/projects", {"since": later}).json()["projects"] == []


def _linked(heart) -> FinishedProject:
    scan_all()
    p = FinishedProject.objects.get()
    p.linked_projects.set([heart])
    p.processing = ["GraXpert", "BlurXTerminator"]
    p.save()
    return p


def test_render_data_matches_the_app_totals_and_omits_what_isnt_known(completed, heart, token):
    p = _linked(heart)
    data = bearer(token).get(f"/api/v1/render/projects/{p.pk}").json()
    assert data["schema_version"] == 1
    assert data["target"]["name"] == "IC 1805"
    assert data["target"]["common_name"] == "Heart Nebula"
    assert data["target"]["constellation"] == "Cassiopeia"
    cap = data["capture"]
    assert cap["subs_accepted"] == 12 and cap["subs_down_weighted"] == 4 and cap["subs_rejected"] == 4
    assert cap["subs_total"] == 20
    assert cap["total_integration_s"] == 16 * 300
    assert cap["nights"] == 2 and cap["first_night"] == "2026-09-14" and cap["last_night"] == "2026-09-15"
    assert cap["mosaic"] == {"panels": 2}
    assert {f["name"] for f in cap["filters"]} == {"Hα", "OIII"}
    assert data["timeline"][0]["track"]
    assert {q["verdict"] for q in data["quality"]} == {"accept", "down", "reject"}
    assert data["quality"][0]["fwhm_arcsec"] == 2.1 and "fwhm" not in data["quality"][0]
    assert data["target"]["ra_deg"] == 38.2
    assert data["capture"]["rigs"][0]["pixel_scale_arcsec"] == 1.55
    assert data["frames"]["final"].startswith("/api/v1/render/projects/")  # root-relative, like project.json
    assert data["processing"] == ["GraXpert", "BlurXTerminator"]
    assert "annotations" not in data  # unsolved: left out, not faked
    assert set(data["frames"]) >= {"final", "starless", "stars", "thumb"}


def test_no_coordinates_leave_substation(completed, heart, token):
    s = InstallationSettings.load()
    s.site_region, s.site_bortle, s.site_lat, s.site_lon = "Example Valley", 5, 47.6, 8.7
    s.save()
    p = _linked(heart)
    body = bearer(token).get(f"/api/v1/render/projects/{p.pk}").content.decode()
    data = json.loads(body)
    assert data["capture"]["sites"] == [
        {
            "id": "s1",
            "region": "Example Valley",
            "bortle": 5,
            "lat_1deg": 48,
            "subs": 16,
            "integration_s": 4800.0,
        }
    ]
    assert {r["site"] for r in data["timeline"]} == {"s1"} and {q["site"] for q in data["quality"]} == {"s1"}
    for leak in ("47.62", "8.71", "site_lon", "site_lat", '"lon'):
        assert leak not in body


def test_files_are_served_by_role_with_an_etag_and_a_thumbnail(completed, heart, token):
    p = _linked(heart)
    c = bearer(token)
    r = c.get(f"/api/v1/render/projects/{p.pk}/files/final")
    assert r.status_code == 200
    etag = r["ETag"]
    assert c.get(f"/api/v1/render/projects/{p.pk}/files/final", HTTP_IF_NONE_MATCH=etag).status_code == 304
    thumb = c.get(f"/api/v1/render/projects/{p.pk}/files/thumb")
    assert thumb.status_code == 200 and thumb["ETag"].endswith('-thumb"')
    assert c.get(f"/api/v1/render/projects/{p.pk}/files/nope").status_code == 404


def test_tokens_are_shown_once_and_revocable(admin_client):
    r = admin_client.post(
        "/api/v1/tokens", data=json.dumps({"name": "dean0 render"}), content_type="application/json"
    )
    assert r.status_code == 201, r.content
    secret = r.json()["secret"]
    assert secret.startswith("sst_")
    listed = admin_client.get("/api/v1/tokens").json()
    assert "secret" not in listed[0] and listed[0]["hint"] == secret[-4:]
    assert bearer(secret).get("/api/v1/render/projects").status_code == 200
    admin_client.post(f"/api/v1/tokens/{listed[0]['id']}/revoke")
    assert bearer(secret).get("/api/v1/render/projects").status_code == 401


def test_project_json_needs_a_writable_library_and_never_overwrites_a_foreign_one(
    completed, heart, admin_client, monkeypatch
):
    lib, folder = completed
    p = _linked(heart)
    monkeypatch.setattr("apps.libraries.access.is_writable", lambda lib: False)
    r = admin_client.post(f"/api/v1/finished/{p.pk}/project-json")
    assert r.status_code == 409
    monkeypatch.setattr("apps.libraries.access.is_writable", lambda lib: True)
    r = admin_client.post(f"/api/v1/finished/{p.pk}/project-json")
    assert r.status_code == 200, r.content
    written = json.loads((folder / "project.json").read_text())
    assert written["project"]["name"] == "2026 Heart Nebula"
    assert admin_client.post(f"/api/v1/finished/{p.pk}/project-json").status_code == 200  # ours: rewrite ok
    (folder / "project.json").write_text("{}")
    assert admin_client.post(f"/api/v1/finished/{p.pk}/project-json").status_code == 409


def _lat_lon_from_track(data) -> tuple[float, float]:
    """Brute-force the site that best explains the track points at the sub times (what an attacker would do)."""
    from apps.processing.sky import alt_az

    ra, dec = data["target"]["ra_deg"], data["target"]["dec_deg"]
    row = data["timeline"][0]
    times = [datetime.fromisoformat(q["t"].replace("Z", "+00:00")) for q in data["quality"]][
        : len(row["track"])
    ]
    best = (1e9, 0.0, 0.0)
    for lat10 in range(440, 520, 2):
        for lon10 in range(60, 120, 2):
            lat, lon = lat10 / 10, lon10 / 10
            alts, azs, _ = alt_az([ra] * len(times), [dec] * len(times), times, lat, lon)
            err = sum(
                (a - p[1]) ** 2 + (z - p[0]) ** 2 for a, z, p in zip(alts, azs, row["track"], strict=False)
            )
            best = min(best, (err, lat, lon))
    return best[1], best[2]


def test_tracks_dont_give_the_site_away(completed, heart, token):
    p = _linked(heart)
    data = bearer(token).get(f"/api/v1/render/projects/{p.pk}").json()
    assert data["timeline"][0]["track"]
    lat, lon = _lat_lon_from_track(data)
    # the real site is 47.6213, 8.7134; tracks are drawn from the site rounded to whole degrees (48, 9)
    # the best an attacker gets is the whole-degree site, not the real longitude
    assert abs(lon - 8.7134) >= 0.2
    assert abs(lat - 48) < 0.2 and abs(lon - 9) < 0.2


def test_a_time_without_a_zone_is_read_as_utc(completed, heart, token):
    _linked(heart)
    r = bearer(token).get("/api/v1/render/projects", {"since": "2000-01-01T00:00:00"})
    assert r.status_code == 200 and len(r.json()["projects"]) == 1


def test_default_processing_can_be_set(admin_client):
    r = admin_client.put(
        "/api/v1/finished/defaults/processing",
        data=json.dumps({"steps": ["GraXpert", " ", "NoiseXTerminator"]}),
        content_type="application/json",
    )
    assert r.status_code == 200, r.content
    assert r.json() == ["GraXpert", "NoiseXTerminator"]


def test_an_empty_mount_keeps_the_last_known_projects(completed, heart, token, tmp_path):
    lib, folder = completed
    _linked(heart)
    empty = tmp_path / "dropped"
    empty.mkdir()
    Library.objects.filter(pk=lib.pk).update(mount_path=str(empty))
    from apps.finished import scan

    scan._last_scan.clear()
    listed = bearer(token).get("/api/v1/render/projects").json()
    assert listed["library_reachable"] is False
    assert len(listed["projects"]) == 1


def test_a_renamed_final_keeps_its_role(completed, heart, token):
    lib, folder = completed
    p = _linked(heart)
    f = p.files.get(rel_path="exports/heart-final.png")
    f.role_set_by_owner = True
    f.save()
    (folder / "exports" / "heart-final.png").rename(folder / "exports" / "heart-v2.png")
    scan_all()
    assert p.files.get(rel_path="exports/heart-v2.png").role == "final"
    assert bearer(token).get(f"/api/v1/render/projects/{p.pk}/files/final").status_code == 200


def test_a_social_crop_never_becomes_the_final(completed):
    lib, folder = completed
    _png(folder / "social" / "heart-final-4x5.jpg")
    scan_all()
    p = FinishedProject.objects.get()
    assert p.files.get(rel_path="exports/heart-final.png").role == "final"
    assert p.files.get(rel_path="social/heart-final-4x5.jpg").role == ""


def test_a_master_from_two_sites_lists_both_and_tags_each_sub(completed, heart, token):
    """A remote observatory's subs mixed with home ones: two sites, never an average (020-DR-07)."""
    remote = Frame.objects.filter(dataset__panel=2)
    remote.update(site_lat=-31.27, site_lon=149.06)
    p = _linked(heart)
    data = bearer(token).get(f"/api/v1/render/projects/{p.pk}").json()
    sites = data["capture"]["sites"]
    assert [(x["id"], x["lat_1deg"], x["subs"]) for x in sites] == [("s1", 48, 8), ("s2", -31, 8)]
    assert all("region" not in x for x in sites)  # no settings describe these places: nothing invented
    by_site = {r["site"] for r in data["timeline"]}
    assert by_site == {"s1", "s2"}
    remote_rows = [r for r in data["timeline"] if r["site"] == "s2"]
    home_rows = [r for r in data["timeline"] if r["site"] == "s1"]
    # each track is drawn from its own site: the same target sits very differently in the two skies
    assert remote_rows[0]["track"][0] != home_rows[0]["track"][0]
    assert {q["site"] for q in data["quality"] if q["verdict"] != "reject"} == {"s1", "s2"}


def test_the_target_name_prefers_a_catalogue_designation(completed, heart, token):
    p = _linked(heart)
    data = bearer(token).get(f"/api/v1/render/projects/{p.pk}").json()
    assert data["target"]["name"] == "IC 1805"
    assert data["target"]["common_name"] == "Heart Nebula"


def test_a_site_with_only_rejected_subs_still_has_an_id(completed, heart, token):
    rejected = [f.pk for f in Frame.objects.filter(grade__verdict="reject")]
    Frame.objects.filter(pk__in=rejected).update(site_lat=-31.27, site_lon=149.06)
    p = _linked(heart)
    data = bearer(token).get(f"/api/v1/render/projects/{p.pk}").json()
    sites = {x["id"]: x for x in data["capture"]["sites"]}
    assert sites["s2"]["lat_1deg"] == -31 and sites["s2"]["subs"] == 0
    assert all("site" in q for q in data["quality"])


def test_a_folder_substation_cant_write_gives_a_reason_not_a_500(completed, heart, admin_client, monkeypatch):
    lib, folder = completed
    p = _linked(heart)
    monkeypatch.setattr("apps.libraries.access.is_writable", lambda lib: True)

    def denied(self, data):  # noqa: ANN001
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("pathlib.Path.write_bytes", denied)
    r = admin_client.post(f"/api/v1/finished/{p.pk}/project-json")
    assert r.status_code == 409
    assert r.json()["code"] == "no_permission"


def test_a_single_field_project_is_never_a_mosaic_whatever_the_subs_say(completed, heart, token):
    """Subs carry panels 1 and 2, but the owner says the project is one field (020-DR-10)."""
    heart.kind, heart.planned_panels = "single", None
    heart.save()
    p = _linked(heart)
    data = bearer(token).get(f"/api/v1/render/projects/{p.pk}").json()
    assert "mosaic" not in data["capture"]
    assert all("panel" not in r for r in data["timeline"])
    assert data["capture"]["subs_accepted"] == 12  # every panel's subs still count
