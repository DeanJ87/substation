"""Header readers (research R7): FITS via astropy, XISF via the `xisf` package. Header only: no pixel data
is ever read while cataloguing (FR-003). Errors come back in the result, never as exceptions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

FITS_SUFFIXES = (".fit", ".fits", ".fts")
COMPRESSED_SUFFIXES = (".fz",)
XISF_SUFFIXES = (".xisf",)
IMAGE_SUFFIXES = FITS_SUFFIXES + COMPRESSED_SUFFIXES + XISF_SUFFIXES


def is_image_name(name: str) -> bool:
    """Image file by name: accepted extensions, case-insensitive; AppleDouble and dotfiles never are."""
    if name.startswith("._") or name.startswith("."):
        return False
    lower = name.lower()
    return lower.endswith(IMAGE_SUFFIXES) or lower.endswith(tuple(s + ".fz" for s in FITS_SUFFIXES))


def file_format(path: Path) -> str:
    lower = path.name.lower()
    if lower.endswith(COMPRESSED_SUFFIXES):
        return "fits_compressed"
    if lower.endswith(XISF_SUFFIXES):
        return "xisf"
    return "fits"


@dataclass
class Keyword:
    value: Any
    comment: str = ""


@dataclass
class ImageHeader:
    index: int
    image_id: str = ""
    geometry: tuple[int, ...] = ()
    sample_format: str = ""
    image_type: str = ""
    keywords: dict[str, Keyword] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)

    def get(self, *names: str) -> Any:
        """First present keyword value among `names` (e.g. EXPTIME, EXPOSURE)."""
        for n in names:
            k = self.keywords.get(n)
            if k is not None and k.value not in (None, ""):
                return k.value
        return None

    def keywords_json(self) -> dict[str, dict[str, Any]]:
        return {k: {"value": v.value, "comment": v.comment} for k, v in self.keywords.items()}


@dataclass
class HeaderResult:
    format: str
    images: list[ImageHeader] = field(default_factory=list)
    file_properties: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.images)

    def integration_index(self) -> int | None:
        """WBPP masters hold integration + rejection maps; only `integration` is the master (constitution)."""
        for img in self.images:
            if img.image_id == "integration":
                return img.index
        return None

    def primary(self) -> ImageHeader:
        idx = self.integration_index()
        return self.images[idx if idx is not None else 0]


def _typed(value: Any) -> Any:
    """XISF FITSKeyword values are strings; give numbers and booleans their types."""
    if not isinstance(value, str):
        return value
    v = value.strip()
    if v in ("T", "F"):
        return v == "T"
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            continue
    return v


def read_xisf(path: Path) -> HeaderResult:
    import xisf

    res = HeaderResult(format="xisf")
    try:
        x = xisf.XISF(str(path))  # parses the XML header only
        metas = x.get_images_metadata()
        res.file_properties = {k: v.get("value") for k, v in (x.get_file_metadata() or {}).items()}
    except Exception as exc:  # noqa: BLE001
        res.error = f"Could not read the XISF header: {exc}"
        return res
    for i, m in enumerate(metas):
        img = ImageHeader(
            index=i,
            image_id=str(m.get("id") or ""),
            geometry=tuple(int(g) for g in (m.get("geometry") or ())),
            sample_format=str(m.get("sampleFormat") or ""),
            image_type=str(m.get("imageType") or ""),
        )
        for name, entries in (m.get("FITSKeywords") or {}).items():
            if name in ("HISTORY", "COMMENT") or not entries:
                continue
            img.keywords[name] = Keyword(
                _typed(entries[0].get("value")), str(entries[0].get("comment") or "")
            )
        img.properties = {k: v.get("value") for k, v in (m.get("XISFProperties") or {}).items()}
        res.images.append(img)
    if not res.images:
        res.error = "The XISF file contains no images."
    return res


def read_fits(path: Path) -> HeaderResult:
    from astropy.io import fits

    res = HeaderResult(format=file_format(path))
    try:
        with fits.open(
            path, mode="readonly", memmap=True, lazy_load_hdus=True, do_not_scale_image_data=True
        ) as hl:
            index = 0
            for hdu in hl:
                h = hdu.header  # header only; .data is never touched
                naxis = int(h.get("NAXIS", 0) or 0)
                if naxis == 0:
                    continue
                img = ImageHeader(
                    index=index,
                    image_id=str(h.get("EXTNAME", "") or ""),
                    geometry=tuple(int(h.get(f"NAXIS{n}", 0)) for n in range(1, naxis + 1)),
                    sample_format=f"BITPIX={h.get('BITPIX')}",
                    image_type=str(h.get("IMAGETYP", "") or ""),
                )
                for card in h.cards:
                    if card.keyword in ("", "HISTORY", "COMMENT") or card.keyword in img.keywords:
                        continue
                    img.keywords[card.keyword] = Keyword(card.value, str(card.comment or ""))
                res.images.append(img)
                index += 1
    except Exception as exc:  # noqa: BLE001
        res.error = f"Could not read the FITS header: {exc}"
        return res
    if not res.images:
        res.error = "The FITS file contains no image."
    return res


def read_header(path: Path) -> HeaderResult:
    fmt = file_format(path)
    return read_xisf(path) if fmt == "xisf" else read_fits(path)
