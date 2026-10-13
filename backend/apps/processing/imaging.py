"""Pixel analysis for calibration frames and masters (spec 002 US2, US3): reading FITS or XISF data, per-frame
statistics for QA, and flat analysis (corner falloff, radial profile, dust motes). numpy and scipy, one frame
in memory at a time, as float32."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

FULL_SCALE = 65535.0


def read_data(path: Path, image_index: int = 0) -> np.ndarray:
    """2-D float32 data in ADU (16-bit scale); colour data (3 planes) is averaged; Bayer data is left as is."""
    lower = path.name.lower()
    if lower.endswith(".xisf"):
        import xisf

        x = xisf.XISF(str(path))
        data = x.read_image(image_index)
        arr = np.asarray(data, dtype=np.float32)
        if arr.ndim == 3:  # xisf gives (h, w, channels)
            arr = arr.mean(axis=2) if arr.shape[2] > 1 else arr[:, :, 0]
        if arr.max() <= 1.0 + 1e-6:  # floating point images are normalised to 0–1
            arr = arr * FULL_SCALE
        return arr
    from astropy.io import fits

    with fits.open(path, memmap=False) as hl:
        hdu = next(h for h in hl if h.data is not None and getattr(h.data, "ndim", 0) >= 2)
        arr = np.asarray(hdu.data, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr.mean(axis=0)
    if arr.max() <= 1.0 + 1e-6:
        arr = arr * FULL_SCALE
    return arr


@dataclass
class FrameStats:
    median: float
    mean: float
    mad: float
    min: float
    max: float
    saturated_frac: float
    zero_rows_frac: float
    zero_cols_frac: float
    spots: int = 0  # star-like spots (darks and bias only; FR-003)
    structure: float = 0.0  # large-scale level difference across the frame, in units of the noise

    def as_dict(self) -> dict:
        return {k: round(float(v), 6) for k, v in self.__dict__.items()}


def frame_stats(a: np.ndarray, dark: bool = False) -> FrameStats:
    sample = a[::4, ::4]
    med = float(np.median(sample))
    mad = float(np.median(np.abs(sample - med)))
    rows0 = float(np.mean(~a.any(axis=1)))
    cols0 = float(np.mean(~a.any(axis=0)))
    st = FrameStats(
        median=med,
        mean=float(sample.mean()),
        mad=mad,
        min=float(a.min()),
        max=float(a.max()),
        saturated_frac=float(np.mean(sample >= 0.98 * FULL_SCALE)),
        zero_rows_frac=rows0,
        zero_cols_frac=cols0,
    )
    if dark and rows0 < 0.02 and cols0 < 0.02:
        st.spots = star_spots(a)
        st.structure = large_scale_structure(a)
    return st


def _crop(a: np.ndarray, size: int = 2048) -> np.ndarray:
    """The central `size` square: enough area for stars, and bounded time on a 26 MP frame."""
    h, w = a.shape
    y0, x0 = max(0, (h - size) // 2), max(0, (w - size) // 2)
    return a[y0 : y0 + size, x0 : x0 + size]


def star_spots(a: np.ndarray, sigma_k: float = 4.0) -> int:
    """Star-like spots in a dark or bias (light reaching the sensor), FR-003. Single hot pixels are removed with
    a 3×3 median first; what's left is smoothed to the scale of a star and thresholded against its own noise.
    Sensitive to stars of 15 ADU peak on a frame with 5 ADU read noise (see `leak_self_test`)."""
    from scipy import ndimage

    c = _crop(a).astype(np.float32)
    c = ndimage.median_filter(c, size=3)
    c = ndimage.gaussian_filter(c, 1.2)
    bg = ndimage.uniform_filter(c, 31)
    d = c - bg
    noise = float(np.median(np.abs(d - np.median(d)))) * 1.4826
    if noise <= 0:
        return 0
    mask = d > sigma_k * noise
    labels, n = ndimage.label(mask)
    if not n:
        return 0
    areas = ndimage.sum_labels(mask, labels, index=np.arange(1, n + 1))
    return int(np.sum((areas >= 4) & (areas <= 400)))


def large_scale_structure(a: np.ndarray) -> float:
    """The spread of the medians of an 8×8 grid of blocks, in units of the pixel noise (from differences of
    neighbouring pixels, so a gradient doesn't inflate it): a leak or glow shows as a gradient across the frame."""
    h, w = a.shape
    bh, bw = h // 8, w // 8
    if bh < 8 or bw < 8:
        return 0.0
    meds = [
        float(np.median(a[y : y + bh : 2, x : x + bw : 2]))
        for y in range(0, bh * 8, bh)
        for x in range(0, bw * 8, bw)
    ]
    c = _crop(a)
    diff = (c[:, 1:] - c[:, :-1]).astype(np.float32)
    noise = max(float(np.median(np.abs(diff - np.median(diff)))) * 1.4826 / np.sqrt(2), 0.5)
    return round((max(meds) - min(meds)) / noise, 2)


def leak_self_test(a: np.ndarray, peak: float = 15.0, n: int = 12, seed: int = 0) -> bool:
    """FR-003 self-test: inject `n` synthetic stars of `peak` ADU into a copy of a real dark and check
    `star_spots` finds most of them."""
    rng = np.random.default_rng(seed)
    c = _crop(a).astype(np.float32).copy()
    base = star_spots(c)
    h, w = c.shape
    yy, xx = np.mgrid[-6:7, -6:7]
    psf = peak * np.exp(-(xx**2 + yy**2) / (2 * 1.3**2))
    for _ in range(n):
        y, x = int(rng.integers(20, h - 20)), int(rng.integers(20, w - 20))
        c[y - 6 : y + 7, x - 6 : x + 7] += psf
    return star_spots(c) - base >= n * 0.75


def qa_set(kind: str, stats: dict[str, FrameStats]) -> dict[str, tuple[str, str]]:
    """{key: (verdict, reason)} for every frame of one set, against the set's robust median (spec 002 FR-002)."""
    if not stats:
        return {}
    meds = np.array([s.median for s in stats.values()])
    set_med = float(np.median(meds))
    spread = float(np.median(np.abs(meds - set_med))) * 1.4826
    out: dict[str, tuple[str, str]] = {}
    for key, s in stats.items():
        if s.zero_rows_frac > 0.02 or s.zero_cols_frac > 0.02:
            pct = round(max(s.zero_rows_frac, s.zero_cols_frac) * 100)
            out[key] = ("reject", f"Truncated readout: {pct}% of rows are zero. Not used.")
            continue
        dev = s.median - set_med
        limit = max(5 * spread, 0.02 * set_med, 3.0)
        notes = []
        verdict = "pass"
        if abs(dev) > limit:
            verdict = "warn"
            notes.append(f"Level {s.median:.0f} ADU ({dev:+.0f} vs set {set_med:.0f}).")
        if kind in ("flat",):
            level = s.median / FULL_SCALE
            if level < 0.1 or level > 0.85:
                verdict = "warn"
                notes.append(f"{level:.0%} of full scale (aim 30–60%).")
            if s.saturated_frac > 0.01:
                verdict = "warn"
                notes.append(f"{s.saturated_frac:.1%} of pixels saturated.")
        if kind in ("dark", "bias", "dark_flat"):
            spots = [x.spots for x in stats.values()]
            typical = float(np.median(spots))
            if s.spots > max(25, 8 * typical):  # plainly stars: every light it touched would gain them
                verdict = "reject"
                notes.append(f"{s.spots} spots (typical {typical:.0f}): light leak. Not used.")
            elif s.spots > max(10, 3 * typical):
                verdict = "warn"
                notes.append(f"{s.spots} spots (typical {typical:.0f}): possible light leak.")
            structures = [x.structure for x in stats.values()]
            if s.structure > max(8.0, 2 * float(np.median(structures))):
                verdict = "warn"
                notes.append(
                    f"Uneven level ({s.structure:.0f}× noise, set "
                    f"{float(np.median(structures)):.0f}×): light leak or glow?"
                )
        out[key] = (verdict, " ".join(notes))  # nothing to say about a good frame
    return out


def _superpixels(a: np.ndarray) -> np.ndarray:
    """A Bayer mosaic as 2×2 superpixels, so the analysis sees illumination rather than the colour pattern."""
    h, w = (a.shape[0] // 2) * 2, (a.shape[1] // 2) * 2
    return a[:h, :w].reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))


def flat_report(a: np.ndarray, cfa: bool = False) -> dict:
    """Centre-to-corner falloff per corner, a radial profile, and dust motes (spec 002 FR-006). Positions and
    sizes are in the master's pixels."""
    return flat_analysis(a, cfa)[0]


def flat_analysis(a: np.ndarray, cfa: bool = False) -> tuple[dict, np.ndarray | None]:
    """The flat report and the dust map: the flat divided by its own smooth illumination, in which dust shows as
    dark rings and spots whatever the vignetting does."""
    from scipy import ndimage

    full_h = a.shape[0]
    if cfa:
        a = _superpixels(a)
    h, w = a.shape
    if min(h, w) < 64:
        return {}, None
    f = min(1.0, 750 / max(h, w))
    small = ndimage.zoom(a, f, order=1) if f < 1 else a.copy()
    sh, sw = small.shape
    cy, cx = sh // 2, sw // 2
    box = max(4, min(sh, sw) // 20)
    centre = float(np.median(small[cy - box : cy + box, cx - box : cx + box]))
    if centre <= 0:
        return {}, None
    corners = {
        "top_left": small[: 2 * box, : 2 * box],
        "top_right": small[: 2 * box, -2 * box :],
        "bottom_left": small[-2 * box :, : 2 * box],
        "bottom_right": small[-2 * box :, -2 * box :],
    }
    # FITS rows run bottom-up: "top" in the image is the last rows
    falloff = {k: round(1 - float(np.median(v)) / centre, 4) for k, v in corners.items()}
    yy, xx = np.indices(small.shape)
    r = np.hypot(yy - cy, xx - cx)
    bins = np.linspace(0, r.max(), 21)
    idx = np.digitize(r.ravel(), bins) - 1
    vals = small.ravel() / centre
    profile = [round(float(np.median(vals[idx == i])), 4) for i in range(20) if np.any(idx == i)]
    # dust: the flat against a running median wider than a mote, smoothed to beat the noise
    bg = ndimage.median_filter(small, size=41, mode="reflect")
    ratio = small / np.maximum(bg, 1e-6)
    rs = ndimage.gaussian_filter(ratio, 2.0)
    m = max(2, sh // 20)  # the frame's edge belongs to the vignetting
    core = rs[m:-m, m:-m]
    noise = float(np.median(np.abs(core - np.median(core)))) * 1.4826
    floor = max(0.003, 5 * noise)
    mask = rs < 1 - floor
    mask[:m] = mask[-m:] = False
    mask[:, :m] = mask[:, -m:] = False
    mask = ndimage.binary_opening(mask, iterations=1)
    labels, n = ndimage.label(mask)
    motes = []
    scale = full_h / sh
    if n:
        for i, sl in enumerate(ndimage.find_objects(labels), start=1):
            region = labels[sl] == i
            area = int(region.sum())
            if area < 6 or area > 0.02 * sh * sw:  # specks, or a broad shadow that's vignetting, not dust
                continue
            ys, xs = np.nonzero(region)
            motes.append(
                {
                    "x": round(float((xs.mean() + sl[1].start) * scale)),
                    "y": round(float((ys.mean() + sl[0].start) * scale)),
                    "diameter_px": round(float(2 * np.sqrt(area / np.pi) * scale)),
                    "depth": round(1 - float(rs[sl][region].min()), 4),
                }
            )
    motes.sort(key=lambda mo: -mo["depth"])
    edge = round(1 - float(np.median(vals[idx == len(profile) - 1])), 4) if profile else None
    report = {
        "centre_adu": round(centre, 1),
        "falloff": falloff,
        "mean_falloff": round(float(np.mean(list(falloff.values()))), 4),
        "edge_falloff": edge,
        "radial_profile": profile,
        "dust_motes": motes[:200],
        "dust_mote_count": len(motes),
        "mote_threshold": round(floor, 4),
    }
    return report, ratio


def render_dust_map(ratio: np.ndarray, motes: list[dict], full_h: int, out: Path) -> None:
    """The dust map (flat ÷ its smooth illumination) on a fixed scale, 0.95 to 1.02, with the motes circled."""
    from PIL import Image, ImageDraw

    sh, sw = ratio.shape
    k = max(1, round(1400 / sw))
    img = (np.clip((ratio - 0.95) / 0.07, 0, 1) * 255).astype(np.uint8)
    pic = (
        Image.fromarray(np.ascontiguousarray(np.flipud(img)), mode="L")
        .convert("RGB")
        .resize((sw * k, sh * k))
    )
    draw = ImageDraw.Draw(pic)
    f = full_h / sh
    for mo in motes:
        cx, cy = mo["x"] / f * k, (sh - mo["y"] / f) * k
        rr = mo["diameter_px"] / f * k / 2 + 3 * k
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(238, 123, 208), width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    pic.save(out, quality=88)


def render_array(
    a: np.ndarray, out: Path, width: int = 1400, motes: list[dict] | None = None, thumb: Path | None = None
) -> None:
    """An auto-stretched JPEG of an array (bottom-up FITS order), optionally with dust motes circled."""
    from PIL import Image, ImageDraw

    from .previews import _bin, _mtf, stretch_params

    small = _bin(a, width)
    lo, m, span = stretch_params(small)  # type: ignore[misc]
    x = np.clip((small - lo) / max(span, 1e-9), 0, 1)
    img = np.flipud((np.clip(_mtf(x, m), 0, 1) * 255).astype(np.uint8))
    pic = Image.fromarray(img, mode="L").convert("RGB")
    if motes:
        f = a.shape[1] / small.shape[1]
        draw = ImageDraw.Draw(pic)
        hgt = small.shape[0]
        for mo in motes:
            cx, cy = mo["x"] / f, hgt - mo["y"] / f
            rr = max(6, mo["diameter_px"] / f / 2 + 4)
            draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(238, 123, 208), width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    pic.save(out, quality=85)
    if thumb is not None:
        t = pic.copy()
        t.thumbnail((320, 320))
        t.save(thumb, quality=80)


def compare_masters(new: np.ndarray, old: np.ndarray, flat: bool) -> tuple[dict, np.ndarray] | None:
    """FR-007: a new master against the previous one of the same kind. Flats as a ratio of the two (each
    normalised by its median), so new dust shows as dark rings and lost dust as bright; darks and bias as a
    difference. Returns a summary and the image to show, or None when the frames don't line up."""
    if new.shape != old.shape:
        return None
    if flat:
        img = (new / max(float(np.median(new)), 1e-6)) / np.maximum(
            old / max(float(np.median(old)), 1e-6), 1e-6
        )
        centre = 1.0
    else:
        img = new - old
        centre = 0.0
    sample = img[::4, ::4]
    med = float(np.median(sample))
    spread = float(np.median(np.abs(sample - med))) * 1.4826
    p01, p99 = (float(x) for x in np.percentile(sample, [0.1, 99.9]))
    summary = {
        "kind": "ratio" if flat else "difference",
        "median": round(med, 5),
        "spread": round(spread, 5),
        "p0_1": round(p01, 5),
        "p99_9": round(p99, 5),
    }
    if flat:
        summary["level_change"] = round(med - centre, 5)
        motes = flat_report(img * 20000.0).get("dust_motes", []) if min(img.shape) >= 64 else []
        summary["changed_spots"] = len(motes)
    else:
        summary["level_change_adu"] = round(med, 2)
    return summary, img
