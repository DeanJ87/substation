# Feature Specification: Brand, theme and app shell

**Feature Branch**: `007-brand-theme-shell`

**Created**: 2026-10-10

**Status**: Draft

**Input**: SubStation brand guidelines and every SubStation design file in the owner's design folder (SQMeter logo and dashboard), reviewed in `docs/design/design-review.md` section A; owner direction 2026-10-10: the brand guidelines are written into this spec.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - SubStation looks and reads like its brand (Priority: P1)

Every screen uses the brand's tokens, type, components, logo and voice, in dark, light and night vision.

**Independent Test**: Grep feature CSS for colour literals (none); switch themes with N on every screen; in night
vision no image or element emits green, blue or white light; copy checks against the writing rules.

### User Story 2 - The shell gets out of the way (Priority: P1)

A 56 px header with the mark, the five-item nav with counts, "Watching N folders" and an account menu; the theme is
chosen in Settings → Appearance or with N; ? lists the keys for the current screen; sign-in is the one-card screen.

**Independent Test**: At 1280–1440 px the header is one line; Sign out is in the account menu; ? opens the key list.

### Edge Cases

- A raster preview in night vision is drawn red-only (CSS filter or server-rendered), including thumbnails.
- Below 96 px wide the lockup gives way to the mark; below 24 px the favicon artwork is used.

## Requirements *(mandatory)*

1. **007-DR-01**: The UI MUST use only `--sst-*` tokens for colour. No hex or rgba literal MUST appear in feature
   CSS.
2. **007-DR-02**: Cards MUST use `linear-gradient(180deg, var(--sst-panel), var(--sst-card-end))` with a 1px
   `--sst-line` border and 0.85rem radius. Readout cards MUST use 0.7rem radius, an 11 px uppercase label, and a
   mono value at 34–36 px, weight 500, −0.03em, tabular. The first readout's value MUST use accent.
3. **007-DR-03**: Buttons MUST follow the guide:
   - primary: accent border, accent-tint fill and accent text at weight 600;
   - secondary: line border, text colour, weight 500;
   - danger: `--sst-bad` border and text;
   - disabled: dashed line border with `--sst-dim` text.
4. **007-DR-04**: Verdict badges MUST be neutral pills (line border, `--sst-panel-3`, text colour, 12 px weight 500)
   in which only the 14 px verdict icon carries colour.
5. **007-DR-05**: The header MUST be 56 px high and contain:
   - the mark at 22 px with "SubStation" at 16 px weight 600;
   - nav Library · Review · Calibration · Activity · Settings at 14 px, inactive items at weight 500, the active
     item at 600 with an accent underline;
   - counts on Review (subs to review) and Activity (jobs running) as mono pills with tint fill and accent text;
   - "Watching N folders";
   - an account menu (avatar initial and username) that holds Sign out.
   The header MUST NOT contain a theme control.
6. **007-DR-06**: The theme MUST be set in Settings → Appearance (Dark, Light, Night vision) and toggled with N
   anywhere outside text inputs. The choice MUST persist per user and be applied before first paint.
7. **007-DR-07**: In night vision, every raster image MUST be rendered in red only (previews, thumbnails, master
   previews, charts, calibration evidence), and no element MUST emit green, blue or white light. Verdicts MUST stay
   distinguishable by shape and glyph alone.
8. **007-DR-08**: The logo MUST use the supplied artwork:
   - full colour on dark, inverted on light, red-only in night vision;
   - a quarter of the mark's height clear space;
   - lockup gap of one third of the mark's height;
   - no rendering below 16 px (mark) or 96 px wide (horizontal lockup);
   - `favicon-16.svg` below 24 px.
   The rejected concept marks MUST NOT ship.
9. **007-DR-09**: The app MUST ship `favicon-16.svg`, `favicon-32`, `favicon-48`, `favicon.svg` and a 512 px app
   icon (PNG, 22% corner radius) for NAS app listings and Docker Hub.
10. **007-DR-10**: Body text MUST be Inter 15/1.55 with `font-feature-settings: 'cv11','ss01'`. Numbers, times and
    tables MUST use tabular figures. Files, paths and FITS keywords MUST be set in JetBrains Mono.
11. **007-DR-11**: The sign-in screen MUST show:
    - the mark and wordmark above a card titled "Sign in" with "to the SubStation on <host>";
    - Username and Password fields;
    - errors under the field they relate to, in the voice guide ("That password doesn't match. Check caps lock and
      try again.");
    - Enter to submit;
    - a footer "SubStation <version>";
    - no other copy.
12. **007-DR-12**: Pressing ? MUST open a list of all keyboard shortcuts for the current screen.
13. **007-DR-13**: Page layout MUST use a 1240 px content width with 32 px gutters and 24 px titles (600, −0.02em)
    with a 13 px muted summary line.
14. **007-DR-14**: All copy MUST follow the writing rules in section A.9:
    - British English and sentence case;
    - no exclamation marks;
    - the U+2212 minus;
    - en-GB number grouping;
    - unit spacing as specified;
    - long dates in headers and short dates in tables;
    - 24-hour times;
    - " · " separators;
    - "Not recorded" for missing metadata;
    - the reason form "measurement, comparison, likely cause".
15. **007-DR-15**: The docs site MUST use the three SubStation palette schemes, self-hosted Inter and JetBrains
    Mono, and the SubStation logo and favicon.
16. **007-DR-16**: Confirmations (delete master, remove collection, discard settings) MUST be built into the page in
    the design system, not browser dialogs.

## Brand reference (from the guidelines)

### A.1 Positioning

- Tagline in the guide: "SubStation watches the folder where a telescope's subs land, calibrates and grades each one
  as it arrives, and stacks finished datasets into masters." Domain `substation.dev`, "a sibling of SQMeter".
- Shared with SQMeter: dark neutral foundation, Inter and JetBrains Mono, gradient cards, hairlines, uppercase
  labels, monospaced readouts, outlined buttons, WCAG AA, a calm plain-English voice.
- SubStation's own: Orchid accent, the converging-frames mark, night-vision mode, a seven-state verdict system, and
  review components (blink viewer, night charts, sub thumbnails).

### A.2 Colour tokens (exact, `substation-tokens.css`; dark is the default, `data-theme="light|night"` on `<html>`)

| Token | Dark (primary) | Light (secondary) | Night vision |
|---|---|---|---|
| `--sst-bg` | `#080d14` | `#f4f6f8` | `#050000` |
| `--sst-panel` | `#0d141d` | `#ffffff` | `#0c0101` |
| `--sst-panel-2` | `#111b27` | `#edf1f4` | `#120202` |
| `--sst-panel-3` | `#0a1018` | `#e8edf1` | `#080000` |
| `--sst-card-end` | `#0a1119` | `#f8fafb` | `#080000` |
| `--sst-line` | `#1b2a38` | `#d3dbe2` | `#3a0a06` |
| `--sst-line-2` | `#142130` | `#e3e8ed` | `#250604` |
| `--sst-text` | `#e7edf3` (16.5 / 14.7) | `#0d141d` (17.1 / 15.7) | `#ff4a3a` (6.3 / 6.1) |
| `--sst-muted` | `#8b9baa` (6.8 / 6.1) | `#45525f` (7.4 / 6.8) | `#e63a2c` (5.0 / 4.8) |
| `--sst-dim` | `#768798` (5.3 / 4.7) | `#55626e` (5.8 / 5.3) | `#e63a2c` (5.0 / 4.8) |
| `--sst-accent` | `#ee7bd0` Orchid (7.8 / 6.9) | `#a3307f` (5.9 / 5.4) | `#ff4a3a` |
| `--sst-accent-tint` | `rgba(238,123,208,0.12)` | `rgba(163,48,127,0.08)` | `rgba(255,74,58,0.10)` |
| `--sst-accent-line` | `rgba(238,123,208,0.45)` | `rgba(163,48,127,0.45)` | `rgba(255,74,58,0.5)` |
| `--sst-on-accent` | `#080d14` | `#ffffff` | `#050000` |
| `--sst-violet` | `#a78bfa` (7.2 / 6.4) | `#6b46d6` (5.6 / 5.1) | `#ff4a3a` |
| `--sst-ok` | `#5ee0a0` (11.7 / 10.5) | `#127a4a` (5.0 / 4.6) | `#ff4a3a` |
| `--sst-warn` | `#f4c15d` (11.7 / 10.4) | `#8a5a00` (5.5 / 5.0) | `#ff4a3a` |
| `--sst-bad` | `#f26b62` (6.5 / 5.8) | `#be3229` (5.3 / 4.8) | `#ff4a3a` |
| `--sst-focus` | `#ee7bd0` | `#a3307f` | `#ff4a3a` |
| `--sst-thumb` | `#04070b` | `#1a222c` | `#000000` |

The ratios in brackets are against `--sst-bg` and the lowest-contrast panel. Every text token passes AA (4.5:1).

- **Night vision rule**: red channel only. "No token has more than 23% green or blue." "Deep red on near-black only.
  No blue, green or white light." Status colours collapse to one red, so verdicts rely on shape and glyph. The guide
  also says to lower screen brightness in the field. Do not separate verdicts by shades of red.
- **Accent choice**: Orchid `#ee7bd0` (316°) is 61° from violet and 47° from red, warm against SQMeter's cyan
  `#55c7f2` (196°), and is never mistaken for a status. Phosphor `#c6e46b` and Periwinkle `#8da2ff` were rejected.
- **Usage**: Orchid is for brand and action only. Status colours are for verdicts only. Never use SQMeter cyan in
  SubStation, and never mix both accents in one interface.
- Page backdrop behind design canvases: `#04070b` (presentation only).

### A.3 Typography

Inter is for words and JetBrains Mono is for data. Body text uses `font-feature-settings: 'cv11','ss01'`.

| Style | Spec | Example |
|---|---|---|
| hero | mono 96/1 (`--sst-fs-hero` 6rem) | 412 |
| readout | mono 48/1 (`--sst-fs-readout` 3rem); components use 44 px, screens use 34–36 px, weight 500, −0.03em | 2.14″ |
| h1 | 36/1.15 · 600 (−0.02em) | M 101, Hα, three nights |
| h2 | 24/1.25 · 600 | Quality across the night |
| h3 | 18/1.35 · 600 | Calibration library |
| body | 15/1.55 · 400 | SubStation matched 78 subs to darks and flats from 6 October… |
| small | 13/1.45 · 400 | Last sub arrived 4 minutes ago |
| label | 11 · 600 · uppercase · +0.08em | Integration time |
| mono | 13/1.5 · 400 | /data/incoming/2026-10-08/M101/M101_Ha_300s_0045.fits |

- Every table, timestamp and live counter uses `font-variant-numeric: tabular-nums`.
- Files, paths and FITS headers are always set in mono.
- In the product screens, page titles are 24 px 600 −0.02em with a 13 px muted summary line beneath.
- Fonts are self-hosted: InterVariable.woff2 and JetBrainsMono-Variable.woff2 (docs CSS).

### A.4 Spacing, radius and surfaces

- Radii: `--sst-radius-sm` 0.55rem (buttons, inputs, thumbnails), `--sst-radius` 0.7rem (readout cards, tables),
  `--sst-radius-lg` 0.85rem (cards, dialogs). Pills use 999px. kbd uses 5px. Code uses 0.35rem.
- Shadow: `--sst-shadow: 0 1px 0 rgba(0,0,0,.25)`. Dialog: `0 24px 60px rgba(0,0,0,.5)` over an
  `rgba(4,7,11,.72)` scrim.
- Cards: `linear-gradient(180deg, var(--sst-panel), var(--sst-card-end))`, 1px `--sst-line`, radius 0.85rem,
  padding 24 px.
- Readout card: gradient `--sst-panel-2 → --sst-card-end` (brand guide) or `--sst-panel → --sst-card-end`
  (screens), radius 0.7rem, padding 16–18 / 18–20 px. Label 11 px uppercase muted. Value mono 34–44 px, weight 500,
  −0.03em, tabular. The first readout's value is accent and the rest are text. Detail line 12–13 px muted.
- Page container: max-width 1240 px (v2) or 1200 px (v1), padding 32 px 32 px 48 px, vertical gap 24 px.
  The review and dataset inspector layouts use up to 1376 px.
- Table header row: `--sst-panel-2` background, 11 px uppercase muted labels, `--sst-line-2` row separators,
  rows 14 px with 14 px × 20 px padding.
- Links are underlined with offset 0.18em and thickness 1px (2px on hover). Focus is a 2px accent outline with
  2px offset. Selection uses `--sst-accent-tint`.

### A.5 Components (brand guide §08, Screens, v2)

- **Buttons** (14 px, padding 8×16, radius 0.55rem):
  - Primary: 1px accent border, `--sst-accent-tint` fill at rest, accent text, weight 600 (for example
    "Stack dataset").
  - Secondary: `--sst-line` border, transparent, text colour, weight 500 ("Re-grade").
  - Danger: `--sst-bad` border and text ("Delete master").
  - Disabled: dashed `--sst-line` border with `--sst-dim` text ("Export").
- **Tabs**: 14 px, gap 22 px, padding 8 px 0, a 1px line under the row. Active tab is text colour at weight 600
  with `box-shadow: inset 0 -2px 0 var(--sst-accent)`. Inactive tabs are muted at weight 500. Counts sit inline
  ("Subs 541", "Masters 7").
- **Keys**: `<kbd>` in mono 12 px, text colour, `--sst-panel-3` background, 1px line border with a 2px bottom
  border, radius 5px, padding 1×7.
- **Verdict badge**: neutral pill (1px `--sst-line` border, `--sst-panel-3` fill, 12 px weight 500 in text colour,
  padding 3 10 3 6) with a coloured 14 px verdict icon. Only the icon carries colour.
- **Sub thumbnail**: 1px line border, radius 0.55rem, `--sst-panel-3`, 3:2 preview on `--sst-thumb`. The verdict
  icon (16 px) sits top-left on a `--sst-bg` disc (padding 2px). File name in mono 11 px text and meta in mono
  11 px muted tabular ("2.31″ · 760"). Selected: accent border plus a 1px accent ring.
- **Chips / filter pills**: active chip uses `--sst-accent-line` border and `--sst-accent-tint` fill. Inactive uses
  `--sst-line` and `--sst-panel-3`, with an icon, label and mono count.
- **Segmented control** (theme switch): line border, radius 0.55rem, 2px padding on `--sst-panel-3`. The guide
  header fills the active segment with accent and uses `--sst-on-accent` text. Settings uses tint fill with accent
  text.
- **Settings controls (A4)**: fields in mono on `--sst-panel-3`. "On" options have an accent border, tint fill and
  accent text at 600. "Off" options have a line border and muted text.
- **Pipeline steps**: a progress bar per step. Done steps are filled with `--sst-ok`. The current step is
  accent-filled to its progress and labelled at 600. Later steps are muted.
- **Header** (`SubStationHeader.dc.html`):
  - Height 56 px, `--sst-panel`, 1px bottom line, padding 0 32 px, gap 40 px.
  - Brand: mark at 22 px with "SubStation" at 16 px, weight 600, −0.01em.
  - Nav: Library · Review · Calibration · Activity · Settings, 14 px, gap 28 px, full-height items. Active items
    are text colour at 600 with an accent inset underline. Inactive items are muted at 500.
  - Counts appear on Review (12) and Activity (6) as mono 11 px pills: tint fill, accent text, accent-line border.
  - Right side: "Watching 3 folders" (mono 12 px muted, with a 7 px `--sst-ok` dot), a 1×20 px divider, and an
    avatar (26 px circle, `--sst-panel-2`, initial at 12 px 600) followed by the username.
  - There is no theme control in the header (Screens 09 note: "Theme lives here (and on N anywhere), not in the
    header").

### A.6 Logo rules

- **Mark: "A · Converge"** (chosen). Offset frames arrive and register into one sharp frame, with a single star as
  the registration point.
  - Construction: 24 × 24 grid, frames 13 × 13 with r 2, offset 2.5 diagonal.
  - Strokes: 1.5 for the back frames and 2 for the front. Round caps.
  - Star: r 1.75 at the front frame's centre (14.5, 14.5).
  - Accent appears only on the front frame and the star. The back frames use the neutral: `#8b9baa` dark,
    `#55626e` light, `#e63a2c` night.
  - Concepts B (Reticle) and C (Platform S) were rejected. Their files exist under `assets/logo/concepts/` and must
    not be used.
- **Wordmark**: "SubStation", Inter Semibold, −0.02em tracking, camel-case S, always one word. Outline the text
  before exporting production SVGs. The header component uses −0.01em at 16 px.
- **Lockups**: horizontal (`substation-lockup-horizontal.svg`, viewBox 260 × 48) and stacked
  (`substation-lockup-stacked.svg`, 180 × 130).
- **Which file on which ground**:

  | Ground | File |
  |---|---|
  | Dark (primary) | Full colour: `substation-mark.svg`, `substation-lockup-horizontal.svg` (text `#e7edf3`, accent `#ee7bd0`) |
  | Light | Inverted: `substation-mark-light.svg`, `substation-lockup-horizontal-light.svg` (text `#0d141d`, accent `#a3307f`, back frames `#55626e`) |
  | Single colour, dark or light | `substation-mark-mono.svg` (`currentColor`) |
  | Night vision | `substation-mark-night.svg` (red only: `#ff4a3a` front, `#e63a2c` back) |

- **Clear space**: keep a quarter of the mark's height clear on every side. In lockups, the gap between mark and
  wordmark is a third of the mark's height.
- **Minimum size**: mark 16 px, horizontal lockup 96 px wide, stacked lockup 64 px. Below 24 px use
  `favicon-16.svg`, which is redrawn on a 16-unit grid and drops the rear frame. The SQMeter README gives
  "horizontal lockup 120 px wide" for SQMeter, which conflicts with SubStation's 96 px (see A.10).
- **Favicon**: 16, 32 and 48 px plus `favicon.svg`, all on a dark `#080d14` tile so they hold on light browser tabs.
- **App icon**: 512 px gradient tile in panel colours with a hairline edge and 22% corner radius. Export a 512 PNG
  for Unraid, TrueNAS, Synology and Docker Hub.
- **Social**: GitHub preview 1280 × 640 (`substation-social-1280x640.svg`, upload as PNG) and README header
  1280 × 320 (`substation-readme-banner.svg`).
- **Family with SQMeter**: both use the same grid, stroke, radius and wordmark typeface, with one neutral and one
  accent per mark. When both appear, each keeps its own accent. Separate them by at least one mark width and align
  them on the wordmark baseline. Never overlap or merge the two marks into one badge (SQMeter guide).
- **Do and don't**:
  - Do use the full-colour mark on dark.
  - Do keep Orchid for brand and action, and status colours for verdicts.
  - Do always pair a verdict colour with its shape and glyph.
  - Don't use SQMeter cyan in the mark or as the accent.
  - Don't use a cyan tab underline or mix accents.
  - Don't borrow SQMeter's name pattern ("SQ Station") or colour part of the wordmark.
  - Don't place the mark on purple-to-blue gradients or nebula photos.
  - Don't rotate, stretch or add glows.
  - Don't separate verdicts by shades of red in night vision.

### A.7 Verdict system (seven states)

Three grades apply to subs and four states apply to datasets and masters. Filled shapes are final decisions.
Outlined shapes are states that will change. Each state has a distinct silhouette and glyph, so colour is a third
cue. SVG paths are on a 16-unit box.

| State | Scope | Shape | Glyph | Token | Meaning (guide copy) |
|---|---|---|---|---|---|
| Accepted | Sub grade | Solid circle | Tick | `--sst-ok` | Stacked at full weight. |
| Down-weighted (full name "Kept, down-weighted") | Sub grade | Solid triangle, point down | Bar | `--sst-warn` | Stacked at reduced weight. Usable, but softer or noisier than the night median. |
| Rejected | Sub grade | Solid square | Cross | `--sst-bad` | Left out of the stack. The file is kept on disk. |
| Awaiting calibration | Sub or dataset | Dashed circle (2.2 1.6) | Clock hands | `--sst-dim` | No matching dark, flat or bias yet. Graded once calibration frames arrive. |
| Integrating | Dataset | Hexagon outline | Three layers | `--sst-accent` | A master is being stacked from accepted subs. |
| Stale (lists say "Master stale") | Master | Square outline | Slash | `--sst-muted` | The master is older than its inputs: new subs, new calibration or changed grades. |
| Needs reconciliation | Dataset | Diamond outline | Exclamation | `--sst-violet` | Files on disk no longer match the catalogue. Review before stacking. |

On filled shapes the glyph is drawn in `--sst-bg`. On outlined shapes the glyph uses the state colour. Strokes are
1.25 for the shape and 1.5 for the glyph, with round caps and joins. Chart markers follow the same shapes:
down-weighted points are triangles and rejected points are squares.

### A.8 Keyboard

The brand guide lists J or ← (previous), K or → (next), Space (blink), A (accept), W (down-weight), R (reject),
U (undo), Z (zoom 1:1), N (night vision) and ? (all shortcuts). Other files add:

- Screens 07: B (compare with best).
- A2: U means revert to the auto grade, I opens metadata, and Shift with A, W or R applies to the run of flagged
  subs.
- D1: click selects, shift-click selects a range, Ctrl/Cmd-A selects the session.
- 01: Enter submits sign-in.
- 04: Enter opens the selected sub in Review.

The key legend is always visible in Review.

### A.9 Voice and writing style

- Write like a careful observing partner: state the measurement, compare it to something the user knows, then give
  the likely cause. Use British spelling (colour, catalogue, normalise, winsorised, grey). No exclamation marks, no
  hype, no "AI-powered" and no "smart". Contractions are fine ("Couldn't", "can't").
- Use sentence case for titles, buttons, tabs and chips ("Open review", "Stack 15 subs", "Pause new work", "Save and
  re-grade"). Uppercase appears only through the 11 px label style, plus the D2 "MANUAL" tag.
- Reasons are one sentence in the form "<measure> <value>, <comparison>: likely <cause>." Examples from the files:
  - "Star count 41% of the night median: likely cloud."
  - "FWHM 2.94″, 38% above the night median: likely poor seeing. Kept at weight 0.55."
  - "Stars elongated (eccentricity 0.71, median 0.38): likely a guiding error or wind."
  - "Accepted manually. You overrode a down-weight on 9 October."
  - "No dark matches gain 100 at −10 °C. Add darks to the calibration library to grade this sub."
  - "Master built before 14 new subs were accepted. Re-stack to include them."
  - A second evidence sentence may follow: "Background 38% above median in the same sub. Five neighbouring subs
    show the same pattern."
- Empty state: name the watched folder, say what will happen and when, and link to the fix. "No subs yet.
  SubStation is watching `/data/incoming`. New FITS or XISF files will appear here within a few seconds of landing.
  Check your capture software's output folder."
- Error: say what happened and why, reassure, give the fix, then name the action. "Couldn't write the master. The
  volume at /data/masters is read-only. Your subs and grades are safe. Mount it with write access, then choose
  Retry."
- Sign-in error goes under the field it relates to: "That password doesn't match. Check caps lock and try again."
- Release notes: a short "<version> <date>" heading, then one plain paragraph per change, ending with "Fixed: …".
- **Numbers and units**:
  - Use en-GB thousands separators ("1,358").
  - Use tabular figures.
  - Use the true minus sign U+2212 ("−10 °C").
  - Put a space before units ("300 s", "571 ADU", "490 mm", "1.0 TB", "−10 °C").
  - No space before ″, %, ° or × ("2.14″", "41%", "87.2°", "1.20×").
  - Write arc-seconds per pixel as "1.58″/px" and sky brightness as "20.31 mag/arcsec²".
  - Use × for counts and fields ("18 subs × 600 s", "2.71° × 1.81°").
  - Write coordinates as "20h 58m 47s +44° 19′ 52″" and offsets as "3′ 12″".
  - Show signs on rotations ("+5.1°", "−32.0°").
  - Use ≈ for estimates ("≈ 9 min").
- **Durations**:
  - Integration: "14h 00m", "2h 30m", "45m" (zero-padded minutes, no space). The readouts render "14h 00m" with
    smaller unit letters.
  - Job time: "4 min 12 s", "1 min 50 s", "42 s".
  - Time left and relative time: "about 9 min left", "3 min ago", "4 minutes ago", "idle since 28 Sep",
    "Unused · 19 months".
- **Dates and times**:
  - Long dates in headers and prose: "7 October 2026", "Night of 7 October 2026".
  - Short dates in tables and lists: "7 Oct 2026", "7 Oct", "Aug 2023".
  - Date with time: "8 October 2026, 01:32" or "9 Oct 2026, 10:14".
  - 24-hour clock: "23:50:04", "22:02".
  - Ranges: "to" in prose ("14 August 2023 to 7 October 2026", "Aug 2023 to Oct 2026") and an en dash for times and
    figure ranges ("23:27–23:42", "58–80°").
- **Separators and placeholders**:
  - Separate meta items with " · ".
  - Truncated file names start with an ellipsis ("…_0007.fits"). Menus use "Choose…".
  - Missing table values show a dash ("–" in the brand guide, "—" in v2; see A.10).
  - Missing metadata shows "Not recorded". It is never hidden.
- **Names**:
  - Catalogue objects take a space: "M 101", "NGC 7000", "IC 1805".
  - Filters: "Hα" (Greek alpha), "OIII", "SII", "L", "OSC".
  - Rigs: "Askar 71F". Datasets: "Rig · Filter (· Framing)".
  - Capture software: "N.I.N.A." in metadata copy.
  - Plurals follow the count ("1 dataset", "6 datasets").
- Keep marketing copy off app screens; the sign-in screen has none.
- Marketing (for docs and README):
  - Recommended headline: "Every sub graded. Every decision explained."
  - Taglines: "Calibrate, grade and stack your subs as they land." and alternatives.
  - Hero copy: "SubStation watches your capture folder, calibrates and grades each sub as it lands, and stacks
    finished datasets into masters. Free, open source and self-hosted."
  - Calls to action: "Install with Docker" and "Read the docs".

## Decisions where the design files disagree

Taken on the recommendation in the design review (owner may overrule):

| Topic | Values seen | Recommendation |
|---|---|---|
| Navigation | Brand 9a "Datasets · Review · Calibration · Settings"; Screens "Datasets"; v2 header "Library · Review · Calibration · Activity · Settings" | v2 (already amended into 001) |
| Down-weight override label | "Keep W" (brand 9c), "Weight W" (Screens 07, D2, D3, A2), "Down-weight W" (D1 bulk bar, key legends) | Buttons "Weight W", bulk bar and legend "Down-weight" |
| Reject override when already rejected | "Reject R" vs "Keep rejected R" (A2) | Label reflects the current auto grade (A2) |
| Stale label | "Stale" (guide) vs "Master stale" (lists in Screens and v2) | "Master stale" in lists, "Stale" as the version tag |
| Grading reference | "night median" (v1, brand) vs "session median" (v2) | v2 (session = one dataset's subs on one night; same thing) |
| Missing value | "–" (brand tables) vs "—" (Screens, v2) | Pick one; v2 uses "—" |
| Wordmark tracking | −0.02em (guide) vs −0.01em (header component, 16 px) | −0.02em for the logo file; the live header text may use −0.01em |
| Lockup minimum | 96 px (SubStation guide) vs 120 px (SQMeter README "shared") | 96 px for SubStation |
| Readout value size | 44 px (guide component), 34–36 px (screens), `--sst-fs-readout` 48 px | 34–36 px in app readouts |
| Weak flat rule | D4 and A3 "more than 21 days apart" is weak | Withdrawn by owner (002 amendment): age alone is never weak |
| Active segment style | Accent fill with on-accent text (guide header) vs tint and accent text (Settings) | Tint and accent text inside the app |

---
## Amendment 2026-10-11 (owner): loading bar, folding sections

- **007-DR-17 Busy bar.** A thin accent bar along the top while any first load, changed filter or save takes over
  200 ms; background polling doesn't show it.
- **007-DR-18 Shared pieces.** Spinner, Skeleton, Collapsible (remembered per browser) and LoadMore (next page as
  the end of a list scrolls into view) are the shell's own components.
## Amendment 2026-10-11 (owner): actions answer at once

- **007-DR-19 Optimistic actions.** Every action changes what's on screen the moment it's pressed (a verdict, a
  cancelled job, a renamed rig, a queued build); the server confirms afterwards. If it refuses, the change is
  undone and a toast says what didn't save. Repeated presses on the same thing run in order, so the last one
  wins and nothing piles up.
- **007-DR-20 Toasts.** Short notes in the corner for a failed action (kept 7 s) or an action that leaves no other
  trace ("Moved to the front"); the same note twice shows once.
- **007-DR-21 Sections fold everywhere.** Every major section on Library, Collection, dataset tabs, sub detail,
  Review, Night, Calibration (library and set), Settings, Reconcile and the frame drawer folds; the choice is
  remembered per browser and a link to a section opens it.
- **007-DR-22 Long lists load as you scroll.** Any list that can run past ~60 items (subs, sessions, datasets,
  masters, raw sets and nights, calibration frames, users, path-pattern previews, reconcile groups, review queue)
  shows a slice and grows as its end scrolls into view, inside a pane that scrolls on its own with its headings
  pinned. Sorting and filters apply first; changing them starts again from the top.
- **007-DR-23 Tables line up.** Tables fill their card with the same cell padding; numbers right-aligned on one
  line; row actions on one line, right-aligned.
- **007-DR-24 Hover to see a frame.** Hovering a file name or frame reference (reconcile files, quality table,
  master inputs, calibration frames, review) shows the frame beside the pointer after a short pause, from its
  existing preview or a small one drawn from the file and cached (`GET /frames/{sha}/glance`).

## Amendment 2026-10-13: scrolling panes hand off to the page

- **007-DR-25**: A pane that scrolls inside the page (tables, queues, frame grids) lets the page carry on scrolling
  once the pane reaches its end, so the pointer is never stuck inside one. No pane sets `overscroll-behavior:
  contain`.

## Amendment 2026-10-14: search from the header

- **007-DR-26**: The header has a search box (focused with "/" from anywhere). Typing two or more characters lists
  matching collections, datasets, nights and files, grouped, with the arrow keys and Enter to open one. A word
  matches any part of a name; a catalogue designation matches with or without its space ("ngc7635", "NGC 7635"); a
  date or partial date ("2026-09") finds nights; three or more characters also match file names. Binned files are
  not listed.

## Amendment 2026-10-14: accessibility is checked, not hoped for

- **007-DR-27**: SubStation meets WCAG 2.2 level AA in all three themes (dark, light, night vision). Two checks enforce
  it: every jsx-a11y lint rule is an error (alt text, labelled controls, keyboard equivalents for pointer handlers,
  no positive tabindex, valid ARIA, and the rest), and CI runs axe (WCAG 2.0/2.1/2.2 A and AA) against the real stack
  on every screen (Library, a dataset, Calibration, Reconcile, Settings, Activity, Map, Bin) in each theme and on the
  sub viewer. A violation fails the build. Map tiles are third-party pictures and are left out of the scan.
- **007-DR-28 Search reads dates as people type them.** Besides 2026-10 and 2026-10-14, search finds nights from a
  month name ("october", "oct 2026"), a day and month in either order ("14 october", "oct 14th"), UK numeric dates
  ("14/10", "14/10/2026") and "yesterday", "last night", "tonight". Typing "october" had found nothing.
