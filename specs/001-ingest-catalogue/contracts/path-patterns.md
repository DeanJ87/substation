# Contract: path patterns

Patterns fill metadata when headers are missing or wrong (constitution II). They never rename or touch
files.

## Grammar

A pattern is a string matched against either the folder path relative to the library (`kind: folder`)
or the file name without extension (`kind: filename`). Literal text must match exactly; `{token}` and
`{token:type}` capture values; `{*}` matches any text without capturing; in folder patterns `**` matches
any number of folders.

| Token | Field | Type default | Example |
|---|---|---|---|
| `{target}` | target | text | `NGC 7000` |
| `{panel}` | panel | int | `3` |
| `{object}` | object (split into target and panel) | text | `NGC 7000 Panel 3` |
| `{filter}` | filter | text | `Ha` |
| `{exposure}` | exptime (seconds) | float | `600.00` |
| `{temp}` | ccd_temp (°C) | float | `-20.0` |
| `{settemp}` | set_temp (°C) | float | `-20` |
| `{gain}` | gain | int | `120` |
| `{offset}` | offset | int | `80` |
| `{bin}` | xbin and ybin | `NxN` or `N` | `1x1` |
| `{type}` | frame_type | text (mapped by the classification table) | `LIGHT` |
| `{date}` | night or date (with `{time}`: date_obs) | `YYYY-MM-DD` or `YYYYMMDD` | `2026-09-28` |
| `{time}` | time of day for date_obs | `HH-MM-SS` or `HHMMSS` | `20-05-02` |
| `{tz}` | how `{date}{time}` are read | `utc` or `local` (default `local`: then site longitude converts) | |
| `{camera}`, `{telescope}` | camera, telescope | text | |
| `{seq}` | ignored (never identity) | int | `0027` |

Types can be overridden: `{exposure:f}`, `{gain:d}`, `{temp:f}`.

## Examples

```
filename  {date}_{time}_{filter}_{temp}_{exposure}s_{seq}           # NINA default
folder    {target}/{date}/{type}/                                    # Target/Night/LIGHT layout
folder    Masters/{camera}/Darks/{settemp}c/                         # spike masters layout
filename  MasterDark_{camera}_{settemp}c_{exposure}s                 # WBPP-renamed masters
```

`BAD_` prefixes are stripped before filename matching (and recorded as NINA verdicts).

## Precedence

1. A user value for that content (always wins).
2. Patterns listing the field in `prefer_over_header` (most specific scope first, then priority).
3. Header value.
4. Other matching patterns (most specific scope, then priority).
5. Inferred (rules such as FlatWizard), then settings (site fallback).

Every value records its source and the pattern id. The API offers a preview: given a pattern and sample
paths, return the captured fields, and for existing frames, which values would change.
