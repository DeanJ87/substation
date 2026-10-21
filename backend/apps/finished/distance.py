"""A target's distance from SIMBAD (020-DR-13), only when the owner asks: the median of the published measurements
for the first of the target's designations SIMBAD knows. Nothing here runs while rendering."""

from __future__ import annotations

import json
import statistics
import urllib.parse
import urllib.request

SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
LY_PER_PC = 3.261563777
_UNITS = {"pc": 1.0, "kpc": 1e3, "mpc": 1e6}


class LookupFailed(Exception):
    pass


def _fetch(designation: str) -> list[list]:
    q = (
        "SELECT m.dist, m.unit FROM mesDistance AS m JOIN ident AS i ON m.oidref = i.oidref "
        f"WHERE i.id = '{designation.replace(chr(39), chr(39) * 2)}'"
    )
    params = urllib.parse.urlencode({"request": "doQuery", "lang": "adql", "format": "json", "query": q})
    try:
        with urllib.request.urlopen(f"{SIMBAD_TAP}?{params}", timeout=15) as r:  # noqa: S310 (fixed https host)
            return json.load(r).get("data") or []
    except (OSError, ValueError) as e:
        raise LookupFailed("SIMBAD couldn't be reached.") from e


def lookup(designations: list[str]) -> tuple[float, str] | None:
    """(light years, source) from the first designation with measurements, or None if SIMBAD has none."""
    for name in designations:
        pcs = []
        for dist, unit in _fetch(name):
            scale = _UNITS.get(str(unit).strip().lower())
            if dist and scale:
                pcs.append(float(dist) * scale)
        if pcs:
            n = len(pcs)
            return statistics.median(
                pcs
            ) * LY_PER_PC, f"SIMBAD: {name}, median of {n} measurement{'s' * (n != 1)}"
    return None
