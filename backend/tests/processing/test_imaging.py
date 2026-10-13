"""Spec 002 FR-002, FR-003, FR-006: calibration-frame QA on synthetic data (no Siril)."""

import numpy as np

from apps.processing.imaging import flat_report, frame_stats, leak_self_test, qa_set, star_spots


def dark(seed: int, size: int = 1024) -> np.ndarray:
    rng = np.random.default_rng(seed)
    a = 300 + rng.normal(0, 5, (size, size)).astype(np.float32)
    hot = rng.integers(0, size, (200, 2))
    a[hot[:, 0], hot[:, 1]] = 4000  # hot pixels are not stars
    return a


def add_stars(a: np.ndarray, n: int, peak: float = 15.0, seed: int = 9) -> np.ndarray:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[-6:7, -6:7]
    psf = peak * np.exp(-(xx**2 + yy**2) / (2 * 1.3**2))
    out = a.copy()
    for _ in range(n):
        y, x = rng.integers(20, a.shape[0] - 20, 2)
        out[y - 6 : y + 7, x - 6 : x + 7] += psf
    return out


def test_hot_pixels_are_not_stars():
    assert star_spots(dark(1)) <= 5


def test_15_adu_stars_are_found():
    assert star_spots(add_stars(dark(1), 30)) >= 24


def test_self_test_passes_on_a_clean_dark():
    assert leak_self_test(dark(2))


def test_a_leaky_dark_is_flagged_and_a_truncated_one_rejected():
    frames = {f"d{i}": dark(10 + i) for i in range(6)}
    frames["leak"] = add_stars(dark(20), 40)
    frames["faint"] = add_stars(dark(22), 18)
    trunc = dark(21)
    trunc[:300] = 0
    frames["trunc"] = trunc
    verdicts = qa_set("dark", {k: frame_stats(v, dark=True) for k, v in frames.items()})
    assert verdicts["leak"][0] == "reject" and "Not used" in verdicts["leak"][1]  # 002 C16: plainly stars
    assert verdicts["faint"][0] == "warn" and "light leak" in verdicts["faint"][1]
    assert verdicts["trunc"][0] == "reject"
    assert all(verdicts[f"d{i}"][0] == "pass" for i in range(6))


def test_a_gradient_is_large_scale_structure():
    frames = {f"d{i}": dark(30 + i) for i in range(5)}
    g = dark(40)
    g += np.linspace(0, 60, g.shape[1], dtype=np.float32)[None, :]
    frames["glow"] = g
    verdicts = qa_set("dark", {k: frame_stats(v, dark=True) for k, v in frames.items()})
    assert verdicts["glow"][0] == "warn" and "Uneven" in verdicts["glow"][1]


def test_flat_report_finds_a_dust_mote_and_falloff():
    size = 1024
    yy, xx = np.mgrid[0:size, 0:size]
    r2 = ((xx - size / 2) ** 2 + (yy - size / 2) ** 2) / (size / 2) ** 2
    f = (20000 * (1 - 0.1 * r2)).astype(np.float32)
    f[(yy - 700) ** 2 + (xx - 300) ** 2 < 25**2] *= 0.96
    rep = flat_report(f)
    assert 0.1 < rep["mean_falloff"] < 0.25
    assert any(abs(m["x"] - 300) < 15 and abs(m["y"] - 700) < 15 for m in rep["dust_motes"])


def test_comparing_flats_shows_new_dust():
    from apps.processing.imaging import compare_masters

    size = 512
    yy, xx = np.mgrid[0:size, 0:size]
    old = (20000 * (1 - 0.1 * ((xx - 256) ** 2 + (yy - 256) ** 2) / 256**2)).astype(np.float32)
    new = old * 1.1
    new[(yy - 100) ** 2 + (xx - 400) ** 2 < 12**2] *= 0.95
    got = compare_masters(new, old, flat=True)
    assert got is not None
    summary, img = got
    assert abs(summary["level_change"]) < 0.01  # the brighter panel is normalised away
    assert summary["changed_spots"] >= 1 and img.shape == old.shape
    assert compare_masters(new[:100], old, flat=True) is None


def _flat(size: int = 1024, noise: float = 0.0, seed: int = 4) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    f = 20000 * (1 - 0.1 * (((xx - size / 2) ** 2 + (yy - size / 2) ** 2) / (size / 2) ** 2))
    if noise:
        f = f * (1 + np.random.default_rng(seed).normal(0, noise, f.shape))
    return f.astype(np.float32)


def test_a_bayer_flat_is_analysed_as_superpixels():
    f = _flat()
    f[0::2, 1::2] *= 1.6  # green pixels respond more than red and blue
    f[1::2, 0::2] *= 1.6
    yy, xx = np.mgrid[0:1024, 0:1024]
    f[(yy - 700) ** 2 + (xx - 300) ** 2 < 30**2] *= 0.96
    rep = flat_report(f, cfa=True)
    assert rep["dust_mote_count"] <= 3
    assert any(abs(m["x"] - 300) < 20 and abs(m["y"] - 700) < 20 for m in rep["dust_motes"])


def test_noise_is_not_dust():
    rep = flat_report(_flat(noise=0.02))
    assert rep["dust_mote_count"] <= 2, rep["dust_motes"][:5]


def test_a_colour_mosaic_preview_is_in_colour(tmp_path):
    """One-shot-colour captures (Seestar GRBG) render as RGB, not a grey checkerboard."""
    from astropy.io import fits
    from PIL import Image

    from apps.processing.previews import render, superpixel

    a = np.full((40, 60), 100, np.float32)
    a[0::2, 1::2] = 900  # R in GRBG
    rgb = superpixel(a, "GRBG")
    assert rgb is not None and rgb.shape == (3, 20, 30) and rgb[0].mean() == 900 and rgb[2].mean() == 100
    assert superpixel(a, "XYZW") is None
    src = tmp_path / "s.fit"
    fits.PrimaryHDU(a, header=fits.Header({"BAYERPAT": "GRBG"})).writeto(src)
    render(src, tmp_path / "p.jpg", tmp_path / "p_t.jpg", raw=True)
    assert Image.open(tmp_path / "p.jpg").mode == "RGB"
