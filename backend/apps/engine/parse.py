"""Reading Siril's output: command logs, star lists and sequence files."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from pathlib import Path

FOUND = re.compile(r"Found (\d+) .*?FWHM ([\d.]+)")
BGNOISE = re.compile(r"Background noise value \(channel: #0\): ([\d.eE+\-]+)")
STAT = re.compile(r"Mean: ([\d.eE+\-]+), Median: ([\d.eE+\-]+), Sigma: ([\d.eE+\-]+)")


def found_stars(log: list[str]) -> tuple[int, float | None]:
    for line in log:
        m = FOUND.search(line)
        if m:
            return int(m.group(1)), float(m.group(2))
    return 0, None


def bgnoise(log: list[str]) -> float | None:
    for line in log:
        m = BGNOISE.search(line)
        if m:
            return float(m.group(1))
    return None


def stat(log: list[str]) -> tuple[float, float, float] | None:
    for line in log:
        m = STAT.search(line)
        if m:
            return float(m.group(1)), float(m.group(2)), float(m.group(3))
    return None


@dataclass
class Star:
    x: float
    y: float
    fwhm_x: float
    fwhm_y: float
    amplitude: float


def star_list(path: Path) -> list[Star]:
    """A `findstar -out=` list: tab-separated, '#' comments; columns star#, layer, B, A, beta, X, Y, FWHMx,
    FWHMy, … (FWHM in px)."""
    stars: list[Star] = []
    if not path.exists():
        return stars
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        c = line.split()
        try:
            stars.append(
                Star(
                    x=float(c[5]),
                    y=float(c[6]),
                    fwhm_x=float(c[7]),
                    fwhm_y=float(c[8]),
                    amplitude=float(c[3]),
                )
            )
        except (IndexError, ValueError):
            continue
    return stars


def roundness(stars: list[Star]) -> float | None:
    """Median minor/major FWHM ratio (1.0 is perfectly round)."""
    r = [min(s.fwhm_x, s.fwhm_y) / max(s.fwhm_x, s.fwhm_y) for s in stars if s.fwhm_x > 0 and s.fwhm_y > 0]
    return statistics.median(r) if r else None


def median_fwhm(stars: list[Star]) -> float | None:
    v = [(s.fwhm_x + s.fwhm_y) / 2 for s in stars if s.fwhm_x > 0 and s.fwhm_y > 0]
    return statistics.median(v) if v else None


def seq_images(path: Path) -> list[dict]:
    """A Siril `.seq` file's images in sequence order: `I <filenum> <included>` lines, with registration data
    (`R<layer>` lines: fwhm, wfwhm, roundness, quality, background, nstars) when present."""
    images: list[dict] = []
    regs: list[dict] = []
    if not path.exists():
        return images
    for line in path.read_text().splitlines():
        if line.startswith("I "):
            p = line.split()
            images.append({"filenum": int(p[1]), "included": p[2] == "1"})
        elif re.match(r"R\d ", line):
            p = line.split()
            try:
                regs.append(
                    {
                        "fwhm": float(p[1]),
                        "wfwhm": float(p[2]),
                        "roundness": float(p[3]),
                        "quality": float(p[4]),
                        "background": float(p[5]),
                        "nstars": int(p[6]),
                    }
                )
            except (IndexError, ValueError):
                regs.append({})
    for i, im in enumerate(images):
        if i < len(regs):
            im["reg"] = regs[i]
    return images


def regional(stars: list[Star], width: int, height: int) -> dict:
    """FWHM and roundness in the centre and each corner (the outer 25% of each side), and a tilt note when one
    corner is clearly softer than the opposite one (spec 004 FR-007)."""

    def stats(sel: list[Star]) -> dict | None:
        if len(sel) < 5:
            return None
        return {
            "fwhm_px": round(median_fwhm(sel) or 0, 2),
            "roundness": round(roundness(sel) or 0, 3),
            "stars": len(sel),
        }

    qx, qy = width * 0.25, height * 0.25
    zones = {
        "centre": [
            s for s in stars if qx * 1.5 <= s.x <= width - qx * 1.5 and qy * 1.5 <= s.y <= height - qy * 1.5
        ],
        # Siril's star lists measure y from the top, as the image is shown (constitution, Data and Engine
        # Constraints); these were swapped until 2026-10-12, so "top left" named the bottom left
        "top_left": [s for s in stars if s.x < qx and s.y < qy],
        "top_right": [s for s in stars if s.x > width - qx and s.y < qy],
        "bottom_left": [s for s in stars if s.x < qx and s.y > height - qy],
        "bottom_right": [s for s in stars if s.x > width - qx and s.y > height - qy],
    }
    out = {k: stats(v) for k, v in zones.items()}
    return {"zones": out, "tilt_note": tilt_note(out)}


def tilt_note(out: dict) -> str:
    corners = {k: v["fwhm_px"] for k, v in out.items() if k != "centre" and v}
    note = ""
    if len(corners) == 4:
        worst = max(corners, key=lambda k: corners[k])
        opposite = {
            "top_left": "bottom_right",
            "top_right": "bottom_left",
            "bottom_left": "top_right",
            "bottom_right": "top_left",
        }[worst]
        if corners[worst] > 1.25 * corners[opposite]:
            note = (
                f"The {worst.replace('_', ' ')} corner is {round((corners[worst] / corners[opposite] - 1) * 100)}% "
                f"softer than {opposite.replace('_', ' ')}: tilt or spacing?"
            )
    return note
