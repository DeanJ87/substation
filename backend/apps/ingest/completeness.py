"""Is this image file completely written? Timing alone can't say: a network share can stall mid-write for
longer than any quiet period, and some file sharing layers report stale sizes. Both formats declare in their
header how many bytes the data takes, so a file shorter than that is still being written.

`expected_size` returns the byte count the header promises, or None when the file can't be judged (not
recognisable, or the header itself is unreadable: the cataloguer reports those properly).
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .headers import file_format

FITS_BLOCK = 2880
CARD = 80
_ATTACHMENT = re.compile(rb'location\s*=\s*"attachment:(\d+):(\d+)"')


def expected_size(path: Path) -> int | None:
    fmt = file_format(path)
    try:
        if fmt == "xisf":
            return _xisf(path)
        if fmt in ("fits", "fits_compressed"):
            return _fits(path)
    except OSError:
        return None
    return None


def _xisf(path: Path) -> int | None:
    """Monolithic XISF: 'XISF0100', uint32 header length, 4 reserved bytes, XML header, then attachments
    at the absolute positions the header gives as location="attachment:<position>:<size>"."""
    with path.open("rb") as f:
        head = f.read(16)
        if len(head) < 16 or head[:8] != b"XISF0100":
            return None
        (length,) = struct.unpack("<I", head[8:12])
        xml = f.read(length)
    if len(xml) < length:
        return 16 + length  # the header itself is still arriving
    ends = [int(pos) + int(size) for pos, size in _ATTACHMENT.findall(xml)]
    return max(ends, default=16 + length)


def _fits(path: Path) -> int | None:
    """Walk HDUs: each is a header of 2880-byte blocks ending in an END card, then
    |BITPIX|/8 x GCOUNT x (PCOUNT + NAXIS1 x ... x NAXISn) data bytes padded to 2880. The last HDU's
    padding is not required, as some writers omit it."""
    size = path.stat().st_size
    pos, end = 0, 0
    with path.open("rb") as f:
        while pos < size:
            f.seek(pos)
            cards: dict[str, str] = {}
            header_len = 0
            while True:
                block = f.read(FITS_BLOCK)
                if len(block) < FITS_BLOCK:
                    return pos + header_len + FITS_BLOCK  # header incomplete
                header_len += FITS_BLOCK
                done = False
                for i in range(0, FITS_BLOCK, CARD):
                    card = block[i : i + CARD].decode("ascii", "replace")
                    key = card[:8].strip()
                    if key == "END":
                        done = True
                        break
                    if card[8:10] == "= ":
                        cards[key] = card[10:].split("/", 1)[0].strip()
                if done:
                    break
                if pos == 0 and header_len == FITS_BLOCK and "SIMPLE" not in cards:
                    return None  # not FITS
            try:
                naxis = int(cards.get("NAXIS", "0"))
                count = 1 if naxis else 0
                for n in range(1, naxis + 1):
                    count *= int(cards[f"NAXIS{n}"])
                bitpix = abs(int(cards["BITPIX"]))
                data = bitpix // 8 * int(cards.get("GCOUNT", "1")) * (int(cards.get("PCOUNT", "0")) + count)
            except (KeyError, ValueError):
                return None
            end = pos + header_len + data
            pos = end + (-data % FITS_BLOCK)
    return end
