# Path patterns

Some software writes poor headers: no filter, the wrong object name, no exposure. If your folders or file
names hold the right value, a **path pattern** reads it from there. Patterns never rename or touch files.

Add them under **Settings → Path patterns**. As you type, SubStation shows what the pattern captures from your
real files and which values would change.

## Writing a pattern

A pattern is matched against either the **file name** (without its extension or a NINA `BAD_` prefix) or the
**folder path** inside the library. Text must match exactly; fields in braces capture values.

| Field | Fills | Example |
|---|---|---|
| `{target}` | target | `NGC 7000` |
| `{panel}` | panel number | `3` |
| `{object}` | target and panel, from text like "NGC 7000 Panel 3" | |
| `{filter}` | filter | `Ha` |
| `{exposure}` | exposure in seconds | `600.00` |
| `{temp}` / `{settemp}` | sensor / set temperature (°C) | `-20.0` |
| `{gain}` / `{offset}` | gain / offset | `120` |
| `{bin}` | binning | `1x1` or `2` |
| `{type}` | frame type | `LIGHT`, `FLAT` |
| `{date}` and `{time}` | observation time | `2026-09-28`, `20-05-02` |
| `{camera}` / `{telescope}` | camera / telescope | |
| `{seq}` | ignored (a sequence number) | `0027` |
| `{*}` | any text, not captured | |

In folder patterns, `**` stands for any number of folders.

## Examples

```
file name   {*}_{*}_{filter}_{temp}_{exposure}s_{seq}       NINA's default file name
folder      {target}/{date}/{type}/                          Target / night / type folders
folder      **/{object}/{*}/                                 the object's folder anywhere in the tree
folder      Masters/{camera}/Darks/{settemp}c/               a masters folder
```

!!! note "Times in file names"
    NINA puts local clock time in file names, summer time included. SubStation reads it as local solar
    time from your site, so it can be up to an hour out. The header's `DATE-OBS` is exact, so the built-in
    NINA example leaves the time to the header.

## Which value wins

1. A value you gave in SubStation always wins.
2. A pattern, for the fields you ticked under **Prefer over the header**.
3. The header.
4. Any other pattern that matches (the most specific first, then by priority).

When the header and a pattern disagree, the sub's detail panel shows both under **Sources disagree**.
