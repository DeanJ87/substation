"""Copy image files with chosen header keywords removed (T082; quickstart V10), to test what SubStation does
when software writes poor headers. The source is only ever read.

    uv run python scripts/strip_headers.py SOURCE... --to TARGET_DIR [--remove FILTER EXPTIME EXPOSURE]

XISF: the FITSKeyword elements (and the matching XISF properties, which would otherwise still supply the
value) are blanked with spaces of the same length, so the attachment positions in the header stay valid.
FITS: the cards are deleted with astropy. A folder SOURCE is copied with its layout.
"""

from __future__ import annotations

import argparse
import re
import shutil
import struct
import sys
from pathlib import Path

# FITS keyword -> XISF properties that carry the same value
PROPERTY_TWINS = {
    "FILTER": ["Instrument:Filter:Name"],
    "EXPTIME": ["Instrument:ExposureTime"],
    "EXPOSURE": ["Instrument:ExposureTime"],
    "OBJECT": ["Observation:Object:Name"],
    "CCD-TEMP": ["Instrument:Sensor:Temperature"],
    "DATE-OBS": ["Observation:Time:Start"],
    "INSTRUME": ["Instrument:Camera:Name"],
    "TELESCOP": ["Instrument:Telescope:Name"],
    "IMAGETYP": [],
}
DEFAULT = ["FILTER", "EXPTIME", "EXPOSURE"]
SUFFIXES = (".xisf", ".fit", ".fits", ".fts")


def blank(m: re.Match[bytes]) -> bytes:
    return b" " * len(m.group(0))


def strip_xisf(src: Path, dst: Path, keywords: list[str]) -> None:
    data = bytearray(src.read_bytes())
    if data[:8] != b"XISF0100":
        raise ValueError(f"{src} is not a monolithic XISF file")
    (length,) = struct.unpack("<I", data[8:12])
    xml = bytes(data[16 : 16 + length])
    for k in keywords:
        xml = re.sub(rb'<FITSKeyword name="' + re.escape(k.encode()) + rb'"[^>]*/>', blank, xml)
        for prop in PROPERTY_TWINS.get(k, []):
            xml = re.sub(
                rb'<Property id="' + re.escape(prop.encode()) + rb'"[^>]*?(/>|>.*?</Property>)',
                blank,
                xml,
                flags=re.S,
            )
    data[16 : 16 + length] = xml
    dst.write_bytes(bytes(data))


def strip_fits(src: Path, dst: Path, keywords: list[str]) -> None:
    from astropy.io import fits

    shutil.copyfile(src, dst)
    with fits.open(dst, mode="update") as hl:
        for hdu in hl:
            for k in keywords:
                while k in hdu.header:
                    del hdu.header[k]


def files(sources: list[Path]):  # -> Iterator[tuple[Path, Path]]
    for s in sources:
        if s.is_dir():
            for f in sorted(s.rglob("*")):
                if f.is_file() and f.suffix.lower() in SUFFIXES and not f.name.startswith("._"):
                    yield f, Path(s.name) / f.relative_to(s)
        else:
            yield s, Path(s.name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+", type=Path)
    ap.add_argument("--to", required=True, type=Path)
    ap.add_argument("--remove", nargs="+", default=DEFAULT, metavar="KEYWORD")
    args = ap.parse_args()
    n = 0
    for src, rel in files(args.sources):
        dst = args.to / rel
        if dst.resolve() == src.resolve():
            ap.error("the target must not be the source")
        dst.parent.mkdir(parents=True, exist_ok=True)
        (strip_xisf if src.suffix.lower() == ".xisf" else strip_fits)(src, dst, args.remove)
        n += 1
        print(f"{rel}: removed {', '.join(args.remove)}")
    print(f"{n} files written to {args.to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
