# Feature Specification: One way to look at subs (Review, Dataset, Sub and Night together)

**Feature Branch**: `poc-substation`
**Created**: 2026-10-14
**Status**: Agreed 2026-10-14; viewer, Flagged filter and map built; night page and dataset labels to do
**Input**: Owner request, 2026-10-14: Review (`/review?dataset=10`), the dataset page (`/datasets/10`), the sub page
(`/subs/<sha>`) and the night page (`/nights/2026-09-25`) all solve a similar problem and together make a convoluted
experience; propose something better. Also asked for: a map on the sub page.

## What's there today (reviewed 2026-10-14 on dataset 10, IC 434 Hα, 25 Sep 2026)

| Page | What it is for | What it shows |
|---|---|---|
| Review | Go through flagged subs and override grades | Queue of datasets on the left; one big image, a filmstrip, the grade and its measures; keys J/K/A/W/R |
| Dataset → Subs | See every sub in a dataset | Grid grouped by night, verdict chips, bin, sort; "The night" link per night; "Open review" |
| Sub | Everything about one file | Big image with its own toolbar, the grade, calibration, measures, plate solve, capture, conditions, header; previous/next in the dataset |
| Night | What was shot on a night | A list of datasets with times and counts; no pictures, conditions, sky or place |

### Problems found

1. **Three viewers.** Review and Sub each have a large image, a grade, Accept/Weight/Reject and a 100% view, but
   with different toolbars (Review: Fit, Blink; Sub: Auto-stretch, Stars, FWHM map, Annotate) and different
   neighbours (Review: flagged subs; Sub: the whole dataset). The dataset grid is a third way in with its own
   actions (select, bin).
2. **The same keys mean opposite things.** Review: J next, K previous. Sub page: J previous, K next.
3. **One dataset, three names.** Review calls dataset 10 "IC 434 · Hα"; its own page "Askar 71F + ATR2600M · Hα"
   under "NGC 2024 - Flame Nebula"; the night page "IC 434".
4. **The night page is a dead end.** It lists datasets but shows no subs, conditions, Moon, altitude, place or
   anything to compare across targets that night, which is what a night is for.
5. **Small errors.** The dataset subtitle reads "26 September 2026 to 25 September 2026" (backwards); "no
   conditions recorded" sits above every night, and the sub page lists five "Not recorded" rows.
6. **Review is a separate place to go.** Flagged subs are already marked in the dataset grid, but reviewing them
   means leaving for another screen and losing the grid.

## Proposal

**One sub viewer, opened from wherever you are, stepping through whatever you were looking at.**

### 1. The viewer (replaces the Review screen's centre and the Sub page)

- One component: image with one toolbar (Fit/100%, Auto-stretch, Stars, FWHM map, Annotate, Aberration, Blink with
  best), filmstrip, grade with Accept/Weight/Reject, and a details drawer (measures, plate solve, capture,
  conditions, calibration, header, and a small map of where it was shot).
- It steps through **the list it was opened from**: a dataset grid (with its filters), one night of it, the flagged
  queue, a night's subs across datasets, or a search result. The list is named at the top ("IC 434 · Hα · flagged
  · 1 of 5"), and J/→ next, K/← previous everywhere.
- `/subs/<sha>` stays as the permanent link: it opens the viewer over the sub's dataset grid, stepping through that
  dataset. Opening from elsewhere adds the list to the address (`?in=night:2026-09-25` or `?in=flagged`), so a
  link or a refresh keeps your place.
- Rows hide when empty: no "Not recorded" rows; a section with nothing recorded says so once.

### 2. The dataset page is the hub

- Subs grid as today, grouped by night, with a **"Flagged · 5" chip that starts reviewing in place**: the viewer
  opens on the first flagged sub and steps through flagged subs only. The grid stays behind it.
- One name everywhere: collection title, then rig and filter ("IC 434 · Askar 71F + ATR2600M · Hα"); the same
  label on Review, nights, search and Activity.
- Dates in order ("25 to 26 September 2026").

### 3. Review becomes a queue, not a screen

- `/review` lists datasets with flagged subs (as the left column does today), largest first. Choosing one opens
  that dataset with the viewer reviewing its flagged subs. When the last one is done, it offers the next dataset.
- The header's Review count stays.

### 4. The night page becomes a night

- Header: date, place (name if known, coordinates otherwise) on a small map, Moon phase and altitude through the
  night, conditions recorded in the headers.
- One strip per dataset that night: a timeline bar (start to end) and its subs as thumbnails, verdict marks on each.
  Clicking a sub opens the viewer stepping through **that night's subs across datasets** in capture order, which is
  how you compare what changed (cloud at 02:10 hits every target).
- Previous/next night as now.

### 5. Map

- **Map** in the main menu: places where subs were shot, grouped like a phone's photo map (a count bubble and one
  picture, splitting as you zoom); choosing a place lists its nights, choosing a night opens the night page.
- The sub viewer's details show a small map with the site marked.
- Map tiles load from OpenStreetMap; SubStation isn't meant to work offline.
- **Built 2026-10-14.** `GET /map` groups lights by site (within about a kilometre of the busiest spot), with subs,
  nights (newest first), the most-shot collections and a picture: the longest master shot there, finished look when
  post-processed, else a sub. The Map page clusters places with Leaflet's marker clustering, each cluster showing
  its biggest place's picture and the total count; a place opens a panel with its name, coordinates, collections and
  nights, each linking to the night page. Place names come from OpenStreetMap's Nominatim, looked up only when a
  place is shown. The sub page has a "Where" section with a small map and the place name. Tiles are OpenStreetMap's
  standard tiles, darkened by CSS for the dark and night-vision themes (CARTO's dark tiles now need a key).

## Out of scope

- Changes to grading itself, stacking, or what is measured.
- New conditions sources (no SQMeter or PHD2: see the design-folder note in spec 007).

## Success criteria

- **SC-001**: Reviewing a dataset's flagged subs takes no page change: from the dataset grid, one click or key to
  start, J/K to move, A/W/R to decide.
- **SC-002**: The same keys do the same thing on every screen that shows a sub.
- **SC-003**: Every place a dataset is named uses the same label.
- **SC-004**: From a night, every sub shot that night can be stepped through in capture order without going back.

## Decisions (owner, 2026-10-14)

1. Review is a filter on each dataset, not a screen: the "Flagged" chip on the Subs tab, and "Review N flagged" in the
   dataset header. Review leaves the main menu; `/review` opens the dataset with the most flagged subs, filtered,
   with the viewer on the first (the home page's "Needs you" link uses it).
2. Viewers open as modals over the page they came from; they don't need pages of their own. `/subs/<sha>` opens
   the sub's dataset with the viewer on it.
3. Dataset labels keep the rig even when a target has only one, for consistency.

## Built 2026-10-14

- The sub viewer is a modal over the dataset's Subs tab (`?sub=<sha>`), stepping through what the grid shows (all,
  flagged, a verdict, by hand), named at the top ("Flagged subs", 2 / 5). J or → next, K or ← previous, A/W/R/U
  decide, Z 100% view, X aberration inspector, Esc closes. In the flagged list a decision moves on to the next
  flagged sub, as Review did. A tile opens with a double-click, its name, or Enter on a single selection.
- The dataset subtitle gives nights in order (a sub after midnight belongs to the night before).
- Still to do: Blink with best (Space) in the viewer; the night page (section 4); one dataset label everywhere
  (section 2); hiding "Not recorded" rows.

### Amendment 2026-10-14: map links and the night page

- **012-DR-01 Map links carry their context.** In a place's panel, every collection shot there is a link to that
  collection's sessions, filtered to the nights shot at that place and naming the place, with a way back to every
  session. Every night is a link to that night's page at that place. The map's data gives each collection its id and
  each night its site.
- **012-DR-02 The night page is a night.** It uses the same layout as the other screens (header, readouts, cards):
  where it was shot (name and small map), the Moon's phase and whether it was above the horizon while the lights
  were taken, a timeline with a bar per dataset, and per dataset a strip of its subs that night. A sub opens the
  viewer modal, which steps through every sub of the night in time order. When subs were shot in more than one place
  that night, the page offers each place. The Moon is worked out locally, with no network access; a night with no
  recorded place shows the phase only.


### Amendment 2026-10-15: keys, zoom and buttons

- **012-DR-03 J goes back, K goes on.** J sits left of K on the keyboard, so J (and ←) is the previous sub and K (and
  →) the next, in the viewer and the key help.
- **012-DR-04 The full-size view zooms like any image viewer.** The wheel or a trackpad pinch zooms about the
  pointer; drag pans; a double click switches between fitting the window and 100%; − and + buttons, the zoom as a
  percentage, Fit and 100% sit together in the bar, with keys + − 0 1. The fixed Fit / 100% / 200% steps are gone.
- **012-DR-05 Clickable pills are buttons.** A button or link drawn as a pill has the main buttons' height, radius,
  type, a filled face and hover, pressed and focus states; toggles in a group stay rounded chips; static tags stay
  small capsules.
