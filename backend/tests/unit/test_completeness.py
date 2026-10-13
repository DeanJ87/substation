"""A file shorter than its header says is still being written (hash task completeness check)."""

from __future__ import annotations

import struct

import numpy as np
from astropy.io import fits

from apps.ingest.completeness import expected_size


def make_xisf(path, data_len=1000):
    pos = 4096
    xml = (
        f'<?xml version="1.0"?><xisf version="1.0"><Image geometry="10:50:1" sampleFormat="UInt16" '
        f'location="attachment:{pos}:{data_len}"/></xisf>'
    ).encode()
    head = b"XISF0100" + struct.pack("<I", len(xml)) + b"\0" * 4 + xml
    path.write_bytes(head + b"\0" * (pos - len(head)) + b"\1" * data_len)
    return pos + data_len


def test_xisf_complete_and_truncated(tmp_path):
    p = tmp_path / "a.xisf"
    full = make_xisf(p)
    assert expected_size(p) == full == p.stat().st_size
    p.write_bytes(p.read_bytes()[:3000])  # stalled mid-write
    assert expected_size(p) == full


def test_xisf_header_still_arriving(tmp_path):
    p = tmp_path / "a.xisf"
    make_xisf(p)
    p.write_bytes(p.read_bytes()[:40])
    assert expected_size(p) > 40


def test_fits_complete_and_truncated(tmp_path):
    p = tmp_path / "a.fits"
    fits.PrimaryHDU(np.zeros((100, 120), dtype=np.uint16)).writeto(p)
    full = p.stat().st_size
    assert expected_size(p) <= full
    assert expected_size(p) > full - 2880
    p.write_bytes(p.read_bytes()[: full // 2])
    assert expected_size(p) > full // 2


def test_compressed_fits(tmp_path):
    p = tmp_path / "a.fits.fz"
    hdus = fits.HDUList(
        [fits.PrimaryHDU(), fits.CompImageHDU(np.arange(120 * 100, dtype=np.int32).reshape(100, 120))]
    )
    hdus.writeto(p)
    full = p.stat().st_size
    assert expected_size(p) is not None and expected_size(p) <= full
    p.write_bytes(p.read_bytes()[: full - 3000])
    assert expected_size(p) > full - 3000


def test_unrecognisable_files_are_not_judged(tmp_path):
    p = tmp_path / "a.xisf"
    p.write_bytes(b"not an xisf file at all")
    assert expected_size(p) is None
    q = tmp_path / "b.fits"
    q.write_bytes(b"x" * 3000)
    assert expected_size(q) is None
