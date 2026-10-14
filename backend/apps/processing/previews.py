"""Previews (spec 003 FR-007): an auto-stretched JPEG for the screen and a small one for tiles, made from the
calibrated FITS. Stretch: a midtones transfer function placing the median at 25% grey, shadows clipped at
median − 2.8·MAD (the usual screen-transfer default)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

SCREEN = 1400
THUMB = 320


def _bin(data: np.ndarray, width: int) -> np.ndarray:
    h, w = data.shape[-2:]
    f = max(1, int(np.ceil(w / width)))
    h2, w2 = (h // f) * f, (w // f) * f
    return data[:h2, :w2].reshape(h2 // f, f, w2 // f, f).mean(axis=(1, 3))


def stretch_params(data: np.ndarray) -> tuple[float, float, float]:
    sample = data[:: max(1, data.shape[0] // 512), :: max(1, data.shape[1] // 512)]
    lo, hi = np.percentile(sample, [0.01, 99.999])
    span = max(hi - lo, 1e-9)
    norm = np.clip((sample - lo) / span, 0, 1)
    med = float(np.median(norm))
    mad = float(np.median(np.abs(norm - med))) * 1.4826
    shadows = max(0.0, med - 2.8 * mad)
    m = (med - shadows) / max(1e-9, 1 - shadows)
    target = 0.25
    midtones = (target - 1) * m / ((2 * target - 1) * m - target) if m > 0 else 0.5
    return float(lo + shadows * span), float(midtones), float(span * (1 - shadows))


def _mtf(x: np.ndarray, m: float) -> np.ndarray:
    return ((m - 1) * x) / ((2 * m - 1) * x - m)


def _stretch8(small: np.ndarray, params: tuple[float, float, float] | None = None) -> np.ndarray:
    lo, m, span = params or stretch_params(small)  # type: ignore[misc]
    x = np.clip((small - lo) / max(span, 1e-9), 0, 1)
    return (np.clip(_mtf(x, m), 0, 1) * 255).astype(np.uint8)


def session_stretch(session: Path, own: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    """One stretch for a dataset's session (003 G18): each sub adds its own parameters (per plane) to the session's
    file, and every preview uses their median, so a cloudy sub looks darker beside the others instead of being
    stretched to look the same. The latest 60 subs count."""
    import json

    try:
        seen = json.loads(session.read_text()) if session.exists() else []
    except (OSError, ValueError):
        seen = []
    seen = [x for x in seen if len(x) == len(own)][-59:] + [[list(p) for p in own]]
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text(json.dumps(seen))
    return [tuple(float(np.median([s[i][k] for s in seen])) for k in range(3)) for i in range(len(own))]  # type: ignore[misc]


def superpixel(data: np.ndarray, pattern: str) -> np.ndarray | None:
    """A one-shot-colour mosaic as RGB at half size: each 2×2 cell gives one pixel. The pattern (RGGB, GRBG, ...)
    reads in the order the rows are stored, as NINA, ASIAIR and the Seestar write it."""
    pat = pattern.strip().upper()
    if len(pat) != 4 or sorted(pat) != ["B", "G", "G", "R"]:
        return None
    h, w = (data.shape[0] // 2) * 2, (data.shape[1] // 2) * 2
    cells = [data[0:h:2, 0:w:2], data[0:h:2, 1:w:2], data[1:h:2, 0:w:2], data[1:h:2, 1:w:2]]
    by = {c: [cells[i] for i, x in enumerate(pat) if x == c] for c in "RGB"}
    return np.stack([by["R"][0], (by["G"][0] + by["G"][1]) / 2, by["B"][0]])


def _read_fits(fits_path: Path) -> tuple[np.ndarray, Any]:
    """Pixels as float32 and the header. Memory-mapped where astropy can; scaled integer data (BZERO/BSCALE, as
    some cameras' 16-bit FITS carry) can't be mapped, so it is read in full instead."""
    from astropy.io import fits

    try:
        with fits.open(fits_path, memmap=True) as hl:
            return np.asarray(hl[0].data, dtype=np.float32), hl[0].header
    except ValueError:
        with fits.open(fits_path, memmap=False) as hl:
            return np.asarray(hl[0].data, dtype=np.float32), hl[0].header


def screen_planes(fits_path: Path, raw: bool = False) -> tuple[list[np.ndarray], str, bool]:
    """The image binned to screen size: (planes, "RGB" or "L", whether to flip rows for display)."""

    data, header = _read_fits(fits_path)
    if data.ndim == 2 and header.get("BAYERPAT"):
        rgb = superpixel(data, str(header["BAYERPAT"]))
        if rgb is not None:
            data = rgb
    if data.ndim == 3 and data.shape[0] == 3:  # colour: each channel stretched on its own, which also
        planes, mode = [_bin(c, SCREEN) for c in data], "RGB"  # neutralises the background
    else:
        planes, mode = [_bin(data[0] if data.ndim == 3 else data, SCREEN)], "L"
    flip = not (raw and str(header.get("ROWORDER", "")).upper() == "TOP-DOWN")  # Siril writes FITS bottom-up
    return planes, mode, flip


def render(
    fits_path: Path,
    out_screen: Path,
    out_thumb: Path,
    raw: bool = False,
    session: Path | None = None,
    params: list[tuple[float, float, float]] | None = None,
) -> None:
    """`raw`: the file is a capture, not Siril's output, so a colour mosaic is debayered here and a top-down file
    is already the right way up. `session` adds this sub to its session's stretch and uses the session's;
    `params` gives the stretch outright (a whole session redrawn at once)."""
    from PIL import Image

    planes, mode, flip = screen_planes(fits_path, raw)
    if params is None:
        params = [stretch_params(pl) for pl in planes]
        if session is not None:
            params = session_stretch(session, params)
    out = [_stretch8(pl, pr) for pl, pr in zip(planes, params, strict=True)]
    img = np.stack(out, axis=-1) if mode == "RGB" else out[0]
    if flip:
        img = np.flipud(img)
    img = np.ascontiguousarray(img)
    out_screen.parent.mkdir(parents=True, exist_ok=True)
    pic = Image.fromarray(img, mode=mode)
    pic.save(out_screen, quality=85)
    t = pic.copy()
    t.thumbnail((THUMB, THUMB))
    t.save(out_thumb, quality=80)


def _load_display(fits_path: Path, raw: bool) -> tuple[np.ndarray, bool]:
    """The image as shown (colour planes or grey, top row first) in float32; and whether it is colour."""

    if fits_path.suffix.lower() == ".xisf":  # stored top row first, channels last
        import xisf

        arr = np.asarray(xisf.XISF(str(fits_path)).read_image(0), dtype=np.float32)
        if arr.ndim == 3 and arr.shape[2] == 3:
            return np.moveaxis(arr, 2, 0), True
        return (arr[:, :, 0] if arr.ndim == 3 else arr), False

    data, header = _read_fits(fits_path)
    if data.ndim == 2 and header.get("BAYERPAT"):
        rgb = superpixel(data, str(header["BAYERPAT"]))
        if rgb is not None:
            data = rgb
    colour = data.ndim == 3 and data.shape[0] == 3
    if data.ndim == 3 and not colour:
        data = data[0]
    if not (raw and str(header.get("ROWORDER", "")).upper() == "TOP-DOWN"):
        data = data[..., ::-1, :]  # Siril writes FITS bottom-up
    return data, colour


def _stretch_full(
    data: np.ndarray, colour: bool, params: list[tuple[float, float, float]] | None = None
) -> np.ndarray:
    """8-bit, stretched with parameters from a binned copy (as the preview), applied at full resolution; or with
    `params` given (a post-processed stage drawn with its master's stretch, so versions compare fairly)."""
    planes = data if colour else data[None]
    out = []
    for i, c in enumerate(planes):
        lo, m, span = params[min(i, len(params) - 1)] if params else stretch_params(_bin(c, SCREEN))  # type: ignore[misc]
        x = np.clip((c - lo) / max(span, 1e-9), 0, 1)
        out.append((np.clip(_mtf(x, m), 0, 1) * 255).astype(np.uint8))
    return np.ascontiguousarray(np.stack(out, axis=-1) if colour else out[0])


def full_and_inspector(
    fits_path: Path,
    out_full: Path,
    out_inspect: Path,
    raw: bool = False,
    tile: int = 320,
    params: list[tuple[float, float, float]] | None = None,
) -> None:
    """For checking a sub at 100% (owner 2026-10-10): the whole sub at full resolution, and an aberration
    inspector: nine full-resolution crops (corners, edge middles, centre) in a 3×3 grid, so elongated or soft
    stars in one corner (tilt, spacing, coma) stand out from ones elongated everywhere (tracking, wind)."""
    from PIL import Image

    data, colour = _load_display(fits_path, raw)
    img = _stretch_full(data, colour, params)
    mode = "RGB" if colour else "L"
    out_full.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img, mode=mode).save(out_full, quality=78)
    h, w = img.shape[:2]
    t = min(tile, h // 3, w // 3)
    gap = 6
    grid = Image.new(mode, (3 * t + 2 * gap, 3 * t + 2 * gap))
    for r, y in enumerate((0, (h - t) // 2, h - t)):
        for c, x in enumerate((0, (w - t) // 2, w - t)):
            grid.paste(
                Image.fromarray(np.ascontiguousarray(img[y : y + t, x : x + t]), mode=mode),
                (c * (t + gap), r * (t + gap)),
            )
    grid.save(out_inspect, quality=92)


def palette_and_inspector(
    channels: dict[str, Path], out_full: Path, out_inspect: Path, out_screen: Path, tile: int = 320
) -> None:
    """A palette image (HOO, SHO) from registered mono masters: each channel's master stretched on its own and
    placed in red, green or blue (`channels` maps "r", "g", "b" to a file; one file may feed two channels). Writes
    the full-resolution view, its aberration inspector and a screen-size preview."""
    from PIL import Image

    planes = {}
    cache: dict[Path, np.ndarray] = {}
    for ch in "rgb":
        p = channels[ch]
        if p not in cache:
            data, colour = _load_display(p, raw=False)
            cache[p] = _stretch_full(data.mean(axis=0) if colour else data, False)
        planes[ch] = cache[p]
    h = min(x.shape[0] for x in planes.values())
    w = min(x.shape[1] for x in planes.values())
    img = np.ascontiguousarray(np.stack([planes[c][:h, :w] for c in "rgb"], axis=-1))
    out_full.parent.mkdir(parents=True, exist_ok=True)
    pic = Image.fromarray(img, mode="RGB")
    pic.save(out_full, quality=82)
    small = pic.copy()
    small.thumbnail((SCREEN, SCREEN))
    small.save(out_screen, quality=85)
    t = min(tile, h // 3, w // 3)
    gap = 6
    grid = Image.new("RGB", (3 * t + 2 * gap, 3 * t + 2 * gap))
    for r, y in enumerate((0, (h - t) // 2, h - t)):
        for c, x in enumerate((0, (w - t) // 2, w - t)):
            grid.paste(
                Image.fromarray(np.ascontiguousarray(img[y : y + t, x : x + t]), mode="RGB"),
                (c * (t + gap), r * (t + gap)),
            )
    grid.save(out_inspect, quality=92)


def master_stretch(fits_path: Path) -> list[tuple[float, float, float]]:
    """A master's own stretch, per plane (owner 2026-10-12: NoiseXTerminator's cleaner sky made each stage's own
    auto-stretch far harsher, turning sub-1% residuals into dark blotches; stages are drawn with this instead)."""
    planes, _mode, _flip = screen_planes(fits_path, False)
    return [stretch_params(pl) for pl in planes]


def plane_backgrounds(fits_path: Path) -> list[float]:
    """Each plane's sky level (median of the screen-size image)."""
    planes, _mode, _flip = screen_planes(fits_path, False)
    return [float(np.median(pl)) for pl in planes]


def shifted_stretch(
    params: list[tuple[float, float, float]], master_bg: list[float], stage_bg: list[float]
) -> list[tuple[float, float, float]]:
    """The master's stretch for a processed stage, each plane's black point moved by how much that plane's sky
    changed. Strength and range stay the master's, so versions still compare like for like; but a stage whose
    gradient was removed (GraXpert) isn't drawn against the master's old per-channel black points, which crushed
    the channel that had the most light pollution (green) and turned OSC stages purple (owner 2026-10-14)."""
    if len(master_bg) != len(params) or len(stage_bg) != len(params):
        return params
    return [
        (lo + (sb - mb), m, span) for (lo, m, span), mb, sb in zip(params, master_bg, stage_bg, strict=True)
    ]


def glance(src: Path, out: Path, width: int = 480) -> None:
    """A small stretched JPEG of any frame, for hover previews (owner 2026-10-11).
    Binned straight down to about `width` pixels, so a 24 MP file takes well under a second."""
    from PIL import Image

    data, colour = _load_display(src, raw=True)
    planes = data if colour else data[None]
    small = [_bin(c, width) for c in planes]
    out8 = []
    for c in small:
        lo, m, span = stretch_params(c)  # type: ignore[misc]
        x = np.clip((c - lo) / max(span, 1e-9), 0, 1)
        out8.append((np.clip(_mtf(x, m), 0, 1) * 255).astype(np.uint8))
    img = np.stack(out8, axis=-1) if colour else out8[0]
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(img)).save(out, quality=80)
