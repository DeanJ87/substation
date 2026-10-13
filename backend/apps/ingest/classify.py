"""Frame classification (research R9; T054, extended in T094). Returns the type and a plain-English reason."""

from __future__ import annotations

import re

from apps.catalogue.models import FrameType

from .headers import HeaderResult

_TYPES = {
    "light": FrameType.LIGHT,
    "lightframe": FrameType.LIGHT,
    "science": FrameType.LIGHT,
    "object": FrameType.LIGHT,
    "flat": FrameType.FLAT,
    "flatfield": FrameType.FLAT,
    "flatframe": FrameType.FLAT,
    "dark": FrameType.DARK,
    "darkframe": FrameType.DARK,
    "bias": FrameType.BIAS,
    "biasframe": FrameType.BIAS,
    "offset": FrameType.BIAS,
    "zero": FrameType.BIAS,
    "darkflat": FrameType.DARK_FLAT,
    "flatdark": FrameType.DARK_FLAT,
    "masterdark": FrameType.MASTER_DARK,
    "masterflat": FrameType.MASTER_FLAT,
    "masterbias": FrameType.MASTER_BIAS,
    "masterdarkflat": FrameType.MASTER_DARK_FLAT,
    "masterflatdark": FrameType.MASTER_DARK_FLAT,
    "masterlight": FrameType.MASTER_LIGHT,
    "integration": FrameType.MASTER_LIGHT,
}
_TO_MASTER = {
    FrameType.LIGHT: FrameType.MASTER_LIGHT,
    FrameType.DARK: FrameType.MASTER_DARK,
    FrameType.FLAT: FrameType.MASTER_FLAT,
    FrameType.BIAS: FrameType.MASTER_BIAS,
    FrameType.DARK_FLAT: FrameType.MASTER_DARK_FLAT,
}


def normalise_type(raw: object) -> FrameType | None:
    if raw is None:
        return None
    key = re.sub(r"[\s\-_]", "", str(raw).casefold())
    return _TYPES.get(key)


def classify(res: HeaderResult, imagetyp: object, imagetyp_source: str) -> tuple[FrameType, str]:
    """Type from IMAGETYP (or XISF imageType); multi-image XISF with an `integration` image is a master."""
    return classify_type(imagetyp, imagetyp_source, res.integration_index() is not None)


def classify_type(imagetyp: object, imagetyp_source: str, has_integration: bool) -> tuple[FrameType, str]:
    t = normalise_type(imagetyp)
    if t is None:
        if has_integration:
            return FrameType.UNKNOWN, ("Master with no frame type in the header.")
        if imagetyp in (None, ""):
            return FrameType.UNKNOWN, "No IMAGETYP in the header."
        return FrameType.UNKNOWN, f"Unknown IMAGETYP '{imagetyp}'."
    if has_integration and t in _TO_MASTER:
        t = _TO_MASTER[t]
        return t, f"{imagetyp_source} = '{imagetyp}' and the file holds an integration image (WBPP master)."
    return t, f"{imagetyp_source} = '{imagetyp}'."
