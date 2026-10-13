"""Synthetic images for engine tests: a flat background with Gaussian stars and noise."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.io import fits


def star_field(
    path: Path,
    n: int = 150,
    fwhm: float = 3.0,
    background: float = 1000.0,
    seed: int = 1,
    size: int = 512,
    elongation: float = 1.0,
    header: dict | None = None,
    field_seed: int | None = None,
    shift: tuple[float, float] = (0.0, 0.0),
) -> Path:
    """`field_seed` fixes the star positions (one sky), so several subs of it can be registered; `shift` moves
    the pointing a little; `n` keeps only the brightest n stars of a 200-star field (cloud dims the rest)."""
    field = np.random.default_rng(seed if field_seed is None else field_seed)
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    img = np.full((size, size), background, dtype=np.float64)
    sigma = fwhm / 2.3548
    total = max(n, 200) if field_seed is not None else n
    stars = [(*field.uniform(20, size - 20, 2), field.uniform(2000, 20000)) for _ in range(total)]
    stars.sort(key=lambda s: -s[2])
    for x, y, a in stars[:n]:
        x, y = x + shift[0], y + shift[1]
        img += a * np.exp(-(((xx - x) / (sigma * elongation)) ** 2 + ((yy - y) / sigma) ** 2) / 2)
    img += rng.normal(0, 10, img.shape)
    hdr = fits.Header()
    for k, v in (header or {}).items():
        hdr[k] = v
    fits.PrimaryHDU(np.clip(img, 0, 65535).astype(np.uint16), header=hdr).writeto(path, overwrite=True)
    return path


def flat_field(path: Path, level: float = 20000.0, size: int = 512, seed: int = 2) -> Path:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    r2 = ((xx - size / 2) ** 2 + (yy - size / 2) ** 2) / (size / 2) ** 2
    img = level * (1 - 0.05 * r2) + rng.normal(0, 30, (size, size))
    fits.PrimaryHDU(img.astype(np.uint16)).writeto(path, overwrite=True)
    return path


def dark_field(path: Path, level: float = 300.0, size: int = 512, seed: int = 3) -> Path:
    rng = np.random.default_rng(seed)
    fits.PrimaryHDU((level + rng.normal(0, 5, (size, size))).astype(np.uint16)).writeto(path, overwrite=True)
    return path
