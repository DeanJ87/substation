"""Replay a capture session into a watched folder (T059; quickstart V3 and V4).

Copies light frames from SOURCE into TARGET in DATE-OBS order, waiting between files as the
original session did (divided by --speedup). The source is only ever read.

    uv run python scripts/replay.py SOURCE TARGET [--speedup 60] [--limit N] [--chunked]

--chunked writes each file in 1 MiB pieces over about 3 s, like a slow NAS share, so the
ingest stability check is exercised. Files without DATE-OBS are copied last, in name order.
Existing files in TARGET are skipped so a replay can be resumed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.ingest.headers import is_image_name, read_header  # noqa: E402
from apps.ingest.night import parse_date_obs  # noqa: E402

CHUNK = 1 << 20


def plan(source: Path) -> list[tuple[datetime | None, Path]]:
    items: list[tuple[datetime | None, Path]] = []
    for root, dirs, files in os.walk(source):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "@")))
        for name in sorted(files):
            if name.startswith("._") or not is_image_name(name):
                continue
            path = Path(root) / name
            try:
                when = parse_date_obs(read_header(path).primary().get("DATE-OBS"))
            except Exception:  # unreadable header: copy it anyway, last
                when = None
            items.append((when, path))
    items.sort(key=lambda it: (it[0] is None, it[0] or datetime.min, str(it[1])))
    return items


def copy(src: Path, dst: Path, chunked: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not chunked:
        shutil.copyfile(src, dst)
        return
    size = src.stat().st_size
    pause = 3.0 / max(1, size // CHUNK)
    with src.open("rb") as r, dst.open("wb") as w:
        while block := r.read(CHUNK):
            w.write(block)
            w.flush()
            time.sleep(pause)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("target", type=Path)
    ap.add_argument("--speedup", type=float, default=60.0, help="divide real gaps by this (0 = no waiting)")
    ap.add_argument("--max-gap", type=float, default=30.0, help="cap any single wait, seconds")
    ap.add_argument("--limit", type=int, default=0, help="stop after N files")
    ap.add_argument("--chunked", action="store_true", help="write slowly in 1 MiB pieces")
    args = ap.parse_args()

    source, target = args.source.resolve(), args.target.resolve()
    if target == source or source in target.parents:
        ap.error("target must not be inside the source")
    items = plan(source)
    if args.limit:
        items = items[: args.limit]
    print(f"{len(items)} files to replay from {source}", flush=True)

    prev: datetime | None = None
    for i, (when, src) in enumerate(items, 1):
        dst = target / src.relative_to(source)
        if dst.exists():
            continue
        if args.speedup and when and prev:
            time.sleep(min(args.max_gap, max(0.0, (when - prev).total_seconds() / args.speedup)))
        prev = when or prev
        copy(src, dst, args.chunked)
        print(
            f"[{i}/{len(items)}] {when.isoformat() if when else '-':19}  {dst.relative_to(target)}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
