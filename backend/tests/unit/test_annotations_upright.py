"""Master labels are turned to match the preview when the catalogue's stars only line up mirrored (2026-10-22)."""

from __future__ import annotations

import numpy as np
from PIL import Image

from apps.processing.annotations import upright


def _preview(tmp_path, stars):  # noqa: ANN001, ANN202
    g = np.full((400, 300), 20, np.uint8)
    for u, v in stars:
        y, x = int(v * 400), int(u * 300)
        g[y - 2 : y + 3, x - 2 : x + 3] = 250
    p = tmp_path / "master.jpg"
    Image.fromarray(g).save(p)
    return str(p)


LABELS = [
    {"name": "zet Ori A", "kind": "star", "mag": 1.9, "u": 0.3, "v": 0.2},
    {"name": "sig Ori", "kind": "star", "mag": 3.8, "u": 0.6, "v": 0.35},
    {"name": "NGC 2024", "kind": "ngc", "mag": None, "u": 0.35, "v": 0.1},
]


def test_labels_already_on_their_stars_stay(tmp_path):
    assert upright(LABELS, _preview(tmp_path, [(0.3, 0.2), (0.6, 0.35)])) == LABELS


def test_labels_whose_stars_only_line_up_mirrored_are_turned(tmp_path):
    out = upright(LABELS, _preview(tmp_path, [(0.3, 0.8), (0.6, 0.65)]))
    assert [round(o["v"], 2) for o in out] == [0.8, 0.65, 0.9]  # every label, not only the stars


def test_too_few_stars_or_no_preview_changes_nothing(tmp_path):
    assert upright(LABELS[1:], _preview(tmp_path, [])) == LABELS[1:]
    assert upright(LABELS, None) == LABELS
