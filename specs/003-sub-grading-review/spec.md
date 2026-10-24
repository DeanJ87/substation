# Feature Specification: Sub grading and review

**Feature Branch**: `003-sub-grading-review`

**Created**: 2026-10-09

**Status**: Draft

**Input**: Scope: calibrate and grade each sub as it arrives (FWHM, star count, roundness, background, noise),
grade it against its own night's median as Accepted, Down-weighted or Rejected with a plain-English reason, and
let the user review the night (night chart, metrics table, blink review with keyboard overrides), in dark, light
and night-vision modes. Sources: phase 1 step 4c
and 4d, phase 2 step 4, design screens 9a, 9b, 9c, components, verdict system and voice.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Each sub is graded within moments of landing (Priority: P1)

During a live session, each calibrated sub is measured and graded. The dashboard shows "Accepted
tonight 65 of 78", and each sub's verdict, measurements and reason.

**Why this priority**: per-sub feedback during the night is the product's core promise.

**Independent Test**: Replay the phase 2 NGC 7000 Panel 3 Hα night at capture pace; every sub has a
grade and reason within the time limit, and verdicts match the spike's grader for the same rules.

**Acceptance Scenarios**:

1. **Given** a sub with a calibration match, **When** it lands, **Then** within 60 seconds it is
   calibrated, measured (FWHM in arcseconds and pixels, star count, roundness, background, noise) and
   graded.
2. **Given** a sub whose star count is 41% of the night median, **When** graded, **Then** it is
   Rejected with the reason "Star count 41% of the night median: likely cloud."
3. **Given** a sub 30% softer than the night median, **When** graded, **Then** it is Down-weighted with
   its weight shown and the reason "FWHM 2.85″, 30% above the median: likely seeing."
4. **Given** a sub that fails star matching against the dataset, **When** graded, **Then** it is
   Rejected with the reason "Could not match stars to the rest of the night: likely cloud or
   tracking."
5. **Given** the first subs of a night (too few for a median), **When** graded, **Then** they show a
   provisional grade that is confirmed once enough subs exist, and the user can see that it is
   provisional.

---

### User Story 2 - The user reviews the night and overrides grades (Priority: P1)

The user opens a dataset and sees the night chart (FWHM, star count and background across the night,
with rejected and down-weighted subs marked and cloud bands shaded), the metrics table, and a blink
review that steps through subs with J and K, blinks with Space and overrides with A (Accept),
W (Keep, down-weighted) and R (Reject).

**Why this priority**: "Every decision explained" requires the user to see and change decisions.

**Independent Test**: Open the Heart Panel 2 dataset; the chart shows the focus drift and cloud gap; the
user overrides sub 6 to Accept with the keyboard and the dataset's counts update.

**Acceptance Scenarios**:

1. **Given** a dataset, **When** opened, **Then** the night chart, the metrics table (verdict, time,
   file, FWHM, stars, background, weight, reason) and the user and NINA verdicts are shown.
2. **Given** blink review, **When** the user presses K, **Then** the next sub is shown already
   auto-stretched, with no visible pause on a NAS (the next 20 subs are prepared in advance).
3. **Given** a machine Rejected sub, **When** the user presses A, **Then** the sub becomes Accepted by
   user override, the machine grade is kept alongside, and the dataset's masters become Stale.
4. **Given** a NINA thumbs-down sub, **When** reviewed, **Then** it shows as Rejected by the user (NINA)
   and the machine grade is shown alongside for comparison.

---

### User Story 3 - The dashboard summarises everything at a glance (Priority: P2)

The Datasets dashboard shows tonight's accepted count, total accepted integration, the processing
queue, free disk space, and each dataset's target, filters, integration, accepted, down-weighted and
rejected counts, state and a one-line note.

**Why this priority**: the at-a-glance view, but the per-dataset views carry the detail.

**Independent Test**: With the phase 2 data loaded the dashboard counts match the catalogue and grades.

**Acceptance Scenarios**:

1. **Given** datasets in different states, **When** the dashboard opens, **Then** each shows its state
   with the shape, glyph and colour from the verdict system, and a note such as "12 subs waiting for
   darks at −10 °C, gain 100."

---

### User Story 4 - It works at the telescope in the dark (Priority: P2)

The user can switch to night-vision mode (red on black) with N anywhere; verdicts remain
distinguishable by shape alone.

**Why this priority**: the user is often at the telescope at night.

**Independent Test**: Every screen passes WCAG AA in dark, light and night-vision modes, and all seven
states are distinguishable in a single-colour rendering.

**Acceptance Scenarios**:

1. **Given** any screen, **When** the user presses N, **Then** the interface switches to night vision
   and back, and the choice is remembered.

---

### User Story 5 - Grades can be recomputed on request (Priority: P3)

The user changes grading thresholds (or a new version improves grading) and chooses Re-grade for a
dataset; changes are previewed before being applied, and user overrides are never changed.

**Why this priority**: needed for tuning, not for the first night.

**Independent Test**: Lower the wFWHM threshold; the preview lists which subs would change; applying it
changes only machine grades.

**Acceptance Scenarios**:

1. **Given** new thresholds, **When** the user chooses Re-grade, **Then** a preview of changed verdicts
   is shown, and nothing changes until confirmed.

### Edge Cases

- A sub with zero stars (cloud or closed shutter) is Rejected, never divides by zero.
- Twilight subs at the start or end of a night have high background; they are graded like any other.
- Pier flips rotate subs by 180°; this does not affect grading.
- Focus drift between autofocus runs: the chart shows focuser position and temperature alongside FWHM,
  so the cause is visible.
- Grading is against the sub's own night median, even in multi-night datasets.
- Very short nights (fewer than 5 subs) use provisional grades.
- Subs awaiting calibration are shown with the dashed-circle state and are not graded yet.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST calibrate each matched sub individually as it arrives, using the matched
  calibration from spec 002, and keep the result for registration and stacking.
- **FR-002**: System MUST measure each calibrated sub: FWHM (pixels and arcseconds, using image scale
  from headers), weighted FWHM, star count, roundness, background, noise, and the field position of
  stars for later regional analysis.
- **FR-003**: System MUST grade each sub against its own night's median for its dataset as Accepted,
  Down-weighted (with a weight) or Rejected, using configurable relative thresholds (defaults from the
  spikes: wFWHM 1.5× median, stars 0.6× median, background 2× median, roundness below 0.85).
- **FR-004**: Every grade MUST include a reason in the voice guide's form: the measurement, the
  comparison with the night median, the likely cause.
- **FR-005**: System MUST keep machine grades, NINA verdicts and in-app overrides as separate records;
  the effective verdict is the latest human decision if any, otherwise the machine grade.
- **FR-006**: System MUST provide the night chart, metrics table and blink review described in the
  design, with keyboard controls J, K, Space, A, W, R and N.
- **FR-007**: Blink review MUST show auto-stretched previews using one stretch per dataset so subs are
  visually comparable, and MUST prepare upcoming previews in advance.
- **FR-008**: System MUST show focuser position and temperature with the metrics, so focus drift is
  visible.
- **FR-009**: System MUST support dark, light and night-vision modes meeting WCAG AA, with verdict
  states distinguishable by shape and glyph.
- **FR-010**: System MUST mark a dataset's masters Stale when a grade or override changes which subs
  they would include.
- **FR-011**: Re-grading MUST be an explicit user action with a preview and MUST NOT change human
  verdicts.
- **FR-012**: System MUST require sign-in with individual user accounts (admin-created; admin and
  standard roles), with revocable sessions; two-factor authentication (TOTP first) MUST be supported
  as a later increment and be configurable as off, optional per user, or required.
- **FR-013**: System MUST show results per night as well as per dataset: for any night, its subs,
  grades, night chart and summary (accepted count, integration, medians), and for a dataset, a list of
  its nights to compare.
- **FR-014**: Every human verdict MUST record which user made it and when.

### Key Entities

- **Sub measurement**: per sub: FWHM, wFWHM, stars, roundness, background, noise, star positions,
  calibration used, engine version, timestamp.
- **Machine grade**: verdict, weight, reason, thresholds version, provisional flag.
- **User override**: verdict, user, time, optional note.
- **Night summary**: per dataset per night: medians and counts.
- **Preview**: auto-stretched image of a sub at screen and 100% crop, with the stretch used.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% of subs with a calibration match are graded within 60 seconds of landing on the
  reference NAS.
- **SC-002**: On the four phase 2 datasets, machine grades agree with the spike grader on 100% of subs
  for the same thresholds, and agree with NINA thumbs-down where both apply.
- **SC-003**: Stepping through blink review shows each next sub in under 200 ms after the first 20
  are prepared.
- **SC-004**: A user can change a verdict in one keystroke and see the dataset counts update
  immediately.
- **SC-005**: In usability checks, users can state why any sub was rejected without opening another
  screen.

## Assumptions

- Grading weights for Down-weighted subs come from the same measurements (for example relative wFWHM);
  exact formula is a planning decision.
- Measurements are Siril's (findstar and registration statistics), per constitution principle IV.
- Several user accounts may exist (for example a household or club); grades and overrides are shared,
  not per user.
- The interface is a web app viewed on a laptop or tablet on the home network; phone layouts are
  read-only friendly but not optimised for review.

## Amendment 2026-10-10: v2 design (docs/design/v2, D1–D3 and A2)

The dataset screen has tabs **Subs · Quality · Calibration · Masters**, with Re-grade, Open review and the
current integration's progress in its header.

- **Subs (D1)**: subs as tiles grouped by session, newest first; each session header shows its conditions
  where recorded (SQM, temperature, humidity, guiding, cloud). Tiles show the verdict glyph, file number,
  FWHM and stars, and **M** for a manual override. Filter chips: Sessions, Accepted, Down-weighted,
  Rejected, Manual. Click selects, shift-click selects a range, Ctrl/Cmd-A selects a session; the bulk bar
  (Accept A, Down-weight W, Reject R, Clear override, Open in review) applies to the selection.
- **Quality (D2)**: a sessions overview (per session, the 10th–90th percentile bar and median of FWHM, stars,
  background, SQM and guiding RMS, with gaps where not recorded); the selected session's chart (FWHM and SQM
  over the night, weighted and rejected subs marked, cloud shaded) and table (grade, time, FWHM, stars,
  background, SQM, altitude, reason); an inspector with the sub's preview, verdict, override buttons, Revert
  to auto grade and its numbers against the session's.
- **Sub detail (D3)**: preview (auto-stretch, linear, stars, FWHM map), the verdict with reason and evidence,
  and sections Measured (SubStation), Plate solve, Capture (header) and Conditions, every field tagged with
  its source and **Not recorded** when absent; raw header one click away; J and K for previous and next.
- **Review (A2)**: flagged subs from every dataset (rejected, down-weighted, or within 10% of a threshold),
  grouped by session; a viewer with blink against the session's best sub; sub vs session numbers; A, W, R
  override and advance, U reverts to the auto grade, Shift applies to a run of flagged subs.
- **Overrides** are labelled **Manual**, logged with user and time, and survive a re-grade.
- **Grading thresholds** (Settings A4) have a down-weight and a reject level per measure, relative to the
  session median: FWHM 1.20× / 1.50×, star count 0.70× / 0.50×, background 1.20× / 1.40×; eccentricity is
  absolute, 0.50 / 0.65. SQM and cloud, when recorded, flag a sub but never reject it alone (setting).
  The spike grader's rules remain available as a profile for validation (SC-002).

## Amendment 2026-10-10: design review

From the full design review (`docs/design/design-review.md`, sections B–D): every SubStation design file and the brand guidelines were checked against the build. These requirements add to the ones above; where the design files disagree, the decisions in spec 007 apply.

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

## Amendment 2026-10-10: eccentricity against the session

Grading compares each sub with its own session (and, within a session, its own exposure). Eccentricity keeps its
absolute down-weight and reject levels, but they never sit below the session's median eccentricity plus 0.08 and
0.15: a lens or tilt that elongates every star is a property of the rig, not of a sub, while tracking errors and wind
still stand out from their session. Subs of different exposures in one session are graded separately (a DSLR night
mixing 5 s and 300 s subs).

## Amendment 2026-10-13: exposure and capture time are obvious

Exposure time was hard to find in the UI, and a sub's capture date wasn't shown at all.

- **003-DR-30**: The dataset header MUST show its exposures with counts ("50 × 60 s, 17 × 240 s"); each sub tile
  shows its exposure; the sub page shows "Taken 13 Apr 2026, 22:14 UTC · 60 s exposure" under its name.

## Amendment 2026-10-13: the 100% view draws itself

- **003-DR-31**: Opening the 100% view of a sub, master or combined image that hasn't been drawn starts drawing it
  at once and shows that it is loading; there is no Generate button. If drawing fails, the viewer says why (the
  task's own reason) and offers Try again. A 16-bit FITS stored with BZERO/BSCALE (the Sony A7 III's) is read in
  full rather than memory-mapped, which it can't be.

## Amendment 2026-10-24: one preview look for the installation

Sub previews were drawn with one stretch per session only for subs measured after that rule (G18), and every
glance or 100% view drawn later used the frame's own stretch, so black points still differed between frames being
compared while grading.

- **003-DR-32**: Settings → Processing → **Sub previews** sets how sub previews are stretched, for the whole
  installation:
  - **Stretch**: *Shared per session* (default) draws every sub of one night and dataset with one stretch, the
    median of its subs' own stretch parameters, so a cloudy or hazy sub looks darker beside its neighbours;
    *Per sub* draws each with its own. Subs drawn from calibrated files and subs drawn from captures (no dark or
    flat applied) are kept as separate groups within a session, since their levels differ.
  - **Black point**: a signed offset from −2 to +2 in units of the sky's noise (sigma), default 0, applied to the
    shadow clip (normally 2.8 sigma below the sky). The midtone balance stays where the default clip puts it, so
    a higher black point draws a darker, cleaner sky and a lower one a lighter, noisier one.
  - **Sky brightness**: the grey level the sky is drawn at with the default clip, 10–40%, default 25%.
- **003-DR-33**: The look applies to everything that shows a sub: tiles, the night page strips, the dataset Subs
  and Quality tabs, Review and the sub viewer all use the stored previews; a glance of a measured sub is its
  preview; the 100% view and aberration inspector of a sub use its session's shared stretch in shared mode, and
  the look otherwise. A glance of a frame that hasn't been measured has no session stretch yet and is drawn on its
  own with the look.
- **003-DR-34**: Changing the look queues one background job that queues a redraw per session (the existing
  session redraw), bounded by the queue's workers; nothing is redrawn inside the request. Each redraw also drops
  the session's 100% views, which are drawn again on request to match. Previews are sent with a five-minute cache
  and an ETag, so browsers pick up redrawn previews without keeping stale ones for a day.
- **003-DR-35**: Masters, combined masters and post-processed stages keep their own stretch and ignore the look:
  their stages are compared against the master's own stretch (spec 010), and moving their black point with a
  setting meant for grading subs would change every stage preview without redrawing them.
