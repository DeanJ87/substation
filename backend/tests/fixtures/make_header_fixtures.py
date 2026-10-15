"""T034: build header-only fixtures from the real spike files (research R13; constitution VI).

usage:  uv run python tests/fixtures/make_header_fixtures.py /path/to/sub-test

The source tree is opened read-only. Each XISF fixture keeps the original signature and XML header
verbatim and drops the pixel data (header-only readers never reach it). FITS fixtures are built from a
real NINA light's keywords with a 2x2 array, plus a tile-compressed `.fz` copy. `manifest.json` records
each fixture's source path and the source file's SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

OUT = Path(__file__).resolve().parent / "headers"

# fixture path (relative to OUT) -> source path (relative to the spike tree)
XISF_FIXTURES = {
    "capture/2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf": "2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf",
    "capture/2026-09-28/LIGHT/2026-09-29_02-18-08_Halpha_-20.00_600.00s_0003.xisf": None,  # Heart P2, filled below
    "capture/2026-09-28/LIGHT/BAD_2026-09-28_20-50-41_Halpha_-20.00_600.00s_0031.xisf": "2026-09-28/LIGHT/BAD_2026-09-28_20-50-41_Halpha_-20.00_600.00s_0031.xisf",
    "capture/2026-09-28/LIGHT/2026-09-28_20-50-41_Halpha_-20.00_600.00s_0031.xisf": "2026-09-28/LIGHT/2026-09-28_20-50-41_Halpha_-20.00_600.00s_0031.xisf",
    "capture/2026-09-28/LIGHT/BAD_2026-09-29_01-29-50_Halpha_-19.90_600.00s_0031.xisf": "2026-09-28/LIGHT/BAD_2026-09-29_01-29-50_Halpha_-19.90_600.00s_0031.xisf",
    "capture/2026-10-07/LIGHT/2026-10-08_00-03-30_OIII_-20.00_600.00s_0011.xisf": "2026-10-07/LIGHT/2026-10-08_00-03-30_OIII_-20.00_600.00s_0011.xisf",
    "capture/2026-10-07/LIGHT/2026-10-07_20-27-58_OIII_-20.00_600.00s_0000.xisf": "2026-10-07/LIGHT/2026-10-07_20-27-58_OIII_-20.00_600.00s_0000.xisf",
    "capture/2026-09-28/FLAT/2026-09-29_05-02-31_Halpha_-19.90_2.00s_0000.xisf": None,  # first Hα flat, filled below
    "capture/2026-09-28/DARK/2026-09-29_05-09-53_Halpha_-20.10_2.00s_0000.xisf": "2026-09-28/DARK/2026-09-29_05-09-53_Halpha_-20.10_2.00s_0000.xisf",
    "capture/2026-09-28/DARK/2026-09-29_05-11-47_Halpha_-19.90_2.00s_0045.xisf": "2026-09-28/DARK/2026-09-29_05-11-47_Halpha_-19.90_2.00s_0045.xisf",
    "masters/Darks/-20c/MasterDark_ATR2600M_-20c_600s.xisf": "Masters/ATR2600M/Darks/-20c/MasterDark_ATR2600M_-20c_600s.xisf",
    "masters/Bias/masterBias_ATR2600M_-10c.xisf": "Masters/ATR2600M/Bias/masterBias_ATR2600M_-10c.xisf",
    "masters/Flats/2026-08-15/masterFlat_BIN-1_6224x4168_FILTER-OIII_mono.xisf": "MasterFlats/ATR2600M/2026-08-15/masterFlat_BIN-1_6224x4168_FILTER-OIII_mono.xisf",
}
STRIPPED = {  # fixture -> (source fixture, keywords and properties removed)
    "stripped/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf": (
        "capture/2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf",
        ["FILTER", "EXPTIME", "EXPOSURE"],
        ["Instrument:Filter:Name", "Instrument:ExposureTime"],
    ),
}
APPLEDOUBLE_SRC = "Masters/ATR2600M/Darks/-10c/._masterDark_ATR2600M_-10c_600.00s.xisf"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while b := f.read(8 << 20):
            h.update(b)
    return h.hexdigest()


def xisf_header_bytes(path: Path) -> bytes:
    with open(path, "rb") as f:
        head = f.read(16)
        assert head[:8] == b"XISF0100", path
        (length,) = struct.unpack("<I", head[8:12])
        return head + f.read(length)


def with_xml(header: bytes, xml: bytes) -> bytes:
    return header[:8] + struct.pack("<I", len(xml)) + header[12:16] + xml


def _write_xisf_headers(src_root: Path, manifest: dict[str, dict]) -> None:
    """Each chosen XISF's header alone (no image data), recorded in the manifest with its source's hash."""
    for rel, src_rel in XISF_FIXTURES.items():
        src = src_root / src_rel
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(xisf_header_bytes(src))
        manifest[rel] = {"source": src_rel, "source_sha256": sha256(src), "kind": "xisf header-only"}


def _write_stripped(manifest: dict[str, dict]) -> None:
    """Copies of written headers with some FITS keywords and XISF properties removed, for the fallbacks."""
    for rel, (base, keywords, props) in STRIPPED.items():
        header = (OUT / base).read_bytes()
        xml = header[16:].decode("utf-8")
        for k in keywords:
            xml = re.sub(rf'\s*<FITSKeyword name="{re.escape(k)}"[^>]*/>', "", xml)
        for p in props:
            xml = re.sub(rf'\s*<Property id="{re.escape(p)}"[^>]*?(/>|>.*?</Property>)', "", xml, flags=re.S)
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(with_xml(header, xml.encode("utf-8")))
        manifest[rel] = {
            "source": manifest[base]["source"],
            "source_sha256": manifest[base]["source_sha256"],
            "kind": f"xisf header-only, removed {keywords + props}",
        }


def _fits_header_from(xisf_path: Path) -> fits.Header:
    """A FITS header carrying an XISF's keywords (structural ones and names over 8 characters left out), each
    value read as an int or float where it is one, comments cut to 40 characters; keywords FITS refuses are
    skipped."""
    import xisf

    meta = xisf.XISF(str(xisf_path)).get_images_metadata()[0]
    hdr = fits.Header()
    for name, entries in meta["FITSKeywords"].items():
        if (
            name in ("SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2", "EXTEND", "BZERO", "BSCALE")
            or len(name) > 8
        ):
            continue
        v = entries[0]["value"]
        for cast in (int, float):
            try:
                v = cast(v)
                break
            except (TypeError, ValueError):
                continue
        try:
            hdr[name] = (v, entries[0].get("comment", "")[:40])
        except ValueError:
            continue
    return hdr


def main(src_root: Path) -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    # fill sources chosen by pattern
    heart = sorted((src_root / "2026-09-28/LIGHT").glob("2026-09-29_02-*_Halpha_*.xisf"))[0]
    XISF_FIXTURES["capture/2026-09-28/LIGHT/" + heart.name] = str(heart.relative_to(src_root))
    del XISF_FIXTURES["capture/2026-09-28/LIGHT/2026-09-29_02-18-08_Halpha_-20.00_600.00s_0003.xisf"]
    flat = sorted((src_root / "2026-09-28/FLAT").glob("*_Halpha_*_2.00s_*.xisf"))[0]
    XISF_FIXTURES["capture/2026-09-28/FLAT/" + flat.name] = str(flat.relative_to(src_root))
    del XISF_FIXTURES["capture/2026-09-28/FLAT/2026-09-29_05-02-31_Halpha_-19.90_2.00s_0000.xisf"]

    manifest: dict[str, dict] = {}
    _write_xisf_headers(src_root, manifest)
    _write_stripped(manifest)

    ad_src = src_root / APPLEDOUBLE_SRC
    if ad_src.exists():
        dst = OUT / "capture/2026-09-28/LIGHT/._2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf"
        shutil.copyfile(ad_src, dst)
        manifest[str(dst.relative_to(OUT))] = {
            "source": APPLEDOUBLE_SRC,
            "source_sha256": sha256(ad_src),
            "kind": "AppleDouble",
        }

    # FITS light built from a real NINA light's keywords, plus a tile-compressed copy
    base_rel = "capture/2026-09-28/LIGHT/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf"
    hdr = _fits_header_from(OUT / base_rel)
    data = np.array([[100, 101], [102, 103]], dtype=np.uint16)
    fits_rel = "capture/fits/2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.fits"
    (OUT / fits_rel).parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(data=data, header=hdr).writeto(OUT / fits_rel)
    fz_rel = fits_rel + ".fz"
    fits.HDUList([fits.PrimaryHDU(), fits.CompImageHDU(data=data, header=hdr)]).writeto(OUT / fz_rel)
    for rel in (fits_rel, fz_rel):
        manifest[rel] = {
            "source": manifest[base_rel]["source"],
            "source_sha256": manifest[base_rel]["source_sha256"],
            "kind": "synthetic FITS with the real header keywords",
        }

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"{len(manifest)} fixtures, {total / 1024:.0f} KiB in {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
