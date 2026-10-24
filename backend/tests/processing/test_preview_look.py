"""003 amendment 2026-10-24: one preview look for the whole installation. Sub previews share one stretch per
session (or each its own), and a black point offset in noise sigmas and a sky brightness apply to every sub
preview, glance and 100% view; changing them redraws previews in the background."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from apps.processing.previews import (
    glance,
    render,
    session_median,
    shared_params,
    stretch_params,
)

SKY, NOISE = 1000.0, 20.0


def _sky(seed: int = 1, scale: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    a = rng.normal(SKY, NOISE, (300, 400)).astype(np.float32) * scale
    a[150, 200] = 60000  # a star, so the range isn't the noise alone
    return a


def test_the_black_point_moves_by_noise_sigmas():
    a = _sky()
    lo0 = stretch_params(a)[0]
    lo_up = stretch_params(a, black_point=1.0)[0]
    lo_down = stretch_params(a, black_point=-1.0)[0]
    # one sigma of sky noise each way (the MAD of a normal sky is its sigma)
    assert lo_up - lo0 == pytest.approx(NOISE, rel=0.15)
    assert lo0 - lo_down == pytest.approx(NOISE, rel=0.15)
    assert lo0 == pytest.approx(SKY - 2.8 * NOISE, abs=NOISE * 0.3)  # the usual default, unchanged
    # never up to the sky itself, however far it is pushed
    assert stretch_params(a, black_point=5.0)[0] < float(np.median(a))


def _mean(path: Path) -> float:
    return float(np.asarray(Image.open(path)).mean())


def test_a_higher_black_point_draws_a_darker_sky_and_brightness_sets_its_grey(tmp_path):
    f = tmp_path / "a.fit"
    fits.PrimaryHDU(_sky()).writeto(f)
    means = {}
    for bp in (-2.0, 0.0, 2.0):
        out = tmp_path / f"p{bp}.jpg"
        render(f, out, tmp_path / f"p{bp}_t.jpg", look={"black_point": bp, "background": 0.25})
        means[bp] = _mean(out)
    assert means[2.0] < means[0.0] < means[-2.0]
    assert means[0.0] == pytest.approx(0.25 * 255, abs=12)  # the sky at a quarter grey
    render(f, tmp_path / "b.jpg", tmp_path / "b_t.jpg", look={"black_point": 0, "background": 0.1})
    assert _mean(tmp_path / "b.jpg") == pytest.approx(0.1 * 255, abs=10)


def test_one_shared_stretch_is_the_median_of_the_frames():
    per_sub = [[(1.0, 0.1, 10.0)], [(2.0, 0.2, 20.0)], [(9.0, 0.9, 90.0)]]
    assert shared_params(per_sub) == [(2.0, 0.2, 20.0)]
    colour = [[(1.0, 0.1, 1.0), (5.0, 0.5, 5.0), (7.0, 0.7, 7.0)]] * 2
    assert len(shared_params(colour)) == 3


def test_session_median_reads_without_adding(tmp_path):
    import json

    f = tmp_path / "s.json"
    assert session_median(f) is None
    f.write_text(json.dumps([[[1, 0.1, 10]], [[3, 0.3, 30]], [[1, 0.1, 10], [2, 0.2, 20], [3, 0.3, 30]]]))
    assert session_median(f, planes=1) == [(2.0, 0.2, 20.0)]
    assert session_median(f, planes=3) == [(1.0, 0.1, 10.0), (2.0, 0.2, 20.0), (3.0, 0.3, 30.0)]
    assert len(f.read_text()) > 0 and len(json.loads(f.read_text())) == 3  # nothing added


def test_glances_follow_the_black_point(tmp_path):
    f = tmp_path / "a.fit"
    fits.PrimaryHDU(_sky()).writeto(f)
    glance(f, tmp_path / "dark.jpg", look={"black_point": 2.0, "background": 0.25})
    glance(f, tmp_path / "light.jpg", look={"black_point": -2.0, "background": 0.25})
    assert _mean(tmp_path / "dark.jpg") < _mean(tmp_path / "light.jpg") - 20


def _session(tmp_path: Path):
    from apps.catalogue.models import Dataset, Frame, FrameStatus, FrameType, Night
    from apps.processing.models import SubMeasurement

    ds = Dataset.objects.create(group_key="pl", display_name="pl", target="M 31")
    night = Night.objects.create(site_key="pl", date=date(2026, 9, 26))
    frames = []
    for i in range(4):
        cal = tmp_path / f"c{i}.fit"
        fits.PrimaryHDU(_sky(i, 0.4 if i == 3 else 1.0)).writeto(cal)  # the last is under cloud
        f = Frame.objects.create(
            sha256=f"ab{i}".ljust(64, "0"),
            size_bytes=1,
            format="fits",
            dataset=ds,
            night=night,
            first_seen_at=datetime(2026, 9, 26, tzinfo=UTC),
            status=FrameStatus.CATALOGUED,
            frame_type=FrameType.LIGHT,
        )
        SubMeasurement.objects.create(
            frame=f,
            state="done",
            calibrated_path=str(cal),
            preview_path=str(tmp_path / "previews" / f"p{i}.jpg"),
        )
        frames.append(f)
    return ds, night, frames


@pytest.mark.django_db
@pytest.mark.parametrize("mode", ["session", "sub"])
def test_a_session_redraws_in_the_chosen_mode(tmp_path, settings, mode):
    from apps.libraries.models import InstallationSettings
    from apps.processing.tasks import full_paths, rerender_session, session_file

    settings.PREVIEWS_DIR = tmp_path / "previews"
    s = InstallationSettings.load()
    s.processing = {"previews": {"mode": mode}}
    s.save()
    ds, night, frames = _session(tmp_path)
    old_full = full_paths(frames[0])[0]
    old_full.parent.mkdir(parents=True, exist_ok=True)
    old_full.write_bytes(b"old")
    assert rerender_session.call(ds.pk, night.pk)["redrawn"] == 4
    means = [_mean(tmp_path / "previews" / f"p{i}.jpg") for i in range(4)]
    if mode == "session":
        assert means[3] < means[0] - 30  # the cloudy sub shows as darker beside the others
    else:
        assert abs(means[3] - means[0]) < 15  # each on its own: it looks like the rest
    assert not old_full.exists()  # 100% views are drawn again to match
    assert session_median(session_file(ds.pk, "2026-09-26", raw=False), planes=1)


@pytest.mark.django_db
def test_the_100pc_view_uses_the_session_stretch(tmp_path, settings):
    from apps.processing.tasks import draw_full_view, full_paths, rerender_session

    settings.PREVIEWS_DIR = tmp_path / "previews"
    ds, night, frames = _session(tmp_path)
    rerender_session.call(ds.pk, night.pk)
    for i in (0, 3):
        draw_full_view(frames[i], tmp_path / f"c{i}.fit")
    clear, cloudy = (_mean(full_paths(frames[i])[0]) for i in (0, 3))
    assert cloudy < clear - 30


@pytest.mark.django_db
def test_preview_settings_are_checked_and_redraw_in_the_background(admin_client):
    from substation.tasks.models import Task

    def patch(previews: dict):
        return admin_client.patch(
            "/api/v1/settings", {"processing": {"previews": previews}}, content_type="application/json"
        )

    got = admin_client.get("/api/v1/settings").json()["processing"]["previews"]
    assert got == {"mode": "session", "black_point": 0.0, "background": 0.25}
    assert patch({"mode": "sometimes"}).status_code == 422
    assert patch({"black_point": 3}).status_code == 422
    assert patch({"background": 0.9}).status_code == 422
    assert not Task.objects.filter(name__endswith="rerender_all_sessions").exists()
    r = patch({"black_point": 0.5, "mode": "sub"})
    assert r.status_code == 200 and r.json()["processing"]["previews"]["black_point"] == 0.5
    assert Task.objects.filter(name__endswith="rerender_all_sessions").count() == 1
    Task.objects.all().delete()
    patch({"black_point": 0.5})  # nothing changed: nothing redrawn
    assert not Task.objects.filter(name__endswith="rerender_all_sessions").exists()


@pytest.mark.django_db
def test_previews_are_revalidated_not_kept_for_a_day(admin_client, tmp_path):
    from apps.processing.models import SubMeasurement

    _ds, _night, frames = _session(tmp_path)
    p = tmp_path / "previews" / "p0.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", (4, 4)).save(p)
    assert SubMeasurement.objects.filter(frame=frames[0]).exists()
    r = admin_client.get(f"/api/v1/frames/{frames[0].sha256}/preview")
    assert r.status_code == 200 and r["Cache-Control"] == "private, max-age=300"
    again = admin_client.get(f"/api/v1/frames/{frames[0].sha256}/preview", HTTP_IF_NONE_MATCH=r["ETag"])
    assert again.status_code == 304
