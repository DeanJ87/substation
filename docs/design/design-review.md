# SubStation design review

Date: 10 October 2026. Read-only review of every SubStation design file against the specs (001–006) and the built
frontend (`frontend/src`). Nothing in the source folders was changed.

**Sources read**

| File | What it holds |
|---|---|
| `~/Downloads/SQMeter logo and dashboard(1)/SubStation Brand Guidelines.dc.html` (937 lines) | Brand guide 1.0: logo, colour, type, verdicts, components, screens 9a–9c, docs theme, marketing, voice, do and don't |
| `…/SubStation Screens.dc.html` (590 lines) | v1 product screens 01–09 at 1440 px, with design notes |
| `…/SubStation v2 Library.dc.html` (271) | L1–L3 (copy in `docs/design/v2/SubStation_v2_Library.txt`) |
| `…/SubStation v2 Dataset.dc.html` (334) | D1–D5 (copy in `docs/design/v2/SubStation_v2_Dataset.txt`) |
| `…/SubStation v2 Activity.dc.html` (246) | A1–A4 (copy in `docs/design/v2/SubStation_v2_Activity.txt`) |
| `…/SubStationHeader.dc.html` (identical to `docs/design/v2/SubStationHeader.dc.html`) | Shared app header component |
| `…/design-system/substation-tokens.css`, `README.md`, `mkdocs/stylesheets/substation.css` | Tokens, asset list, docs theme (copies in `docs/design/design-system/`) |
| `…/assets/logo/*`, `assets/favicon/*`, `assets/app-icon/*`, `assets/social/*` (copies in `docs/design/assets/`) | Logo, favicon, app icon, social SVGs |
| `…/SQMeter Brand.dc.html`, `SQMeter Logo Torch.dc.html`, `SQMeter Feature Sheet.dc.html`, `sqmeter-tokens.css` | Sibling brand; used only where it constrains SubStation |
| `…/uploads/pasted-1791582305244-0.png` | Screenshot of an earlier SubStation build (v1 Datasets with a theme select in the header) |

Line numbers below refer to the `.dc.html` files in the Downloads folder.

Version note: v2 (L, D, A screens) supersedes v1 (Screens 01–09) and the brand guide's screens 9a–9c wherever they
overlap. Spec 001's 2026-10-10 amendment already adopts the v2 navigation. v1 is still the only source for the
sign-in screen (01), the first-run empty state (03), some master-detail fields (06) and the calibration type tabs (08).

---

## A. Brand guidelines summary

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

### A.10 Conflicts between design files (owner decision needed)

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

## B. Screen inventory

### B.1 Shared header — `SubStationHeader.dc.html` (lines 9–28; script 31–43)

- **Purpose**: the app frame on every signed-in screen.
- **Elements**: see A.5. Nav items are Library, Review (badge "12"), Calibration, Activity (badge "6") and
  Settings. Right side: "Watching 3 folders" with a green dot, then avatar "A" and "admin".
- **Interactions**: active item underlined. No theme switch, no sign-out button and no queue indicator are shown.

### B.2 Brand guide product screens — `SubStation Brand Guidelines.dc.html`

| Label | Line | Purpose | Key elements and copy | Superseded by |
|---|---|---|---|---|
| 9a Datasets dashboard | ~438 | Home | Readouts: Accepted tonight "65 of 78 subs · M 101 Hα"; Integration "61 h 40 m accepted, all datasets"; Queue "2 awaiting calibration"; Disk "1.8 TB free on /data". Dataset cards: target, "Pinwheel Galaxy · 3 nights", state badge, integration "34h 20m accepted", split bar, "412 ✓ 61 ▾ 13 ✕", filters, one-line note ("Stacking Hα master, 70 new subs from last night."; "7 files were moved outside SubStation. Review before stacking."; "New flats since the last master on 2 October."; "12 subs waiting for darks at −10 °C, gain 100."). Header "watching /data/incoming" | L1 |
| 9b Dataset view | ~475 | Night chart and metrics table | Breadcrumb "Datasets / M 101". Title "M 101 · Hα" with "Night of 8 October 2026 · 78 subs × 300 s · gain 100 · −10 °C". Buttons "Open review" and primary "Stack 70 subs". Tabs Subs, Night chart, Calibration, Masters. "Quality across the night": three charts (FWHM, Star count, Background) on a shared axis with a night-median dashed line, down-weighted triangles, rejected squares and a cloud band. Table: Verdict, Time, File, FWHM, Stars, Bg ADU, Weight, Reason | D2 |
| 9c Blink review | ~547 | Review one sub | "M 101 · Hα · 8 Oct", "45 / 78", toggles Fit, "Blink 4 Hz", Auto-stretch. Preview with file name and time. Verdict "Rejected" with two-sentence reason. Stats: FWHM 2.31″, Stars 760 / 1,812, Background 571 ADU, Eccentricity 0.41. Override: Accept A, Keep W, Reject R. Thumbnail strip with the selected sub in accent. Key legend J/←, K/→, Space, A, W, R, U, Z, N, ? | A2 |
| 10 Docs theme | ~606 | MkDocs Material override | Three palette schemes (`substation`, `substation-light`, `substation-night`), self-hosted fonts, tabs with accent underline, underlined links, tables with uppercase headers. Sample page "Docker Compose" with the note "SubStation never deletes or moves your original subs." | — |
| 11 Marketing hero | ~652 | Landing, social, README | See A.9. Live card: "Last night · M 101 Hα 65/78 subs accepted · 5 down-weighted · 5 h 50 m stacked". `docker run -v /astro:/data ghcr.io/substation/substation` | — |
| 12 Voice samples | ~709 | Copy patterns | Verdict reasons, empty state, error, release notes 0.4.0 ("Night-vision mode. Press N anywhere…", "Blink review loads the next 20 subs in advance…") | — |

### B.3 v1 product screens — `SubStation Screens.dc.html` (theme switch and notes in Tweaks)

| Label | Line | Purpose and design note | Key elements, copy and interactions |
|---|---|---|---|
| 01 Sign in | 28 | "Single local account by default. Error text sits under the field it relates to. Enter submits. No marketing on this screen." | Centred 380 px column. Mark at 36 px with "SubStation" at 24 px. Card titled "Sign in" with "to the SubStation on `observatory.local`". Fields Username and Password (with a red border on error) and "That password doesn't match. Check caps lock and try again." Primary "Sign in". Footer "SubStation 0.4.0" |
| 02 Datasets | 45 | Home, grouped by target, newest night first. State badge only when there is something to act on. "Needs attention" filters to awaiting, stale and reconciliation | Title "Datasets" with "8 datasets · 2 targets · 14h 00m accepted". Filter "Filter by target, panel or filter". Segments All / Needs attention 3 / Integrating 1. Readouts: Last night 38, Integration 14h 00m, Processing 6 ("subs in progress · 6 workers"), Disk 1.0 TB. Target group header "Heart Nebula · IC 1805 · Cassiopeia · 5 datasets · 6h 30m". Table columns Dataset, State, Accepted, Grades (split bar and "9 accepted 2 weighted 2 rejected" or "Not graded yet"), Last night, chevron |
| 03 Datasets, first run | 97 | "Shown until the first sub is catalogued. Names the watched folder, says what will happen and when, and links to the fix if nothing arrives." | Icon, "No subs yet", "SubStation is watching `/data/library/capture`. New FITS or XISF files will appear here within a few seconds of landing." Buttons "Change watched folders" and "Import an existing archive" |
| 04 Dataset, subs | 114 | "Primary action stacks the accepted and weighted subs and states the count. Grid thumbnails are auto-stretched; the verdict sits on a bg-coloured disc. Chips filter by grade. Selected sub takes the accent border; Enter opens it in Review." | "Datasets / NGC 7000". "NGC 7000 · Panel 1 · OIII" with "Night of 7 October 2026 · 18 subs × 600 s · gain 100 · −10 °C". Buttons Re-grade, Open review, primary "Stack 15 subs". Tabs Subs 18, Night chart, Calibration, Masters. Readouts: Accepted integration "2h 30m" (15 of 18 subs kept), Median FWHM, Median stars, Background. Chips All 18 / Accepted 13 / Down-weighted 2 / Rejected 3. "Sort Capture time". Thumbnail grid showing time, file and "2.31″ · 1,234 stars" |
| 05 Dataset, night chart | 160 | "Three metrics on a shared time axis. Dashed line is the night median; the tinted band marks a detected cloud pass… hovering a row highlights its point." | Legend: down-weighted, rejected, night median, cloud pass. Table as in 9b with the selected row tinted |
| 06 Dataset, masters | 233 | "Every stack is kept as a version with its inputs. Only the newest can be current; older ones are marked superseded and can be deleted. The right column shows the calibration frames that were matched…" | "Master v3 Current. Stacked 8 October 2026, 01:32 · took 4 min 12 s". Buttons "Show in folder" and "Download XISF". Integration 2h 30m, Inputs "13 + 2 full + weighted", FWHM 2.36″, SNR gain 3.7×. Rejection "Winsorised sigma clip, 3.0 low / 3.0 high". Weighting "SubStation grade weights". Registration "Reference …_0007.fits, 1,412 stars matched". File path. "Master v2 Superseded … replaced after you rejected …_0011.fits in review" with Delete. Right column "Calibration used, matched automatically": Dark, Flat and Bias, each with a match sentence. "Choose different frames" |
| 07 Review | 288 | "Queue of flagged subs across all datasets, left. Blink viewer centre, verdict and metrics right. The reason is a full sentence… Overrides are one key each and move to the next sub. Everything works from the keyboard; key legend is always visible." | Grid 280 px / fluid / 320 px. Left: "To review · 12 subs" with queue cards (name, count, "7 Oct · 3 rejected, 2 weighted") and "Flagged means rejected, down-weighted, or within 10% of a threshold." Centre: "NGC 7000 · P1 · OIII · 7 Oct", "11 / 18", Fit, Blink 4 Hz, Auto-stretch, Compare with best, preview, strip. Right: Verdict Rejected, reason, stats (value against median), Override Accept A, Weight W, Reject R, "Overrides are logged and survive a re-grade." Legend J K Space A W R B N |
| 08 Calibration | 357 | "Anything blocking grading is shown first, with exactly what SubStation is looking for. The table shows what each master matches and how many datasets use it." | "Calibration" with "9 masters from /data/library/calibration · last scan 3 min ago" and "Rescan library". Banner "Heart Nebula · Panel 2 · OIII is waiting for a flat. 2 subs can't be graded yet. SubStation is looking for an OIII flat at rotation 112° ± 2°, taken within 30 days of 7 October 2026." with "Use nearest flat". Tabs All 9 / Darks 2 / Flats 6 / Bias 1. Columns Type, Matches, Frames, Created, Used by, State (Current, Older than 30 days) |
| 09 Settings | 390 | "One page, sections in the left rail. Grading thresholds are relative to each night's median and say so. Theme lives here (and on N anywhere), not in the header. Changes save with one bar at the bottom; grading changes offer a re-grade." | Rail: Folders, Grading, Stacking, Notifications, Appearance, Users. Folders: "New files in these folders are catalogued within a few seconds." with "Add folder", rows path / role / status with a dot / Edit, and output "1.0 TB free of 4.0 TB". Grading table Metric / Down-weight when / Reject when. Appearance: "Night vision switches to red on black. Press N anywhere to toggle it." with a Dark / Light / Night vision segment. Save bar "Unsaved: FWHM reject threshold changed from 1.60× to 1.50×. 4 datasets would be re-graded." with Discard and "Save and re-grade" |

### B.4 v2 Library — `SubStation v2 Library.dc.html`

Data model: a dataset is one rig, one filter and one framing over any number of nights. A collection groups datasets
of one object. Collections are suggested from the plate-solved centre and overlap, and the user confirms.

| Label | Line | Purpose (design note) | Key elements, copy and interactions |
|---|---|---|---|
| L1 Library | 29 | "Home. Collections first, then datasets that aren't in a collection yet, each with SubStation's suggested collection and the overlap it measured. The Processing readout links to Activity. Cards show integration per filter so gaps are visible at a glance." | Title "Library" with "16 datasets in 4 collections, 2 ungrouped · 3 rigs". Search "Search objects, rigs, filters", chip "Rig All", button "New collection". Readouts: Last night 38 ("subs · 7 October 2026 · 2 rigs", accent), Accepted integration 134h 35m ("all collections"), Processing 6 ("workers busy · Hα master integrating"), Disk 1.0 TB ("free on /data/substation"). **Collections** cards (200 px preview column showing the master preview with dataset framings overlaid as rectangles): name, "NGC 7000 · IC 5070 · Cygnus · 6 datasets", rig pills, per-filter bars with "50h 50m", "Aug 2023 to Oct 2026 · 80 sessions", total "101h 25m", state badges (Integrating, Master stale, Awaiting calibration, Needs reconciliation). **Not in a collection** rows: name "IC 1805 · Seestar S30 Pro · OSC", meta "2 sessions · 420 subs × 10 s · from 3 and 4 October 2026", integration, suggestion "Suggested: Heart Nebula. Centre 6′ away, 88% overlap." or "No existing collection within 2°. Plate-solved as Crescent Nebula.", buttons "Choose…" and "Add to Heart Nebula" or "New collection" |
| L2 Collection | 85 | "One object across rigs and years. Framing shows every dataset's plate-solved field over the reference framing. The matrix shows accepted integration by rig and filter. The sessions timeline shows every night on every rig… Datasets open the dataset screens." | "Library / Collections". Title "North America and Pelican" with "NGC 7000 · IC 5070 · 6 datasets · 3 rigs · 80 sessions from 14 August 2023 to 7 October 2026". Buttons Add datasets, Edit collection, Stack combined masters. Tabs Overview, Datasets 6, Sessions 80, Masters 9. **Framing** "from plate solves · north up": reference master preview with rig fields drawn (reference in accent, others muted or dashed) and a legend (field "2.71° × 1.81°", scale "1.58″/px", overlap "100%"). **Matrix** "Accepted integration by rig and filter": rows rig, camera, focal length and scale with "reference" or framing label, a Total row in accent. **Combined masters**: "One master per filter. Every dataset is registered to the reference framing and resampled to 1.58″/px. Subs are weighted by their grade and by each rig's measured SNR." with the warning "Hα combined master is stale: 41 new subs since 2 October." **Sessions** timeline per rig ("bar height is accepted integration that night · select a range to filter the datasets below"). **Dataset table**: Dataset (name and meta), State (badge "Integrating v7" / "Master stale" or "Master current · 2 Oct"), Sessions, Accepted, Grades (split bar and "452 of 541 kept"), Last night ("7 Oct 2026") |
| L3 Add datasets to a collection | 156 | "Opened from a collection or from an ungrouped dataset. Candidates are ranked by plate-solved centre distance and overlap with the reference framing. Low overlap is allowed and marked as a separate panel. Nothing is moved on disk; collections are catalogue-only." | Modal (860 px, scrim). Title "Add datasets to North America and Pelican" with "Matched against the reference framing, Askar 71F · Hα, centred at 20h 58m 47s +44° 19′ 52″." Columns checkbox, Dataset, Centre offset, Rotation, Overlap (bar, % and note). Notes include "Matches the existing Cygnus Wall panel", "Partial overlap. Kept as its own panel", "Different rotation. Will be re-registered", "No overlap. Different object". Candidates may already be in another collection ("In collection “Cygnus 2022”"). Footer "Reference framing Askar 71F · Hα", Cancel, primary "Add 2 datasets" |

### B.5 v2 Dataset — `SubStation v2 Dataset.dc.html`

Shared note: "Grading is automatic. Every verdict can be overridden per sub or in bulk, from any screen that lists
subs. Overrides are marked Manual, logged, and survive a re-grade. Metadata… is shown where present and marked Not
recorded where not."

Shared header:

- Breadcrumb "Library / North America and Pelican".
- Title "Askar 71F · Hα" with "31 sessions · 541 subs × 300 s · gain 100 · −10 °C · 14 August 2023 to 7 October
  2026".
- Buttons Re-grade, Open review, "Integrating v7 · 52%".
- Tabs Subs 541, Quality, Calibration, Masters 7.

| Label | Line | Purpose (design note) | Key elements, copy and interactions |
|---|---|---|---|
| D1 Subs | 29 | "Grouped by session, newest first, with each session's conditions in its header. Click selects, shift-click selects a range, Ctrl/Cmd-A selects the session. The bulk bar appears with a selection; A, W and R apply to every selected sub. A small M marks a manual override." | Chips: "Sessions All 31", Accepted 452, Down-weighted 44, Rejected 45, Manual 4; "Sort Capture time". Bulk bar: "3 selected from 7 October 2026", Accept A, Down-weight W, Reject R (with kbd), Clear override, Open in review. Session header: "7 October 2026 · 24 subs · 2h 00m · SQM 21.12 · 8.1 °C · 82% RH · guiding 0.62″ · cloud 23:27–23:42 (SQMeter)". Tiles: verdict disc, M marker, selection checkbox (accent when selected), "…_0019", "2.52″ · 598" |
| D2 Quality | 74 | "Top: every session… Each bar is the 10th to 90th percentile for that night with its median as a dot; SQM and guiding come from capture headers and leave gaps where they weren't recorded. Click a session to fill the lower chart and table… The inspector on the right shows the selected sub's image, verdict and overrides. Grading compares each sub with its own session's median." | "Sessions · 31" with year chips All, 2026, 2025, 2024, 2023. Five rows: FWHM "median 2.38″", Stars "median 1,340", Background "median 446 ADU", SQM "20 of 31 recorded", Guiding RMS "25 of 31 recorded". Gaps drawn as ×; outliers in warn; selected session in accent. Axis "Aug 2023 … 7 Oct". Lower chart "7 October 2026 · 24 subs" with FWHM and SQM lines, weighted and rejected markers, median and cloud band. Table columns: (selected indicator), Grade (three-segment accept / down / reject control per row with the active one highlighted, plus M), Time, FWHM, Stars, Bg, SQM, Alt, Reason ("Manual. Auto: FWHM 2.71″, 17% above the session median."). "Show all 24 subs". Inspector: preview with "Open full size", "NGC7000_Ha_300s_0014.fits · 22:02", "Accepted MANUAL", "Auto grade was Down-weighted: FWHM 2.71″, 17% above the session median. You accepted it at 9 Oct 2026, 10:14.", Accept A, Weight W, Reject R, "Revert to auto grade", stats FWHM / Stars (vs session), Background, Eccentricity, SQM (SQMeter), Altitude ("airmass 1.12"), "All metadata" |
| D3 Sub detail | 134 | "Everything known about one sub. Each field is tagged with where it came from… Fields with no source show Not recorded rather than hiding… Raw header is one click away." | Breadcrumb "North America and Pelican / Askar 71F · Hα / 7 October 2026" with the title as the file name in mono. "19 / 24", Previous J, Next K. Preview "auto-stretched · star detections overlaid" with modes Auto-stretch / Linear / Stars / FWHM map. Verdict "Rejected · auto · graded 7 Oct 2026, 23:33" with Accept A, Weight W, Reject R. Reason "Star count 44% of the session median: likely cloud." and evidence "SQM dropped from 21.12 to 20.31 at the same time and SQMeter reported cloud. Subs 18 and 20 show the same pattern." Sections, each with uppercase source tags (SubStation, Solve, Header, SQMeter): **Measured** (SubStation; FWHM "2.52″ · 1.59 px", Stars "598 of 1,358 median", Background "519 ADU · +17%", Eccentricity, SNR); **Plate solve** (ASTAP · 1.4 s; Centre, Rotation, Pixel scale, Field, Offset from reference); **Capture** (N.I.N.A. 3.1 header; Camera with gain and offset, Sensor temperature and set point, Filter with wheel slot, Focuser with temperature, Guiding RMS RA/Dec, Mount alt/az/pier, Airmass); **Conditions** (SQM "20.31 mag/arcsec²", Cloud "Cloudy · sky −6 °C vs ambient 8 °C" from SQMeter, Ambient and dew point, Wind "Not recorded", Moon "23% · 41° away"). "Show raw FITS header · 142 keywords" |
| D4 Calibration | 169 | "Which dark, flat and bias each session was calibrated with, and how good the match is. Flats are matched per session… Weak matches are flagged in plain English; any session can be pointed at different frames, which re-calibrates and re-grades only that session." | Warn banner "2 sessions have a weak flat match. Their flats were taken more than 21 days apart… Grading still ran." (the 21-day rule is withdrawn; see A.10). Columns Session, Subs, Dark ("Dark 300 s −10 °C · 30" / "Exact match"), Flat ("Flat Hα 87.2° · 5 Oct 2026" / "Same rotation · 2 days before", in warn when weak), Bias ("Bias gain 100 · 100"), Change. "Show all 31 sessions" |
| D5 Masters | 198 | "An integration in progress appears at the top with its pipeline steps and links to the worker running it. Finished masters are versions with their inputs and settings. A master goes stale when its inputs change; the reason is stated." | Running card "Master v7 · integrating" with "496 subs from 31 sessions · started 10:02 · about 9 min left · 4 workers", "View in Activity", Cancel. Steps: Select inputs (496 subs), Calibrate (cached), Register 496 / 496, Normalise 308 / 496, Integrate (winsorised σ), Write (XISF 32-bit). Versions: preview, "Master v6" with a Current tag in ok colour, "455 subs · 29 sessions · 2 Oct 2026, 08:40 · winsorised σ 3.0 · grade weights", Integration, FWHM, Download and Inputs. Superseded rows are tagged in muted with the reason "replaced by v6 (2 new sessions)" |

### B.6 v2 Activity, review, calibration, settings — `SubStation v2 Activity.dc.html`

| Label | Line | Purpose (design note) | Key elements, copy and interactions |
|---|---|---|---|
| A1 Activity | 28 | "What every worker is doing right now. Jobs show their pipeline steps, the current step's progress, which workers are on it and the last few log lines. The queue can be reordered and paused. Failures stay at the top of Recent until retried or dismissed, with the cause in plain English." | Title "Activity" with "6 workers · 3 jobs running · 9 queued". Buttons Pause new work and Worker settings. Readouts with meters: CPU 78% ("12 threads · 6 workers"), Memory "22.4 / 64 GB" ("integration buffer 14 GB"), Disk "210 MB/s" ("write · /data/substation"), Intake "Watching" in ok ("3 folders · last file 10:11"). **Running** job cards: title "Integrate master v7 · Askar 71F · Hα", worker chips "W3 W4 W5 W6", meta, ETA "≈ 9 min", "Open dataset" or "Pause", Cancel, step bars, and three mono log lines ("10:13:02 normalise NGC7000_Ha_300s_0309.fits scale 0.982 offset −3.1"; "failed M31_OSC_10s_1181.fits too few stars (cloud). Will use header RA/Dec"). **Workers** rows: id, coloured state verb ("Solving", "Normalising"), task, current file, CPU%. **Queue · 9** "drag to reorder", each row with a drag handle, number, task, meta ("calibration changed · 198 subs") and estimate ("3 min"), plus "Show 4 more". **Recent**: pinned failure "Couldn't write the SII master. The volume at /data/masters was read-only at 09:41. Subs and grades are safe." with Retry; rows "10:01 Graded 24 subs · Askar 71F · Hα · 7 Oct · 19 accepted, 2 weighted, 3 rejected 1 min 50 s" |
| A2 Review | 77 | "Flagged subs from every dataset, grouped by session. The right panel adds the session's conditions next to the sub's own numbers, so a cloud or guiding problem can be confirmed without leaving the viewer. A, W and R override and advance; U reverts to the auto grade." | Three columns. Left: "To review · 12" with queue cards ("Askar 71F · Hα 5", "NGC 7000 · 7 Oct · 3 rejected, 2 weighted"; the selected card is tinted) and the footnote "Flagged: rejected, down-weighted, or within 10% of a threshold." Centre: "Askar 71F · Hα · 7 Oct 2026", "2 / 5 flagged · sub 19 of 24", toggles Fit, Blink with best, Auto-stretch, Stars; preview "blinking against …_0009 (best of session)"; file and "22:22 · alt 64°"; thumbnail strip with verdict discs, selected in accent. Right: "Auto grade Rejected", reason and evidence ("SQM fell to 20.31 and SQMeter reported cloud from 23:27 to 23:42."), a Sub / Session table (FWHM 2.52″/2.38″, Stars 598/1,358 in bad, Background 519/444 in warn, SQM 20.31/21.12 in warn, Guiding RMS, Altitude 64°/58–80°, Cloud Cloudy/SQMeter), Override "Accept A · Weight W · Keep rejected R" and "Apply to subs 18 to 20 as well (Shift+key)". Footer legend J, K, Space, A, W, R, U revert to auto, I metadata, N night vision |
| A3 Calibration | 105 | "Calibration masters per rig… Anything blocking grading is shown first with what SubStation is looking for. Each master lists the datasets and sessions using it." | Title "Calibration" with "21 masters across 3 rigs from `/data/library/calibration` · last scan 3 min ago". Chip "Rig Askar 71F" and "Rescan". Blocking banner "Heart Nebula · Askar 71F · OIII is waiting for a flat. 2 subs from 7 October 2026 can't be graded. Looking for an OIII flat at rotation 112° ± 2°, within 30 days." with "Use nearest flat". Table columns Type, Matches ("Askar 71F · 300 s · gain 100 · −10 °C"), Frames, Created, Used by ("9 datasets · 48 sessions"), State (Current in ok, "Kept for 2025 data" muted, "Weak match for 2" warn, Missing bad, "Unused · 19 months" muted) |
| A4 Settings | 121 | "One scrolling page; the left rail jumps to sections. Rigs are detected from headers and can be renamed. Metadata sources say which header keywords are read and what to do when a value is missing. One save bar at the bottom; changes that affect grades offer a re-grade." | Rail: Folders, Rigs, Grading, Stacking, Plate solving, Metadata sources, Notifications, Workers, Users, Appearance. Sections and rows are listed below this table. Sticky save bar: "Unsaved: FWHM reject threshold 1.60× → 1.50×. 9 datasets would be re-graded; manual overrides are kept." with Discard and "Save and re-grade" |

A4 sections and rows:

- **Folders** ("New files in these folders are catalogued within a few seconds.", Add folder):
  - `/data/library/capture` Lights · last file 3 min ago [Watching]
  - `/data/library/archive` Lights, archive · idle since 28 Sep [Watching]
  - `/data/library/calibration` Calibration frames [Watching]
  - `/data/substation` Output for masters and previews · 1.0 TB free of 4.0 TB [Change]
- **Rigs** ("Detected from TELESCOP, INSTRUME and FOCALLEN. Rename or merge them here.", Add rig): one row per rig,
  for example "ASI2600MM Pro · 490 mm · 1.58″/px · 61 sessions" [Edit].
- **Grading** ("Each sub is compared with the median of its own session."):
  - FWHM 1.20× / 1.50×
  - Star count 0.70× / 0.50×
  - Background 1.20× / 1.40×
  - Eccentricity (absolute) 0.50 / 0.65
  - "Use SQM and cloud when recorded" [On/Off]: "A sub is flagged, not rejected, on SQM or cloud alone"
- **Stacking** ("Defaults for dataset and combined masters."):
  - Rejection: Winsorised σ clip 3.0 / 3.0
  - Weighting: Grade / SNR / Equal
  - Registration reference: Best FWHM / Most stars / Manual
  - Auto-stack: After each session / Every 10 new subs / Never
  - Output: XISF / FITS, 32-bit float
- **Plate solving** ("Every sub is solved so it can be matched to datasets and collections."):
  - Solver `/usr/local/bin/astap` ("Local ASTAP with the D50 database")
  - Use header position as a hint: On / Off
  - When solving fails: Use header position / Leave unsolved
- **Metadata sources** ("Read from FITS and XISF headers when present. Nothing is required."):
  - Capture software: Auto-detect (N.I.N.A., ASIAIR, Seestar, SharpCap, Ekos from SWCREATE)
  - Sky quality: SQM keyword, SQMeter · sqmeter.local
  - Weather: Header (AMBTEMP, HUMIDITY, DEWPOINT, CLOUDCVR, WINDSPD)
  - Guiding: PHD2 log folder `/data/library/phd2`
- **Notifications** ("Sent when something needs you, not for routine work.", Send test):
  - Channels: ntfy · substation / Webhook / Email
  - Events: Master finished, Job failed, Awaiting calibration, Session summary
- **Workers** ("Parallel jobs. More workers use more memory."):
  - Workers: 6 ("6 of 12 CPU threads")
  - Priority: New subs first / In order
- **Users and appearance** (Add user):
  - admin: Owner · last signed in today 09:58
  - guest: "Read only · can review, can't override"
  - Theme: Dark / Light / Night vision ("Press N anywhere for night vision")

**Totals**: 1 header component, 3 brand-guide product screens (9a–9c), 3 brand-guide reference pages (docs theme,
marketing hero, voice samples), 9 v1 screens (01–09) and 12 v2 screens (L1–L3, D1–D5, A1–A4). That is **24 product
screens and states**, plus the header and 3 reference pages.

---

## C. Gap list (built frontend against the design)

Severity:

- **Major**: a missing screen, workflow or rule that the design or specs treat as core, or a brand or night-vision
  rule that is broken.
- **Minor**: a visual, copy or detail difference.

New specs proposed:

- **007** Brand, theme and app shell: tokens in use, header, sign-in, theme, logo, favicons, shortcuts help, docs
  theme.
- **008** Settings: the single settings page with save bar and re-grade offer.
- **009** Plate solving: framing, overlap, solve metadata. Spec 006 already says plate solving "is a later spec".

### Shell, brand and theme

| # | Screen | Sev | Spec | Built (file) | Design |
|---|---|---|---|---|---|
| G1 | Header | major | 007 | `routes/AppFrame.tsx` puts a theme `<select>` in the header (the earlier build screenshot shows the same) | Theme lives only in Settings → Appearance (segmented Dark / Light / Night vision) and on the N key; not in the header (Screens 09 note) |
| G2 | All (night vision) | major | 007 / 003 | Previews, thumbnails, master previews and calibration evidence images render in grey or white in night mode. `v2.module.css .banner` hard-codes `rgba(244,193,93,.06)` (yellow). `dataset.module.css` and `frames.module.css` use `rgba(0,0,0,…)` overlays | "Deep red on near-black only. No blue, green or white light." Every image must be rendered red-only in night mode, and no colour may sit outside the tokens |
| G3 | Header | minor | 007 | Height set by padding 10 px; lockup `<img>` 28 px high; nav items are padded boxes, all weight 600; header wraps | 56 px fixed, mark 22 px plus wordmark text, nav 14 px with gap 28 px, inactive items at 500, underline at the header's bottom edge |
| G4 | Header | minor | 007 | Review count is a solid `--sst-warn` pill and Activity count is solid accent (`frame.module.css .count`, `.countAccent`) | Both are mono 11 px pills with tint fill, accent text and an accent-line border |
| G5 | Header | minor | 007 | Right side shows "N to reconcile" link, `QueueIndicator`, plain "Watching N folders", the theme select, the username and a "Sign out" button | "Watching 3 folders" in mono with an ok dot, a divider, and an avatar with the user's initial and name (sign-out belongs in an account menu). The reconciliation entry comes from Library notices (001 amendment) |
| G6 | Header / Activity | minor | 005 | `features/queue/QueueIndicator.tsx` links to the legacy `/queue` page (`QueuePage.tsx`). Legacy `features/datasets/DatasetsDashboard.tsx` and `DatasetView.tsx` (v1 model) remain in the tree | One Activity screen. The Processing readout and the Activity badge are the queue indicator |
| G7 | Header logo | minor | 007 | Lockup is chosen per theme as an `<img>`; night mode shows the mark only, without the wordmark | Mark plus wordmark in every theme; night uses red-only artwork. An inline SVG mark using `--sst-muted` and `--sst-accent` with live text covers all three themes |
| G8 | Favicon / app icon | minor | 007 | Only `public/favicon.svg` (32 grid); no 16 px file, no 48, no app icon or touch icon, no `theme-color` | `favicon-16.svg` below 24 px (drops the rear frame), 32 and 48 px versions, 512 app icon with 22% radius for NAS app stores |
| G9 | Global type | minor | 007 | `design/base.css` lacks `font-feature-settings: 'cv11','ss01'` | The guide sets them on the body |
| G10 | Cards | minor | 007 | `ui.module.css .card` and `v2.module.css .card/.readout` use `panel-2 → panel`; `--sst-card-end` is never used | Cards use `panel → card-end`; readouts use `panel-2 → card-end` |
| G11 | Buttons | minor | 007 | `.primary` is transparent at rest and only tints on hover; default buttons are weight 600; disabled buttons use opacity 0.5 | Primary has the accent-tint fill at rest; secondary is weight 500; disabled uses a dashed line border with `--sst-dim` text |
| G12 | Verdict badge | minor | 007 | `VerdictBadge.module.css` uses a coloured border and coloured 600 text | Neutral pill (line border, `--sst-panel-3`, text colour, 500) with only the icon coloured |
| G13 | Page layout | minor | 007 | Page h1 30 px; readout values 32 px; main max-width 1400 px | Titles 24 px 600 −0.02em; readouts 34–36 px weight 500 −0.03em; container 1240 px with 32 px gutters |
| G14 | Keyboard help | major | 007 / 003 | No "?" overlay, no Z, B, I or Space; Review shows a one-line text hint | "? all shortcuts" overlay and an always-visible kbd legend in Review (A2, 07, 9c) |
| G15 | Docs | minor | 007 | `mkdocs.yml` uses `palette: scheme: slate` with no logo, favicon or `font: false` | Three schemes (`substation`, `substation-light`, `substation-night`) with toggles, self-hosted Inter and JetBrains Mono, logo and favicon |
| G16 | 01 Sign in | minor | 007 / 003 | `routes/SignIn.tsx`: lockup image; field "Username or email"; the server's (allauth) error text appears in one alert below both fields; extra line "Accounts are created by an admin…"; no version | Mark at 36 px with the wordmark at 24 px above the card; "Sign in" with "to the SubStation on <host>" in mono; the error sits under the related field with a red field border and the copy "That password doesn't match. Check caps lock and try again."; footer "SubStation <version>"; no other copy |

### Library and collections (006)

| # | Screen | Sev | Spec | Built (file) | Design |
|---|---|---|---|---|---|
| G17 | L1 | minor | 006 | `features/library/Library.tsx` has no "New collection" header button; the rig filter is a `<select>` reading "Rig: All" | "New collection" button next to search; rig chip "Rig All" |
| G18 | L1 | minor | 006 | Processing detail reads "workers busy · a master is integrating" | Names the job: "workers busy · Hα master integrating" |
| G19 | L1 / 03 | major | 001 / 006 | Empty library shows readouts plus the generic text "SubStation is watching your folders…" with no actions | First-run state replaces the content: "No subs yet", the watched folder path(s) in mono, "within a few seconds of landing", and buttons "Change watched folders" and "Import an existing archive" |
| G20 | L1 | minor | 006 | Ungrouped meta reads "2 sessions · 420 subs · last 4 October 2026" | "2 sessions · 420 subs × 10 s · from 3 and 4 October 2026" |
| G21 | L1 | minor | 006 / 009 | Card preview has no framing overlay; the objects line has no constellation | Framings drawn over the master preview; "NGC 7000 · IC 5070 · Cygnus · 6 datasets" |
| G22 | L2 | major | 006 | `CollectionView.tsx` is one long page with no tabs | Tabs Overview · Datasets N · Sessions N · Masters N |
| G23 | L2 / L3 | major | 006 | No "Add datasets" action and no L3 dialog; datasets join only from L1 suggestions; "Edit collection" is an inline rename | "Add datasets" opens L3: candidates ranked by centre offset, rotation and overlap, each with a plain-English note, checkboxes and "Add N datasets"; low overlap is kept as its own panel |
| G24 | L2 | major | 006 / 004 / 009 | No Framing panel, no Combined masters panel, no "Stack combined masters" | Framing from plate solves (field, scale, overlap per rig) and combined masters per filter with a stale notice ("Hα combined master is stale: 41 new subs since 2 October.") |
| G25 | L2 | minor | 006 | Dataset table: Grades column is text only; State column shows muted text "Master stale" with no badge; Last night uses the long date | Split bar plus "452 of 541 kept"; badges "Integrating v7" and "Master stale", or "Master current · 2 Oct"; "7 Oct 2026" |
| G26 | L2 | minor | 006 | Timeline is hover only ("Hover or focus a bar for details") | "Select a range to filter the datasets below" |
| G27 | L2 | minor | 006 | Rig rows lack the "reference" marker and framing label; dataset meta is "target · gain · bin"; Remove collection uses `window.confirm` | "490 mm · 1.58″/px · reference" and "Cygnus Wall"; dataset meta "Reference framing · 300 s · gain 100 · −10 °C"; confirmation built into the page |

### Dataset screens (003, 002, 004)

| # | Screen | Sev | Spec | Built (file) | Design |
|---|---|---|---|---|---|
| G28 | Dataset header | major | 003 | `dataset/DatasetScreen.tsx` has no Re-grade button, and there is no re-grade anywhere in the UI (US5 preview) | Re-grade · Open review · "Integrating v7 · 52%" in every dataset tab header |
| G29 | Dataset header | minor | 003 | "Open review" is a pill link to the global `/review` | A button that opens Review filtered to this dataset's flagged subs |
| G30 | Dataset header | minor | 003 | Summary omits sensor temperature and appends the camera | "31 sessions · 541 subs × 300 s · gain 100 · −10 °C · 14 August 2023 to 7 October 2026" |
| G31 | D1 | minor | 003 | `SubsTab.tsx` tile: verdict icon has no bg disc; the M chip uses `rgba(0,0,0,.5)` | Verdict on a `--sst-bg` disc; markers use tokens |
| G32 | D1 | minor | 003 | Bulk bar has no "Open in review" (it has an extra Deselect); Enter does nothing; Sort is static text | Bulk "Open in review"; Enter opens the selected sub in Review (Screens 04); Sort is a control |
| G33 | D2 | major | 003 | `QualityTab.tsx` table Grade column is an icon only | A three-segment Accept / Down-weight / Reject control in each row for one-click override, with M |
| G34 | D2 | minor | 003 | Sessions overview has no Guiding RMS row and no year chips | Five rows including Guiding RMS ("25 of 31 recorded") and chips All / 2026 / 2025 / 2024 / 2023 |
| G35 | D2 / 05 | major | 003 | Session chart has no cloud-pass band and no dashed median line | Shaded band for a detected cloud pass and a dashed session median (spec 003 US2 "cloud bands shaded") |
| G36 | D2 | minor | 003 | Inspector shows "MANUAL" but not what the auto grade was or who overrode it and when | "Auto grade was Down-weighted: FWHM 2.71″, 17% above the session median. You accepted it at 9 Oct 2026, 10:14." |
| G37 | A2 inspector | minor | 003 | `ReviewScreen.tsx` renders `<Inspector sub>` without `session`, so no "/ median" comparisons show | Every number is shown against the session's value |
| G38 | D3 | major | 003 | `sub/SubDetail.tsx` has a single preview | Modes Auto-stretch / Linear / Stars (detections overlaid) / FWHM map |
| G39 | D3 | minor | 003 | Breadcrumb reads "Dataset / 7 October 2026"; no "Show raw FITS header · N keywords" (raw headers exist only in `frames/FrameDetail.tsx`) | "Collection / Rig · Filter / 7 October 2026"; raw header one click away |
| G40 | D3 | minor | 001 / 009 | Sections depend on the backend; there is no Conditions section from SQMeter and no plate-solve section yet | Measured, Plate solve, Capture, Conditions, each with a source tag; SQMeter as a source |
| G41 | D4 | minor | 002 | `dataset/CalibrationTab.tsx` has no Bias column | Columns Session · Subs · Dark · Flat · Bias |
| G42 | D4 | major | 002 | No per-session "Change" | "Change" points a session at other frames; only that session re-calibrates and re-grades |
| G43 | D5 | minor | 004 | `MastersTab.tsx` Running card offers Cancel only while queued; no time left, no worker count | "started 10:02 · about 9 min left · 4 workers", "View in Activity" and Cancel while integrating |
| G44 | D5 | minor | 004 | Version tag is uppercase ("CURRENT"); meta lacks the method; superseded rows give no reason | Sentence case: "Current" (ok), "Superseded" (muted) with the reason ("replaced by v6 (2 new sessions)"); meta "winsorised σ 3.0 · grade weights" |
| G45 | D5 / 06 | minor | 004 | No master detail: rejection, weighting, registration reference with stars matched, SNR gain, output path, "Show in folder", calibration used, "Choose different frames" | Shown in Screens 06 |
| G46 | D5 / 04 | minor | 004 | Start button reads "Integrate master" | The primary action states the count: "Stack 15 subs" |

### Activity, review, calibration, settings

| # | Screen | Sev | Spec | Built (file) | Design |
|---|---|---|---|---|---|
| G47 | A1 | minor | 005 | `activity/Activity.tsx` running card: no Cancel, no ETA, one worker chip, log only on failures | Cancel, "≈ 9 min", every worker's chip ("W3 W4 W5 W6"), the last three log lines in mono |
| G48 | A1 | minor | 005 | Queue: "↑" bump only, no estimate per item | "drag to reorder" with a handle; estimate per item ("3 min"); "Show N more" |
| G49 | A1 | minor | 005 | Worker tiles: "Idle" or job name with a sparkline | State verb in colour ("Solving", "Normalising"), task, current file and CPU% (keep the sparkline for FR-002) |
| G50 | A1 | minor | 005 | Recent rows: "✓ name target" with duration and time | Outcome sentences ("Graded 24 subs · Askar 71F · Hα · 7 Oct · 19 accepted, 2 weighted, 3 rejected") with the duration |
| G51 | A2 / 07 | major | 003 | `review/ReviewScreen.tsx`: grouped tables plus the D2 inspector in two columns | Three-column console: queue (280 px), blink viewer with toolbar (Fit, Blink with best, Auto-stretch, Stars) and thumbnail strip, then the verdict panel (320 px) |
| G52 | A2 | major | 003 | No Space blink, no J/K stepping; overrides do not advance to the next flagged sub; U is the only extra key | Blink against the best of session; J/K; A, W and R override and advance; U reverts; I opens metadata |
| G53 | A2 | minor | 003 | Buttons read Accept / Weight / Reject; no run apply | "Keep rejected R" when the auto grade is Rejected; "Apply to subs 18 to 20 as well (Shift+key)" |
| G54 | A2 | minor | 003 | Only FWHM and stars are compared | Sub vs Session table (FWHM, Stars, Background, SQM, Guiding RMS, Altitude, Cloud) with warn and bad colouring and shape-independent text |
| G55 | A3 / 08 | major | 002 | `calibration/CalibrationLibrary.tsx` has two tables (raw sets by night, imported masters) and "Build missing masters". There is no blocking banner, no Rescan, no rig filter, no summary line, and no Used-by or State columns | Blocking items first with what is being looked for and "Use nearest flat"; one masters table (Type, Matches, Frames, Created, Used by, State) per rig; summary "21 masters across 3 rigs from … · last scan 3 min ago"; Rescan |
| G56 | A3 / 08 | minor | 002 | Title "Calibration library"; no type filter | Title "Calibration"; tabs All / Darks / Flats / Bias with counts |
| G57 | A4 / 09 | major | 008 | `settings/SettingsPage.tsx` has only Rigs, Path patterns and Ignored. Activity's "Worker settings" links to `#workers`, which does not exist | One page with a left rail: Folders, Rigs, Grading, Stacking, Plate solving, Metadata sources, Notifications, Workers, Users, Appearance |
| G58 | A4 | major | 008 / 003 | No save bar and no re-grade offer; grading thresholds are not editable | Sticky bar "Unsaved: … N datasets would be re-graded; manual overrides are kept." with Discard and "Save and re-grade" |

**Counts**: 58 gaps, of which **17 are major** (G1, G2, G14, G19, G22, G23, G24, G28, G33, G35, G38, G42, G51,
G52, G55, G57, G58) and **41 are minor**.

Things the build does that the design does not show (keep unless the owner objects):

- Reconciliation list and the "N to reconcile" link.
- Night view `/nights/$date`.
- Path patterns and ignore rules in Settings.
- "Accept every suggestion" on the Library.
- Merge-names panel on a collection.
- Master Re-run and Delete.
- Calibration set contact sheet (`/calibration/sets/$id`).
- NINA and provisional tags on tiles.

These come from specs 001, 002 and 004 and need homes in the v2 information architecture:

- Path patterns and ignore rules become Settings sections.
- Reconciliation is reached from the Library's notices.

---

## D. Requirements to add (paste-ready)

Existing FRs and amendments are not repeated. IDs are suggestions (`DR` = design requirement).

### Spec 001 — Ingest and catalogue

1. **001-DR-01**: Until the first light is catalogued, the Library MUST show the first-run state instead of
   readouts and lists. It MUST contain "No subs yet", every watched lights folder path in mono, the sentence "New
   FITS or XISF files will appear here within a few seconds of landing.", and the actions "Change watched folders"
   (opens Settings → Folders) and "Import an existing archive".
2. **001-DR-02**: The header MUST show "Watching N folders" in mono with an `--sst-ok` dot when every library is
   reachable. When any library is unreachable or scanning, the dot MUST change colour and shape, and the
   folder-by-folder status MUST be available on hover or focus.
3. **001-DR-03**: The reconciliation list MUST be reachable from "Needs reconciliation" badges and notices on
   Library, collection and dataset screens. It MUST NOT need a dedicated header link.
4. **001-DR-04**: Every metadata value shown on the sub detail screen MUST carry a source tag from the set
   SubStation, Solve, Header, Pattern, User or a linked device (for example SQMeter). A field with no value MUST
   show "Not recorded".
5. **001-DR-05**: The system MUST read sky quality (SQM keyword), weather (AMBTEMP, HUMIDITY, DEWPOINT, CLOUDCVR,
   WINDSPD), guiding RMS and capture software (SWCREATE) from headers when present, and MUST treat all of them as
   optional.
6. **001-DR-06**: The system SHOULD accept a linked SQMeter (by host name) as a source of SQM and cloud, matched to
   each sub by capture time, and MUST label such values "SQMeter".
7. **001-DR-07**: The system SHOULD read guiding RMS from a configured PHD2 log folder when the header has none.
8. **001-DR-08**: Each session header on the Subs tab MUST list the conditions recorded for that night (SQM,
   ambient temperature, humidity, guiding RMS, cloud periods with their source), omitting any that are not
   recorded.

### Spec 002 — Calibration library

1. **002-DR-01**: The Calibration screen MUST be titled "Calibration". Its summary MUST read "<N> masters across
   <R> rigs from <calibration folder> · last scan <relative time>". It MUST offer a Rescan action and a rig filter.
2. **002-DR-02**: Above everything else, the Calibration screen MUST list each dataset whose grading is blocked by
   missing calibration. Each entry MUST say what is waiting ("Heart Nebula · Askar 71F · OIII is waiting for a
   flat"), how many subs from which night cannot be graded, and exactly what SubStation is looking for (type,
   filter, exposure, gain, temperature, rotation when known). A "Use nearest flat" action MUST be offered only when
   the later-flat fallback applies.
3. **002-DR-03**: The Calibration screen MUST show one table of masters (built and imported) with columns Type,
   Matches, Frames, Created, Used by ("N datasets · M sessions") and State. State MUST be one of Current, "Kept for
   <year> data", "Weak match for N" (evidence-based only), Missing or "Unused · <age>".
4. **002-DR-04**: The masters table MUST be filterable by type with tabs All, Darks, Flats and Bias, each showing
   its count.
5. **002-DR-05**: Raw calibration sets (QA contact sheets) MUST remain reachable from the master they built and
   from the masters table.
6. **002-DR-06**: The dataset Calibration tab MUST show a Bias (or dark-flat) column alongside Dark and Flat for
   every session.
7. **002-DR-07**: Each session row on the dataset Calibration tab MUST offer "Change". It lets the user pick
   different dark, flat or bias frames for that session only, then re-calibrates and re-grades only that session,
   keeping human verdicts.
8. **002-DR-08**: Match notes MUST be plain English and give the age as information ("Same rotation · 2 days
   before", "Exact match", "44 days before"). They MUST be coloured warn only when a weak match is supported by
   evidence (spec 002, 2026-10-10 owner amendment).

### Spec 003 — Sub grading and review

**Dataset header**

1. **003-DR-01**: Every dataset tab MUST share a header with:
   - the breadcrumb "Library / <collection>";
   - the title "<Rig> · <Filter>[ · <framing>]";
   - the summary "<N> sessions · <N> subs × <exposure> s · gain <g> · <set temp> °C · <first night> to <last
     night>";
   - the actions Re-grade, Open review and, while a master integrates, "Integrating v<N> · <percent>%" linking to
     Masters.
2. **003-DR-02**: Re-grade MUST open a preview listing the subs whose machine verdict would change, with counts by
   change. Nothing MUST change until the user confirms, and human verdicts MUST be kept.
3. **003-DR-03**: "Open review" on a dataset MUST open Review filtered to that dataset's flagged subs.

**Subs tab (D1)**

4. **003-DR-04**: On the Subs tab each tile's verdict icon MUST sit on a `--sst-bg` disc. A manual override MUST
   show a small M. The selected tile MUST take the accent border and ring.
5. **003-DR-05**: Pressing Enter with one sub selected MUST open it in Review. The bulk bar MUST include "Open in
   review" for the selection.

**Quality tab (D2)**

6. **003-DR-06**: The Quality tab's metrics table MUST show the grade as a three-segment control (Accept,
   Down-weight, Reject) with the effective verdict highlighted. One click MUST apply an override.
7. **003-DR-07**: The sessions overview MUST include Guiding RMS, with gaps where not recorded and "N of M
   recorded". Year chips (All and each year present) MUST filter the sessions shown.
8. **003-DR-08**: The session chart MUST draw the session median as a dashed line and shade each detected cloud
   pass as a tinted band. Down-weighted subs MUST be triangles and rejected subs squares. Hovering a table row MUST
   highlight its point, and the reverse.
9. **003-DR-09**: When a sub has a human verdict, the inspector and sub detail MUST say what the auto grade was and
   who changed it and when ("Auto grade was Down-weighted: <reason> You accepted it at 9 Oct 2026, 10:14."). They
   MUST also offer "Revert to auto grade".

**Sub detail (D3)**

10. **003-DR-10**: The sub detail screen MUST offer preview modes Auto-stretch, Linear, Stars (detections
    overlaid) and FWHM map. Its breadcrumb MUST read "<Collection> / <Rig · Filter> / <night>", and the file name
    MUST be the title in mono.
11. **003-DR-11**: The sub detail screen MUST offer "Show raw FITS header · N keywords" in one click.

**Review console (A2)**

12. **003-DR-12**: Review MUST be a three-column console:
    - left: a queue of flagged subs grouped by dataset and session, with counts, "3 rejected, 2 weighted" summaries
      and the footnote "Flagged: rejected, down-weighted, or within 10% of a threshold.";
    - centre: a viewer with Fit, Blink with best, Auto-stretch and Stars toggles, the file name, capture time and
      altitude, and a thumbnail strip of the session;
    - right: the auto grade with its reason and evidence, a Sub vs Session table, and the override buttons.
13. **003-DR-13**: In Review:
    - J/← and K/→ MUST step through flagged subs;
    - Space MUST blink against the best sub of the session;
    - A, W and R MUST override and advance to the next flagged sub;
    - U MUST revert to the auto grade;
    - I MUST open the sub's metadata;
    - Z MUST zoom to 1:1;
    - Shift with A, W or R MUST apply to the current run of adjacent flagged subs ("Apply to subs 18 to 20 as
      well").
14. **003-DR-14**: The Sub vs Session table MUST compare FWHM, Stars, Background, SQM, Guiding RMS, Altitude and
    Cloud. Values outside the session's normal range MUST be marked with text or an icon as well as colour.
15. **003-DR-15**: When the current sub's auto grade is Rejected, the Reject override button MUST read "Keep
    rejected".
16. **003-DR-16**: Review MUST show an always-visible key legend using `<kbd>` chips.

**Shared**

17. **003-DR-17**: Every screen that shows a sub's numbers next to a median MUST use that sub's own session median.
18. **003-DR-18**: Override buttons MUST read "Accept A", "Weight W" and "Reject R". The bulk bar and key legends
    MUST read "Down-weight".

### Spec 004 — Stacking and masters

1. **004-DR-01**: The button that starts a master MUST state the number of subs it will use ("Stack 15 subs").
2. **004-DR-02**: An integrating master MUST show:
   - its pipeline steps with per-step progress;
   - the line "<N> subs from <M> sessions · started <hh:mm> · about <n> min left · <k> workers";
   - "View in Activity";
   - Cancel at every stage.
3. **004-DR-03**: Each master version MUST show:
   - a state tag in sentence case: Current (ok), Superseded (muted, with the reason, for example "replaced by v6
     (2 new sessions)") or Stale (with the reason);
   - its method summary ("winsorised σ 3.0 · grade weights");
   - Download and Inputs.
4. **004-DR-04**: A master's detail MUST show:
   - rejection and weighting;
   - the registration reference with stars matched;
   - inputs as full plus weighted counts;
   - SNR gain;
   - the output file path in mono;
   - the calibration frames used, with their match notes.
5. **004-DR-05**: A collection MUST offer "Stack combined masters", which builds one master per filter registered
   to the reference framing (depends on spec 009). The collection MUST state when a combined master is stale and
   why ("41 new subs since 2 October").
6. **004-DR-06**: Stacking defaults MUST be editable in Settings → Stacking:
   - rejection method and sigma;
   - weighting: Grade, SNR or Equal;
   - registration reference: Best FWHM, Most stars or Manual;
   - auto-stack: After each session, Every N new subs or Never;
   - output: XISF or FITS, 32-bit float.

### Spec 005 — Queue and workers console (Activity)

1. **005-DR-01**: Activity MUST be the only queue screen. The header's Activity badge and the Library's Processing
   readout MUST link to it, and the legacy `/queue` page MUST redirect to it.
2. **005-DR-02**: Each running job card MUST show:
   - every worker on the job as chips (W1…);
   - the estimated time left ("≈ 9 min");
   - Cancel;
   - a link to the dataset;
   - the last three log lines in mono with timestamps.
3. **005-DR-03**: Each worker row MUST show its state as a verb ("Solving", "Normalising", "Idle"), its job, the file
   in progress, CPU% and the 15-minute history.
4. **005-DR-04**: The queue MUST be reorderable by drag and by keyboard, and MUST show an estimate for each waiting
   item.
5. **005-DR-05**: Recent completions MUST read as outcome sentences ("Graded 24 subs · Askar 71F · Hα · 7 Oct · 19
   accepted, 2 weighted, 3 rejected") with their duration.
6. **005-DR-06**: The Activity readouts MUST be:
   - CPU (threads and workers);
   - Memory (used of total, with the integration buffer);
   - Disk (write rate on /data/substation);
   - Intake (Watching, folder count, last file time).
   Each readout MUST have a meter.

### Spec 006 — Library, collections and rigs

1. **006-DR-01**: The Library header MUST offer search ("Search objects, rigs, filters"), a rig filter chip and a
   "New collection" action.
2. **006-DR-02**: The Processing readout MUST name the main job in progress ("workers busy · Hα master
   integrating").
3. **006-DR-03**: Each ungrouped dataset MUST show "<sessions> · <subs> × <exposure> s · from <dates>".
4. **006-DR-04**: The collection screen MUST have tabs Overview, Datasets N, Sessions N and Masters N.
5. **006-DR-05**: The collection header MUST offer:
   - "Add datasets", which opens a dialog ranking candidates by centre offset, rotation and overlap with the
     reference framing, each with a plain-English note, multi-select and "Add N datasets";
   - Edit collection;
   - Stack combined masters.
   Candidates already in another collection MUST say so. Adding never moves files.
6. **006-DR-06**: The collection's dataset table MUST show:
   - state as a verdict badge ("Integrating v7", "Master stale", "Awaiting calibration", "Needs reconciliation"),
     or "Master current · <date>";
   - grades as a split bar with "<kept> of <total> kept";
   - last night as a short date.
7. **006-DR-07**: Selecting a date range on the sessions timeline MUST filter the dataset table below it.
8. **006-DR-08**: The integration matrix MUST mark the reference rig ("reference") and any framing label, and each
   dataset's meta MUST give exposure, gain and set temperature.
9. **006-DR-09**: Once plate solving exists (spec 009), collection cards and the Overview MUST draw each dataset's
   field over the master preview, with field size, image scale and overlap in a legend.

### New spec 007 — Brand, theme and app shell

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

### New spec 008 — Settings

1. **008-DR-01**: Settings MUST be one scrolling page with a left rail that jumps to its sections: Folders, Rigs,
   Grading, Stacking, Plate solving, Metadata sources, Path patterns, Ignored, Notifications, Workers, Users,
   Appearance.
2. **008-DR-02**: Folders MUST list each watched folder with its role (Lights, Lights archive, Calibration), status
   with a dot ("Watching · last file 3 min ago", "idle since 28 Sep") and Edit. It MUST show the output folder with
   free and total space and offer "Add folder".
3. **008-DR-03**: Grading MUST say "Each sub is compared with the median of its own session." It MUST show, per
   measure, the down-weight and reject levels with their direction (above or below) and a one-line explanation, and
   MUST include the switch "Use SQM and cloud when recorded" ("A sub is flagged, not rejected, on SQM or cloud
   alone").
4. **008-DR-04**: Changes MUST collect in one sticky save bar that states what changed ("FWHM reject threshold
   1.60× → 1.50×") and, for grading changes, how many datasets would be re-graded and that manual overrides are
   kept. It MUST offer Discard and "Save and re-grade" (or Save).
5. **008-DR-05**: Workers MUST set the worker count (shown as "N of M CPU threads") and the priority (New subs first
   or In order). Activity's "Worker settings" MUST link to this section.
6. **008-DR-06**: Notifications MUST offer channels (ntfy topic, webhook, email), event choices (Master finished,
   Job failed, Awaiting calibration, Session summary) and "Send test". The description MUST read "Sent when
   something needs you, not for routine work."
7. **008-DR-07**: Users MUST list accounts with role and last sign-in, offer "Add user", and support a read-only role
   ("can review, can't override").
8. **008-DR-08**: Appearance MUST offer Dark, Light and Night vision as a segmented control with the note "Press N
   anywhere for night vision".
9. **008-DR-09**: Rigs MUST show camera, focal length, image scale, mount type when known and session count, with
   Edit (rename, merge) and "Add rig".

### New spec 009 — Plate solving

1. **009-DR-01**: The system MUST plate-solve every light with a local solver (ASTAP, configurable path), using the
   header RA, DEC and OBJCTROT as a hint when switched on. On failure it MUST either fall back to the header
   position or leave the sub unsolved (setting), and MUST log the reason ("too few stars (cloud)").
2. **009-DR-02**: Solves MUST record centre, rotation, pixel scale, field size and offset from the dataset's
   reference framing, each shown on the sub detail with the solver and time ("ASTAP · 1.4 s").
3. **009-DR-03**: Collection suggestions and the "Add datasets" ranking MUST use the solved centre distance,
   rotation difference and field overlap, and MUST say so in the note.
4. **009-DR-04**: Back-filling solves for existing subs MUST run as a low-priority job visible in Activity.

**Requirement counts**: 001: 8 · 002: 8 · 003: 18 · 004: 6 · 005: 6 · 006: 9 · 007: 16 · 008: 9 · 009: 4 (84 in
total).
