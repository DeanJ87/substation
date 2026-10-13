"""Owner 2026-10-10: the 100% view and aberration inspector of a sub."""

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from apps.processing.previews import full_and_inspector


def test_full_resolution_view_and_three_by_three_inspector(tmp_path):
    rng = np.random.default_rng(1)
    data = (rng.normal(1000, 20, (900, 1200))).astype(np.float32)
    data[10, 10] = 60000  # a star in the top-left corner of the displayed image (FITS rows run bottom-up)
    data = data[::-1]
    src = tmp_path / "sub.fit"
    fits.PrimaryHDU(data).writeto(src)
    full, inspect = tmp_path / "full.jpg", tmp_path / "inspect.jpg"
    full_and_inspector(src, full, inspect, tile=200)
    a = Image.open(full)
    assert a.size == (1200, 900)
    g = Image.open(inspect)
    assert g.size == (3 * 200 + 12, 3 * 200 + 12)
    assert np.asarray(g.convert("L"))[10, 10] > 200  # the corner star sits in the top-left tile


def test_xisf_subs_are_read_top_row_first(tmp_path):
    import xisf

    data = np.full((300, 400, 1), 1000, dtype=np.uint16)
    data[5, 5, 0] = 60000
    src = tmp_path / "sub.xisf"
    xisf.XISF.write(str(src), data)
    full, inspect = tmp_path / "f.jpg", tmp_path / "i.jpg"
    full_and_inspector(src, full, inspect, raw=True, tile=90)
    assert np.asarray(Image.open(inspect).convert("L"))[5, 5] > 200


def test_hoo_palette_from_registered_masters(tmp_path):
    """Owner 2026-10-10: HOO at 100% from combined masters: Hα in red, OIII in green and blue."""
    from apps.processing.previews import palette_and_inspector

    ha = np.random.default_rng(1).normal(1000, 20, (300, 300)).astype(np.float32)
    ha[145:156, 145:156] = 60000  # an Hα-only blob
    oiii = np.random.default_rng(2).normal(1000, 20, (300, 300)).astype(np.float32)
    for name, d in (("ha", ha), ("oiii", oiii)):
        fits.PrimaryHDU(d).writeto(tmp_path / f"{name}.fit")
    out = [tmp_path / "f.jpg", tmp_path / "i.jpg", tmp_path / "s.jpg"]
    palette_and_inspector(
        {"r": tmp_path / "ha.fit", "g": tmp_path / "oiii.fit", "b": tmp_path / "oiii.fit"},
        out[0],
        out[1],
        out[2],
        tile=90,
    )
    px = np.asarray(Image.open(out[0]))[300 - 1 - 150, 150]  # FITS rows run bottom-up
    assert px[0] > 200 and px[1] < 120 and px[2] < 120


def test_one_stretch_per_session(tmp_path):
    """003 G18: a cloudy sub's preview is darker than its clear neighbours, not stretched to match them."""
    from apps.processing.previews import render

    rng = np.random.default_rng(3)
    clear = rng.normal(1000, 20, (200, 300)).astype(np.float32)
    cloudy = (clear * 0.4 + 200).astype(np.float32)  # a dimmer sky, less contrast
    session = tmp_path / "stretch" / "2026-09-26.json"
    means = []
    for i, d in enumerate((clear, clear, clear, cloudy)):
        f = tmp_path / f"s{i}.fit"
        fits.PrimaryHDU(d).writeto(f)
        render(f, tmp_path / f"s{i}.jpg", tmp_path / f"s{i}_t.jpg", session=session)
        means.append(np.asarray(Image.open(tmp_path / f"s{i}.jpg")).mean())
    assert means[3] < means[0] - 30  # the cloudy sub is clearly darker
    solo = tmp_path / "solo.jpg"
    render(tmp_path / "s3.fit", solo, tmp_path / "solo_t.jpg")  # on its own it would look like the others
    assert abs(np.asarray(Image.open(solo)).mean() - means[0]) < 15


@pytest.mark.django_db
def test_a_session_is_redrawn_with_one_stretch(tmp_path, settings):
    """003 G18: rerender_session draws every sub of a session with the session's median stretch."""
    from datetime import UTC, date, datetime

    from apps.catalogue.models import Dataset, Frame, FrameStatus, FrameType, Night
    from apps.processing.models import SubMeasurement
    from apps.processing.tasks import rerender_session

    settings.PREVIEWS_DIR = tmp_path / "previews"
    ds = Dataset.objects.create(group_key="rr", display_name="rr", target="M 31")
    night = Night.objects.create(site_key="rr", date=date(2026, 9, 26))
    rng = np.random.default_rng(4)
    for i in range(4):
        d = rng.normal(1000, 20, (200, 300)).astype(np.float32) * (0.4 if i == 3 else 1)
        cal = tmp_path / f"c{i}.fit"
        fits.PrimaryHDU(d).writeto(cal)
        f = Frame.objects.create(
            sha256=f"rr{i}".ljust(64, "0"),
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
    assert rerender_session.call(ds.pk, night.pk)["redrawn"] == 4
    means = [np.asarray(Image.open(tmp_path / "previews" / f"p{i}.jpg")).mean() for i in range(4)]
    assert means[3] < means[0] - 30


def test_glance_is_small_and_stretched(tmp_path):
    """Owner 2026-10-11: hover previews of any frame, drawn small and fast."""
    from apps.processing.previews import glance

    data = np.random.default_rng(3).normal(1000, 20, (2000, 3000)).astype(np.float32)
    fits.PrimaryHDU(data).writeto(tmp_path / "a.fit")
    glance(tmp_path / "a.fit", tmp_path / "g.jpg", width=480)
    img = Image.open(tmp_path / "g.jpg")
    assert img.width <= 480 and 30 < np.asarray(img).mean() < 225
