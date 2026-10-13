"""Path pattern compiler and matcher (T073; contracts/path-patterns.md).

A pattern compiles to an anchored regular expression. Folder patterns match the folder path relative to the
library (with a trailing slash); filename patterns match the file name without its extension and without a
NINA `BAD_` prefix. Errors are plain English, for the pattern editor.

The `parse` library was planned for this, but it can't express `**` (any number of folders) or keep typed
captures from spilling across folder separators, so this is a small purpose-built compiler.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .classify import normalise_type
from .headers import IMAGE_SUFFIXES

_TEXT, _INT, _FLOAT = "text", "int", "float"

# token -> (default type, fields it fills)
TOKENS: dict[str, tuple[str, tuple[str, ...]]] = {
    "target": (_TEXT, ("target",)),
    "panel": (_INT, ("panel",)),
    "object": (_TEXT, ("object",)),
    "filter": (_TEXT, ("filter",)),
    "exposure": (_FLOAT, ("exptime",)),
    "temp": (_FLOAT, ("ccd_temp",)),
    "settemp": (_FLOAT, ("set_temp",)),
    "gain": (_INT, ("gain",)),
    "offset": (_INT, ("offset",)),
    "bin": ("bin", ("xbin", "ybin")),
    "type": (_TEXT, ("frame_type",)),
    "date": ("date", ()),
    "time": ("time", ()),
    "tz": ("tz", ()),
    "camera": (_TEXT, ("camera",)),
    "telescope": (_TEXT, ("telescope",)),
    "seq": (_INT, ()),
}
_TYPE_SPECS = {"d": _INT, "f": _FLOAT, "s": _TEXT, "w": _TEXT}
_RX = {
    _INT: r"[+-]?\d+",
    _FLOAT: r"[+-]?\d+(?:\.\d+)?",
    "bin": r"\d+(?:x\d+)?",
    "date": r"\d{4}-?\d{2}-?\d{2}",
    "time": r"\d{2}[-:]?\d{2}[-:]?\d{2}",
    "tz": r"(?i:utc|local)",
}
_TOKEN = re.compile(r"\{([^{}]*)\}")


class PatternError(ValueError):
    """A pattern that can't be used, with a message for the user."""


@dataclass
class Compiled:
    kind: str
    source: str
    regex: re.Pattern[str]
    tokens: list[tuple[str, str]] = field(default_factory=list)  # (group name, type)

    def fields(self) -> set[str]:
        out: set[str] = set()
        for name, _ in self.tokens:
            out.update(TOKENS[name][1])
        if {"date", "time"} <= {n for n, _ in self.tokens}:
            out.add("date_obs")
        if "object" in out:
            out.update({"target", "panel"})
        return out


def _segment(text: str, text_rx: str, tokens: list[tuple[str, str]], seen: set[str]) -> str:
    out, pos = [], 0
    for m in _TOKEN.finditer(text):
        lit = text[pos : m.start()]
        if "{" in lit or "}" in lit:
            raise PatternError(f"There is an unmatched brace in “{text}”.")
        out.append(re.escape(lit))
        body = m.group(1).strip()
        pos = m.end()
        if body == "*":
            out.append(text_rx.replace("+?", "*?"))
            continue
        name, _, spec = body.partition(":")
        name = name.strip()
        if name not in TOKENS:
            raise PatternError(
                f"{{{name}}} isn't a field SubStation knows. You can use: "
                + ", ".join(f"{{{t}}}" for t in TOKENS)
                + ", and {*} for text to skip."
            )
        if name in seen:
            raise PatternError(f"{{{name}}} appears twice. Use {{*}} for the second one.")
        seen.add(name)
        typ = TOKENS[name][0]
        if spec:
            if spec.strip() not in _TYPE_SPECS:
                raise PatternError(
                    f"“:{spec}” isn't a type. Use :d for whole numbers, :f for decimals or :s for text."
                )
            typ = _TYPE_SPECS[spec.strip()]
        tokens.append((name, typ))
        out.append(f"(?P<{name}>{_RX.get(typ, text_rx)})")
    tail = text[pos:]
    if "{" in tail or "}" in tail:
        raise PatternError(f"There is an unmatched brace in “{text}”.")
    out.append(re.escape(tail))
    return "".join(out)


def compile_pattern(pattern: str, kind: str) -> Compiled:
    pattern = pattern.strip()
    if not pattern:
        raise PatternError("The pattern is empty.")
    tokens: list[tuple[str, str]] = []
    seen: set[str] = set()
    if kind == "filename":
        if "/" in pattern:
            raise PatternError("A file name pattern can't contain “/”. Use a folder pattern for folders.")
        rx = _segment(pattern, r".+?", tokens, seen)
    elif kind == "folder":
        parts = [p for p in pattern.strip("/").split("/") if p != ""]
        rx = ""
        for part in parts:
            if part == "**":
                rx += r"(?:[^/]+/)*"
            elif "**" in part:
                raise PatternError("“**” must be a whole folder name, as in “**/{target}/”.")
            else:
                rx += _segment(part, r"[^/]+?", tokens, seen) + "/"
    else:
        raise PatternError("A pattern is either a folder pattern or a file name pattern.")
    if not tokens:
        raise PatternError("The pattern doesn't capture anything. Add a field such as {filter}.")
    return Compiled(kind=kind, source=pattern, regex=re.compile(f"^{rx}$", re.IGNORECASE), tokens=tokens)


def subject(rel_path: str, kind: str) -> str:
    """What a pattern of this kind is matched against."""
    folder, name = os.path.split(rel_path.replace("\\", "/"))
    if kind == "folder":
        return f"{folder}/" if folder else ""
    if name.startswith("BAD_"):
        name = name[4:]
    lower = name.lower()
    for suffix in sorted(IMAGE_SUFFIXES + (".fits.fz", ".fit.fz", ".fts.fz"), key=len, reverse=True):
        if lower.endswith(suffix):
            return name[: -len(suffix)]
    return os.path.splitext(name)[0]


def _parse_date(s: str) -> tuple[int, int, int]:
    d = s.replace("-", "")
    return int(d[:4]), int(d[4:6]), int(d[6:8])


def _parse_time(s: str) -> tuple[int, int, int]:
    t = s.replace("-", "").replace(":", "")
    return int(t[:2]), int(t[2:4]), int(t[4:6])


def match(c: Compiled, rel_path: str, site_lon: float | None = None) -> dict[str, Any] | None:
    """Captured field values for this path, typed, or None if the pattern doesn't match. Values that can't
    be read (an impossible date, say) are left out."""
    m = c.regex.match(subject(rel_path, c.kind))
    if m is None:
        return None
    got = {k: v for k, v in m.groupdict().items() if v is not None}
    types = dict(c.tokens)
    out: dict[str, Any] = {}
    for name, raw in got.items():
        typ, fields = types[name], TOKENS[name][1]
        if not fields:
            continue
        try:
            if name == "bin":
                x, _, y = raw.lower().partition("x")
                out["xbin"], out["ybin"] = int(x), int(y or x)
            elif name == "type":
                t = normalise_type(raw)
                if t is not None:
                    out["frame_type"] = t.value
            elif typ == _INT:
                out[fields[0]] = int(raw)
            elif typ == _FLOAT:
                out[fields[0]] = float(raw)
            else:
                out[fields[0]] = raw.strip()
        except ValueError:
            continue
    if "date" in got and "time" in got:
        try:
            y, mo, d = _parse_date(got["date"])
            h, mi, s = _parse_time(got["time"])
            when = datetime(y, mo, d, h, mi, s, tzinfo=UTC)
            if got.get("tz", "local").lower() == "local":
                if site_lon is None:
                    raise ValueError("local time needs a site longitude")
                # Read as local mean solar time, as nights are: a clock time with summer time may be up to an
                # hour off, which moves the time but not the night.
                when -= timedelta(hours=site_lon / 15.0)
            out["date_obs"] = when
        except ValueError:
            pass
    return out
