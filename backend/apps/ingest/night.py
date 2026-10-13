"""Observing night (constitution II): date(UTC start + longitude/15 h − 12 h). Never the host time zone."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta


def parse_date_obs(value: object) -> datetime | None:
    """Parse DATE-OBS variants: NINA writes 7 fractional digits; some writers add Z or use a space."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    s = str(value).strip().rstrip("Z").replace(" ", "T")
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?([+-]\d{2}:?\d{2})?", s)
    if not m:
        return None
    base = datetime.fromisoformat(m.group(1))
    micro = int((m.group(2) or "0")[:6].ljust(6, "0"))
    if m.group(3):  # an explicit offset (as stored values carry): convert to UTC
        off = m.group(3).replace(":", "")
        delta = timedelta(hours=int(off[1:3]), minutes=int(off[3:5]))
        base = base - delta if off[0] == "+" else base + delta
    return base.replace(microsecond=micro, tzinfo=UTC)


def observing_night(utc: datetime, longitude_deg: float) -> date:
    local_mean_time = utc + timedelta(hours=longitude_deg / 15.0)
    return (local_mean_time - timedelta(hours=12)).date()


def site_key(lat: float | None, lon: float | None) -> str:
    """Key for a new site (two decimals of a degree). Existing sites within SAME_SITE_KM are reused instead
    (catalogue.services.grouping.night_for), because any rounding grid splits points near its boundaries."""
    if lat is None or lon is None:
        return "unknown"
    return f"{round(lat, 2):.2f},{round(lon, 2):.2f}"


SAME_SITE_KM = 5.0


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))
