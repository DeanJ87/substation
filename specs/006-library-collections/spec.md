# Feature Specification: Library, collections and rigs

**Feature Branch**: `006-library-collections`

**Created**: 2026-10-10

**Status**: Draft

**Input**: Claude Design "SubStation v2 · 1 of 3 · Library and collections" (docs/design/v2), owner
direction 2026-10-10: "adjust the spec to match the UI; spec defines first".

## Data model (from the design)

- **Rig**: one telescope and camera (and focal length), detected from TELESCOP, INSTRUME and FOCALLEN,
  renamable and mergeable by the user. Display name such as "Askar 71F".
- **Dataset**: one rig, one filter and one framing, spanning any number of nights (sessions). Displayed as
  "Rig · Filter" with a framing label when a collection holds more than one framing of that rig and filter
  ("Askar 71F · Hα · Panel 3", "SQA130 · Hα · Cygnus Wall"). Spec 001's grouping key (target, panel, filter,
  camera, telescope, binning, gain, offset) stays the identity; the panel is the framing until plate
  solving supplies one.
- **Session**: one dataset's subs on one observing night (spec 001's dataset night).
- **Collection**: one object across rigs, filters, framings and years ("North America and Pelican: NGC 7000 ·
  IC 5070"). Catalogue-only: nothing moves on disk. Datasets are *suggested* for a collection; the user
  confirms.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The Library is home (Priority: P1)

The Library shows readouts (last night's subs and rigs, accepted integration, processing with a link to
Activity, free disk), then collections as cards (master preview, name, objects and constellation,
dataset count, rigs, accepted integration per filter so gaps are visible, date range and sessions, total
integration and state badges), then datasets not yet in a collection, each with SubStation's suggestion
("Suggested: Heart Nebula. Centre 6′ away, 88% overlap." or "No existing collection within 2°") and
Choose…, Add to …, New collection. Search by object, rig or filter; filter by rig.

**Independent Test**: With the phase 2 tree, the Library shows two collections (North America and Pelican
with NGC 7000 panels; Heart Nebula) built from suggestions the user accepted, with integration per filter
matching the datasets.

**Acceptance Scenarios**:

1. **Given** datasets of a target with no collection, **When** the Library opens, **Then** they are listed
   under "Not in a collection" with a suggestion, and one click adds them.
2. **Given** a collection, **When** shown, **Then** its card gives integration per filter and the states
   that need attention (Integrating, Master stale, Awaiting calibration, Needs reconciliation).

### User Story 2 - A collection shows one object across rigs and years (Priority: P2)

The collection screen shows framing (each dataset's field over the reference framing, when plate solved),
accepted integration by rig and filter, combined masters, a sessions timeline per rig, and the dataset table
(state, sessions, accepted, grades kept, last night). Datasets can be added (ranked by centre distance and
overlap; low overlap allowed as a separate panel) and removed.

### User Story 3 - Rigs are detected and can be renamed (Priority: P2)

Rigs appear in Settings with camera, focal length, image scale and session count; the user can rename or
merge them, and names are used everywhere datasets are shown.

### Edge Cases

- Without plate solving, suggestions use the OBJECT name (target) and header RA/Dec when present; the
  suggestion says which was used.
- A dataset may belong to one collection at a time.
- Deleting a collection never deletes datasets or files.

## Requirements *(mandatory)*

- **FR-001**: System MUST detect rigs from TELESCOP, INSTRUME and FOCALLEN and let users rename and merge
  them.
- **FR-002**: System MUST let users create, rename and delete collections and add or remove datasets.
- **FR-003**: System MUST suggest a collection for each ungrouped dataset (by plate-solved centre and overlap
  when available, else by target name and header coordinates) and state the evidence.
- **FR-004**: The Library MUST show the readouts, collection cards and ungrouped datasets described above.
- **FR-005**: The collection screen MUST show accepted integration by rig and filter, the sessions timeline,
  and the dataset table.

## Success Criteria *(mandatory)*

- **SC-001**: Every dataset is either in a collection or listed with a suggestion.
- **SC-002**: Integration per filter on a collection card equals the sum over its datasets.

## Assumptions

- Plate solving (ASTAP) is a later spec; framing overlap and the framing panel need it.
- Combined masters across rigs (resampling to the reference) are a later increment of spec 004.

## Amendment 2026-10-10: design review

From the full design review (`docs/design/design-review.md`, sections B–D): every SubStation design file and the brand guidelines were checked against the build. These requirements add to the ones above; where the design files disagree, the decisions in spec 007 apply.

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

## Amendment 2026-10-10 (owner): projects, framing views, sortable tables

- **006-DR-20 Projects.** A collection is the object (NGC 7000). Inside it, a **project** is one way of shooting it:
  "6-panel mosaic 2026" (4 panels so far), "Single panel 2025" at another framing. A project has a name, a kind
  (single field or mosaic), planned panels (for a mosaic: 6, with the ones not shot yet shown as missing), an
  order, and its datasets. Datasets are suggested into a project by panel and framing (plate solves): a dataset
  whose field overlaps a project's fields by 50% or more, or that names a panel of it. Overview, framing,
  integration and combined masters work per project; the collection page lists its projects first.
- **006-DR-21 Framing selection.** The framing table selects rows like a file list: click one, Shift-click a
  range, Cmd/Ctrl-click to add or remove, drag down the rows to sweep, All and None. The drawing shows the
  selected datasets' images; outlines can be turned off.
- **006-DR-22 Framing by filter and palette.** Filter chips (All, Hα, OIII, SII, L, R, G, B, OSC) show only that
  filter's fields and images. Palette views combine filters per panel on the sky: **HOO** (Hα red, OIII green and
  blue) and **SHO** (SII red, Hα green, OIII blue), offered only when the filters exist. They are previews made
  from single subs, labelled so.
- **006-DR-23 Sortable tables.** Every data table sorts by clicking its column heading (again to reverse), with
  the sort shown on the heading and kept in the URL where the page has one.
- **006-DR-24 Drag to reorder.** Projects in a collection, and datasets in a project, can be dragged into order
  (and moved with Alt+↑/↓); the order is kept.

## Amendment 2026-10-11 (owner): images open, loading shows

- **006-DR-25 Any image opens.** Clicking a sub, master, combined master or calibration image anywhere opens it at
  100% with the aberration inspector; no separate button needed.
- **006-DR-26 Loading is visible.** Pages show skeletons until their data arrives; Library totals dim with a
  spinner while new filters load, and search asks once typing settles.
- **006-DR-27 Plain words.** Interface copy is short and factual: labels, numbers and the next step, no
  explanations of what is on screen.

## Amendment 2026-10-13: collection titles, rigs that follow the camera

- **006-DR-28**: A collection named "<designation> - <common name>" (the library's naming convention, e.g. "NGC 7635 -
  Bubble Nebula") is titled by its common name with the designation as a small tag beside it. The line under it
  gives the constellation, the dataset count, and only those object names the title doesn't already carry ("also
  NGC 6992"), so nothing is said twice. The Moon and planets get no constellation.
- **006-DR-29**: A dataset whose rig has a different camera (left by a rig merge that was later corrected) is put
  back on its own camera's rig the next time its rig is looked up. A light whose focal length differs from an
  existing rig's only by rounding (within 2%, same camera and telescope) joins that rig rather than starting a new
  one.
- **006-DR-30** (2026-10-13): A collection card's filter bars count everything captured, calibrated or not. Each
  bar is split into usable (graded and kept), waiting (for calibration or grading) and rejected, with the totals on
  hover; the right-hand figure is the time captured, and the card's foot reads "usable of captured". Datasets keep
  their rejected exposure alongside the accepted (`rejected_integration_s`).
- **006-DR-31** (2026-10-13): Library readouts never add past 100%: "Rejected" is shown as 100% minus the rounded
  "Kept", as the two together are every graded sub.
