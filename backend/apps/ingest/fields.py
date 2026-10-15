"""Header field extraction and normalisation (T053). Keyword maps cover NINA, PixInsight WBPP and common FITS
writers. Each value keeps the raw text and the keyword it came from (constitution II: source recorded)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .headers import ImageHeader
from .night import parse_date_obs

# field -> keyword names in order of preference
KEYWORDS: dict[str, tuple[str, ...]] = {
    "object": ("OBJECT",),
    "filter": ("FILTER",),
    "exptime": ("EXPTIME", "EXPOSURE"),
    "ccd_temp": ("CCD-TEMP", "CCD_TEMP"),
    "set_temp": ("SET-TEMP", "SET_TEMP"),
    "gain": ("GAIN", "ISOSPEED", "ISO"),  # DSLRs (Sony A7 III) write ISO instead: it plays the same role
    "offset": ("OFFSET",),
    "xbin": ("XBINNING",),
    "ybin": ("YBINNING",),
    "camera": ("INSTRUME", "CREATOR"),  # Seestar writes no INSTRUME; CREATOR names the device
    "telescope": ("TELESCOP",),
    "date_obs": ("DATE-OBS", "DATE-BEG"),
    "site_lat": ("SITELAT", "LAT-OBS", "OBSGEO-B"),
    "site_lon": ("SITELONG", "LONG-OBS", "OBSGEO-L"),
    "frame_type": ("IMAGETYP", "FRAMETYP", "FRAME"),
}
# XISF properties used when the FITS keyword is absent
PROPERTIES: dict[str, tuple[str, ...]] = {
    "object": ("Observation:Object:Name",),
    "filter": ("Instrument:Filter:Name",),
    "exptime": ("Instrument:ExposureTime",),
    "ccd_temp": ("Instrument:Sensor:Temperature",),
    "xbin": ("Instrument:Camera:XBinning",),
    "ybin": ("Instrument:Camera:YBinning",),
    "camera": ("Instrument:Camera:Name",),
    "telescope": ("Instrument:Telescope:Name",),
    "date_obs": ("Observation:Time:Start",),
    "site_lat": ("Observation:Location:Latitude",),
    "site_lon": ("Observation:Location:Longitude",),
}
FLOAT_FIELDS = {"exptime", "ccd_temp", "set_temp", "site_lat", "site_lon"}
INT_FIELDS = {"gain", "offset", "xbin", "ybin"}

# Built-in filter names; user aliases (InstallationSettings.filter_aliases) take precedence.
_FILTER_CANON = {
    "ha": "Hα",
    "halpha": "Hα",
    "hydrogenalpha": "Hα",
    "hα": "Hα",
    "oiii": "OIII",
    "o3": "OIII",
    "oxygeniii": "OIII",  # "Oxygen-III", "Oxygen III" (owner 2026-10-13: some captures spell them out)
    "oxygen3": "OIII",
    "sulphurii": "SII",
    "sulfurii": "SII",
    "sulphur2": "SII",
    "sulfur2": "SII",
    "sii": "SII",
    "s2": "SII",
    "hb": "Hβ",
    "hbeta": "Hβ",
    "l": "L",
    "lum": "L",
    "luminance": "L",
    "clear": "L",
    "r": "R",
    "red": "R",
    "g": "G",
    "green": "G",
    "b": "B",
    "blue": "B",
}


def normalise_filter(raw: str | None, aliases: dict[str, str]) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    key = s.casefold()
    if key in aliases:
        return aliases[key]
    compact = re.sub(r"[\s\-_]", "", key)
    if compact in aliases:
        return aliases[compact]
    return _FILTER_CANON.get(compact, s)


@dataclass(frozen=True)
class FieldValue:
    value: Any  # typed, normalised
    raw: str  # original text as found
    source_detail: str  # keyword or property name


def _typed(field: str, value: Any) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if field in FLOAT_FIELDS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if field in INT_FIELDS:
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None
    if field == "date_obs":
        return parse_date_obs(value)
    return str(value).strip()


def _from_keywords(img: ImageHeader, field: str) -> FieldValue | None:
    """The first of the field's FITS keywords present with a usable value, in KEYWORDS order."""
    for name in KEYWORDS[field]:
        kw = img.keywords.get(name)
        if kw is None:
            continue
        typed = _typed(field, kw.value)
        if typed is not None:
            return FieldValue(typed, str(kw.value), name)
    return None


def _from_properties(img: ImageHeader, field: str) -> FieldValue | None:
    """Failing a keyword, the first of the field's XISF properties present with a usable value."""
    for prop in PROPERTIES.get(field, ()):
        if prop in img.properties:
            typed = _typed(field, img.properties[prop])
            if typed is not None:
                return FieldValue(typed, str(img.properties[prop]), prop)
    return None


def extract(img: ImageHeader) -> dict[str, FieldValue]:
    """Header-derived candidate values for each field (only fields actually present)."""
    out: dict[str, FieldValue] = {}
    for field in KEYWORDS:
        got = _from_keywords(img, field)
        if got is None:
            got = _from_properties(img, field)
        if got is not None:
            out[field] = got
    if "frame_type" not in out and img.image_type:
        out["frame_type"] = FieldValue(img.image_type, img.image_type, "XISF imageType")
    if "filter" not in out and is_colour(img):
        # A colour (Bayer) camera with no filter recorded: an unfiltered one-shot-colour sub. The owner can correct
        # it (e.g. to a dual-band filter the software never wrote) and the correction sticks by content.
        out["filter"] = FieldValue("OSC", "", "inferred: colour camera, no filter in the header")
    return out


def is_colour(img: ImageHeader) -> bool:
    """A one-shot-colour sub: a Bayer pattern in the header (BAYERPAT, XISF ColorFilterArray) or three channels."""
    if img.keywords.get("BAYERPAT") or img.keywords.get("COLORTYP"):
        return True
    if any("ColorFilterArray" in k or k.startswith("PCL:CFASourcePattern") for k in img.properties):
        return True
    return len(img.geometry) == 3 and img.geometry[2] == 3
