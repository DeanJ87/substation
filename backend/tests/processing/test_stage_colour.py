"""A processed colour stage is drawn with the master's stretch, each channel's black point following that stage's
own sky: GraXpert removes a green light-pollution glow, and the master's old green black point then crushed green
and turned the stage purple (owner 2026-10-14)."""

from __future__ import annotations

import numpy as np
from astropy.io import fits

from apps.processing.previews import master_stretch, plane_backgrounds, render, shifted_stretch


def colour(path, bg):
    rng = np.random.default_rng(3)
    planes = np.stack([b + rng.normal(0, 0.002, (300, 400)) for b in bg]).astype(np.float32)
    planes[:, 140:160, 190:210] += 0.3  # a star, the same in every channel
    fits.PrimaryHDU(planes).writeto(path)


def sky(jpg) -> np.ndarray:
    from PIL import Image

    a = np.asarray(Image.open(jpg).convert("RGB"), dtype=float)
    return np.median(a[:100, :100].reshape(-1, 3), axis=0)  # a patch of empty sky: R, G, B


def test_a_stage_with_its_glow_removed_keeps_a_neutral_sky(tmp_path):
    master, stage = tmp_path / "m.fits", tmp_path / "s.fits"
    colour(master, (0.10, 0.20, 0.10))  # green light pollution
    colour(stage, (0.10, 0.10, 0.10))  # GraXpert: the green glow gone, a neutral sky
    params = master_stretch(master)
    old = tmp_path / "old.jpg"
    render(stage, old, tmp_path / "old_t.jpg", params=params)
    r, g, b = sky(old)
    assert g < min(r, b) - 20  # the bug: green crushed, the sky purple
    new = tmp_path / "new.jpg"
    render(
        stage,
        new,
        tmp_path / "new_t.jpg",
        params=shifted_stretch(params, plane_backgrounds(master), plane_backgrounds(stage)),
    )
    r, g, b = sky(new)
    assert max(r, g, b) - min(r, g, b) < 8  # neutral
