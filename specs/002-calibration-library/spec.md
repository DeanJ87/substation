# Feature Specification: Calibration library

**Feature Branch**: `002-calibration-library`

**Created**: 2026-10-09

**Status**: Draft

**Input**: Scope: a calibration library that imports existing masters (including PixInsight
WBPP), checks raw flats, darks, dark flats and bias frames for problems before use (truncated readouts,
level outliers, stars or light leaks, gradients), builds masters from raw frames, and matches each light
to a dark and flat by documented rules, leaving validity decisions to the user. Sources: phase 1 steps
3 and 4, phase 2 steps 2 and 3, design "Calibration" tab and "Awaiting calibration" state.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lights are matched to calibration automatically (Priority: P1)

As lights arrive, each is matched to a master dark (same exposure, temperature within tolerance, same
gain, offset and binning) and a master flat (same filter, latest flat on or before the night).
Unmatched lights show "Awaiting calibration" with the reason, and are processed as soon as a match
appears.

**Why this priority**: calibration is required before grading and stacking; matching is the core.

**Independent Test**: On the phase 2 tree every light matches the expected dark and flat named in
SPIKE2_REPORT (for example Hα lights to the 09-28 Hα master flat and the −20 °C 600 s master dark).

**Acceptance Scenarios**:

1. **Given** a light at −19.9 °C and a −20 °C 600 s dark, **When** matched, **Then** the dark is chosen
   (tolerance ±2 °C by default), and the match and the rule used are shown on the light.
2. **Given** a light whose filter has no flat on or before its night, **When** matched, **Then** it
   shows "Awaiting calibration: no Hα flat on or before 28 Sep", and a "nearest later flat" suggestion
   is offered only if that fallback is switched on.
3. **Given** a match depends on a master with unconfirmed metadata, **When** the light is matched,
   **Then** it uses the user's confirmed values from reconciliation, or waits if they are unconfirmed.
4. **Given** a new master that would change existing matches, **When** it is added, **Then** affected
   datasets are listed and nothing is re-calibrated until the user accepts.

---

### User Story 2 - Bad calibration frames are caught before use (Priority: P1)

Every raw dark, dark flat, flat and bias is checked against its own set before a master is built. The
user sees a contact sheet per set with flagged frames outlined and a plain-English reason for each.

**Why this priority**: a single bad frame (for example a truncated readout or a dark with stars from an
open panel) silently spoils every light calibrated with it.

**Independent Test**: On the phase 2 tree exactly one frame is rejected (the truncated 2 s dark flat),
and a test frame with injected faint stars at 15 ADU peak is flagged as contaminated.

**Acceptance Scenarios**:

1. **Given** a dark whose lower 62% of rows are zero, **When** checked, **Then** it is rejected as a
   truncated readout.
2. **Given** a dark that recorded stars, **When** checked, **Then** it is rejected with the number of
   star-like sources and their typical size, and a close-up of the evidence.
3. **Given** a dark set with consistent hot pixels and amp glow, **When** checked, **Then** no frame is
   flagged for those.
4. **Given** a flat, **When** checked, **Then** its exposure level as a fraction of full scale is shown
   and flagged if too low or near saturation, and its consistency with the set is shown.
5. **Given** a flat set with no matching dark-flat exposure, **When** checked, **Then** the set is
   flagged and cannot become a master until a dark flat or bias is provided or the user chooses to
   proceed.

---

### User Story 3 - Masters are built from raw frames (Priority: P2)

When a set of raw calibration frames is complete, SubStation builds a master from the frames that
passed QA, shows its statistics and histogram, and adds it to the library. For flats it also shows the
falloff and dust motes.

**Why this priority**: the owner has raw flats that were never stacked; the spike showed old masters
can be wrong for the current optical train.

**Independent Test**: Building the phase 2 Hα master flat reproduces the spike's falloff (about 5%
mean) and dust-mote count within tolerance.

**Acceptance Scenarios**:

1. **Given** a QA-passed dark-flat set, **When** built, **Then** a master dark flat is produced using
   the method in the calibration rules, and the excluded frames are listed.
2. **Given** a flat set and its matching master dark flat, **When** built, **Then** a master flat is
   produced, and its centre-to-corner falloff per corner and dust motes are shown.
3. **Given** a new master flat and an older master for the same filter, **When** both exist, **Then**
   a ratio image and summary ("differs by up to 5% in the top-left corner") let the user judge whether
   the old one still applies.
4. **Given** a rebuilt master (for example after a frame was excluded), **When** it differs from the
   previous version, **Then** a difference summary shows what the excluded frames had changed.

---

### User Story 4 - The user manages the library (Priority: P3)

The user can view all masters, see provenance (built here or imported, from which frames, with which
method), confirm or correct metadata, retire a master or set a validity window, and see which datasets
use each master.

**Why this priority**: important for trust and control, but matching works with defaults.

**Independent Test**: Retire the 08-15 WBPP flats; affected datasets show "Stale" for their masters
and re-match on request.

**Acceptance Scenarios**:

1. **Given** a master, **When** opened, **Then** its provenance, metadata (with source of each value)
   and usage are shown.
2. **Given** a master the user retires, **When** retired, **Then** it is no longer matched and
   datasets using it are marked for the user's attention.

### Edge Cases

- WBPP masters store integration plus rejection maps; only the integration image is used and its
  position in the file is verified.
- Masters with no temperature, gain or offset headers rely on user-confirmed values (spec 001
  reconciliation).
- Flats taken after midnight belong to the observing night that started the evening before.
- Filters whose names differ by case match.
- Dark flats are filter-independent: a Green flat set can use dark flats labelled "Red" at the same
  exposure.
- Calibration frames from a different site or rig are not invalidated automatically; the user decides.
- A camera at a new set temperature with no darks: lights wait in "Awaiting calibration".

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST import existing masters (FITS and XISF, including WBPP multi-image XISF)
  without modifying them, using only the integration image.
- **FR-002**: System MUST run QA on every raw calibration frame against the robust median of its set:
  median, mean, MAD, minimum and maximum, saturated fraction, truncated or corrupt readout, level
  outlier, large-scale structure, and star or leak contamination.
- **FR-003**: Star and leak detection MUST be sensitive enough to flag stars of 15 ADU peak in a dark,
  and MUST include a self-test with synthetic stars that runs as part of QA verification.
- **FR-004**: System MUST present QA results per set as a contact sheet with flagged frames outlined,
  plus a verdict and reason per frame, and let the user override any QA verdict.
- **FR-005**: System MUST build master darks, dark flats, bias frames and flats from QA-passed frames
  by documented methods (no normalisation for darks and bias, multiplicative normalisation for flats,
  flats calibrated by the matching master dark flat or bias).
- **FR-006**: System MUST report for each master flat the falloff per corner, a radial profile and
  detected dust motes (position, size, depth).
- **FR-007**: System MUST compare a new master with an existing one for the same type and filter, and
  show a ratio or difference image and summary.
- **FR-008**: System MUST match each light to a dark (exact exposure, temperature within a configurable
  tolerance, default ±2 °C, same gain, offset and binning) and a flat (same filter, camera and
  binning, and the same telescope or lens when both record one, since a flat belongs to its optical train;
  latest flat on or before the light's night).
- **FR-008a**: Matching MUST use resolved metadata (spec 001: header, path pattern or user value) and
  show each value's source on the match, so a match that relied on a pattern or a user value is visible.
- **FR-009**: System MUST mark unmatched lights "Awaiting calibration" with the missing item named, and
  process them automatically once a match exists.
- **FR-010**: Fallback rules (nearest later flat, bias instead of dark flat, wider temperature
  tolerance) MUST be off by default, user-switchable, and shown on every light that used them.
- **FR-011**: System MUST NOT invalidate calibration frames by site, rig or age heuristics; it MUST show
  evidence (for example the flat ratio image) and leave the decision to the user.
- **FR-012**: System MUST record provenance for every master (source frames, excluded frames and
  reasons, method, engine version) and which datasets use it.
- **FR-013**: When a master changes or is retired, System MUST list affected datasets and mark their
  outputs "Stale" without re-processing until the user accepts.

### Key Entities

- **Calibration set**: raw frames grouped for one master (from spec 001).
- **QA result**: per frame: measurements, verdict (pass, warn, reject), reason, evidence images.
- **Master**: as in spec 001, plus build method, source frames, QA summary, falloff, dust motes and
  validity window.
- **Calibration match**: light → dark and flat (and bias or dark flat), with the rule and any fallback
  used.
- **Calibration rules**: user settings: tolerances, fallbacks, master-building method.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the phase 2 tree, QA rejects exactly the one corrupt frame and no clean frame
  (0 false rejects over 551 frames).
- **SC-002**: The injection self-test recovers at least 99% of synthetic 15 ADU stars in a dark, with no
  more than 3 false detections per frame.
- **SC-003**: Masters built by SubStation from the phase 2 frames reproduce the spike's statistics
  (falloff within 0.5 percentage points, median level within 0.5 ADU).
- **SC-004**: Every light in the test trees has either a match or an "Awaiting calibration" reason; none
  is silently uncalibrated.
- **SC-005**: Building a 50-frame master flat completes within 5 minutes on the reference NAS.

## Assumptions

- Mono cameras first; one-shot-colour (CFA) masters are out of scope for v1.
- Defaults follow Siril's bundled preprocessing method; WBPP-style linear-fit clipping for flats can be
  offered later.
- The owner judges flat validity; SubStation never decides it.
- Dark scaling (optimisation) is out of scope for v1; exposures must match exactly.

## Amendment 2026-10-10: v2 design (docs/design/v2, A3 and D4)

- **Calibration screen (A3)**: masters per rig (rig filter, Rescan), with whatever blocks grading first
  ("Heart Nebula · Askar 71F · OIII is waiting for a flat. 2 subs from 7 October 2026 can't be graded.
  Looking for an OIII flat … within 30 days." with **Use nearest flat**). A table of masters: type, what it
  matches, frame count, created, used by (datasets and sessions), state (**Current**, **Kept for 2025 data**,
  **Weak match for N**, **Missing**, **Unused · 19 months**).
- **Dataset Calibration tab (D4)**: one row per session: subs, dark, flat and bias used, each with the match
  quality in plain English ("Exact match"; "Same rotation · 2 days before"; "Weak: 33 days before"), a
  banner when sessions have weak flat matches, and **Change** to point a session at other frames (re-calibrates
  and re-grades only that session).
- Flats are matched per session; a flat more than 21 days from the lights is a **weak** match (used, and
  flagged). Rotation matching needs plate solving and follows with it.

## Amendment 2026-10-10 (owner): a flat's age is not evidence

An old flat is fine while the optical train hasn't changed, so an age limit is no test of a flat. A flat's
age alone never makes a match weak or invalid. The age is shown as information ("44 days before"). A flat match
is flagged only on evidence: a different camera or binning (never matched), a rotation change from plate solves
(later), or a measured difference from a newer flat of the same filter (ratio image, FR-007). The 21-day "weak"
rule in the v2 design amendment is withdrawn; `weak_flat_days` exists as an opt-in setting, off by default.
The owner judges flat validity (FR-011): SubStation shows evidence, including dust motes and falloff for each
master flat, so lenses known for uncorrectable dust (the TTArtisan) can be judged by eye.

## Amendment 2026-10-10: design review

From the full design review (`docs/design/design-review.md`, sections B–D): every SubStation design file and the brand guidelines were checked against the build. These requirements add to the ones above; where the design files disagree, the decisions in spec 007 apply.

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
## Amendment 2026-10-11 (owner): see the flat, find masters

- **002-DR-09 Flats are visible.** A session's current flat and every flat offered by Change show a thumbnail
  (the built master's preview, else a frame's QA thumbnail) that opens at 100%, so a Duo NB flat can be told from
  an OSC one by eye. Change offers flats as picture cards, not a dropdown.
- **002-DR-10 Masters search.** The calibration library has the Library's search, filter and date range (plus
  rig), applied to masters and raw sets; each master row has a thumbnail that opens at 100%.
- **002-DR-11 Built masters have a date.** A master built here takes the night its frames were shot.
- **002-DR-12 Short QA notes.** A good frame says nothing; others say what's off in a few words ("Level 98 ADU
  (+18 vs set 80). 90 spots (typical 24): possible light leak."). Stored notes were rewritten to match.
- **002-DR-13 A filter change shows the move.** After setting a session's filter its row stays, faded, reading
  "Moving to <filter>…", then links to the dataset the subs moved to; you stay on the page.
- **002-DR-14 Wait for a closer flat.** While a flat set from a light's own night (or nearer than the best built
  flat) is still queued or building, the light waits ("waiting for the 11 Oct OIII flats to be built") instead of
  taking an older flat. Subs already calibrated with another flat are re-calibrated automatically once a flat from
  their own night exists; other newer-calibration cases still wait for the owner (002 C11). (Owner 2026-10-11.)

## Amendment 2026-10-12: choosing a flat is a table of your filter's flats

The card grid of every flat ("Flats OIII", "Flats SII", "Flats G" for an Hα session, many with no picture) made
picking a flat slow: the session's own filter should come first, in a table, with a preview on hover.

- **002-DR-16**: Change opens a full-width panel under the session. Flats of the session's filter are listed first
  in a table (flat, filter, night, days from the session, frames, telescope, built / to build / library master),
  nearest night first; hovering a flat's name shows its preview. Flats of other filters are hidden behind "Show
  other filters (n)", for a session whose own filter is wrong, and are marked when shown. A flat set SubStation
  built is listed once (as its set), not again as a library master.

## Amendment 2026-10-12: masters are applied in the light's row order

M81 Hα (Feb 2026) showed the OAG's bright patch on one side and its shadow on the other, and a dust mote
twice: the flat was applied upside down. Cause: Siril keeps a NINA FITS light as written (`ROWORDER=TOP-DOWN`) but
writes converted XISF masters bottom-up, and nothing reconciled the two. A sweep of the NAS found 900 of 2,171
calibrated subs affected (755 XISF lights with top-down FITS darks; 125 top-down FITS lights with XISF flats; 20
with both).

- **002-DR-17**: Before calibrating, each master MUST be put in the light's row order (a flipped copy, cached);
  the same holds for the dark flat or bias applied to raw flats when building a master. Affected subs are
  recalibrated and re-graded (manual verdicts kept); masters stacked from them go stale.

## Amendment 2026-10-13: flats' filter, flat picker links and previews

- **002-DR-18**: A flat set's page lets a user say which filter the flats were taken through. A camera with no
  filter wheel records none, so flats shot through a Duo NB read as OSC; the correction is stored per flat (like a
  session's filter), regroups them with that filter's flats, and lights are matched again. Only flats take a
  filter.
- **002-DR-19**: In the flat picker, a flat set's name links to its page, and every row's hover preview shows an
  image: the built master, else one of its flats; when none can be drawn the card says so instead of staying blank.

## Amendment 2026-10-13: one exposure, one format; one row order per master

- **002-DR-20**: When the capture software saved the same exposure as both FITS and XISF (same camera, type and
  DATE-OBS), the XISF copy is set aside by a content ignore rule noted "Same exposure as <file> (FITS)". Stacking
  both would mirror a flat: Siril reads XISF bottom-up and NINA's FITS top-down, so every dust mote and the OAG
  shadow appear twice (found on the NGC 7822 flats: three sets of 50 FITS + the same 50 as XISF).
- **002-DR-21**: Before a master is stacked, every converted frame is put in the first frame's row order, so no
  master mixes orientations even when a set legitimately holds both formats. The build report says how many were
  turned.
- **002-DR-22** (2026-10-13): A master SubStation builds takes its camera and telescope from its own header (Siril
  keeps its frames'), resolved through the equipment aliases like a light, not from its set's label at build time.
  A later rig merge or correction then reaches the master too. (17 Sony masters built while the Sony frames were
  filed under the ATR2600M rig had kept "ATR2600M", showing ATR2600M data before the camera was bought.)

## Amendment 2026-10-14: masters build themselves

Two new bias sets sat unbuilt, and the 15 flat sets blocked for want of a bias stayed blocked once the bias existed:
masters were built only from the Build buttons.

- **002-DR-23**: SubStation builds a master for a raw calibration set (bias, dark flat, dark, flat) once it has 3+
  usable frames and nothing has arrived for 20 minutes, and again when frames arrive after its last master. A
  flat build blocked for want of a bias, dark flat or dark is retried once such a master at the same camera, gain
  and offset has been built. A set with a build queued or running waits; a failed build is not retried by itself.
  Checked every five minutes by one worker container at a time; Settings → Calibration can switch it off
  (`calibration.auto_build`). A finished master re-matches waiting lights, which queues their calibration.

## Amendment 2026-10-14: frames with no night; jittered flats

M 81 L (13 Feb) waited for a flat although a 14 Feb 06:22 L flat existed and the flat picker called it "same night".
The flat, from KStars/INDI, recorded no site, so it had no night, and matching fell back to its UTC date (the 14th),
"after" the lights. The 17 Feb L flats were four sets because NINA's flat wizard gives each run a slightly different
exposure (0.00654 / 0.00655 s) and sets required an exact match.

- **002-DR-24**: A frame with no recorded night is dated by its evening, as NINA's `$$DATEMINUS12$$`: local solar time
  (UTC + longitude / 15 h, from the frame, else the installation's site, else Greenwich) minus 12 hours. Flats of one
  camera, filter, gain, offset and binning in one session form one set when their exposures are within 5%; darks and
  bias still match exactly. Existing split flat sets were merged by a migration, their built masters moving with them.

### Amendment 2026-10-14: a master built mid re-match is not missed

- **002-DR-25 Every new master gets a re-match that sees it.** Re-matching every light reads the masters there are
  when it starts. A request made while one is waiting joins it; a request made while one is already running queues
  one more run after it, since the running one may have read the masters before the new one existed (three dark
  masters built a few minutes apart: the 60 s one finished during the re-match the 2 s one started, and its lights
  stayed blocked). All the places that ask for a re-match share one key, so at most one runs and one waits.
- **002-DR-26 The dark picker never hides a mismatch.** Each master dark or bias offered for a session shows its gain,
  offset and temperature. Those that fit the session's subs are listed first; the rest are listed apart, each saying
  how it differs ("gain 120, the subs are 100"), with a warning when one is picked and when none fits. A session
  chosen by hand can go back to automatic: its choice is forgotten, it is matched again, and a sub calibrated with
  masters it no longer uses loses that calibration and its grade until it is calibrated again.
  A session given only a flat (or only a dark) by hand takes the other from matching; with none to be had it waits
  for one instead of being calibrated without it (a flat chosen for M 42 · B calibrated 41 subs with no dark), except
  on rigs calibrated with a flat alone.
- **002-DR-27 A dark that saw light is not a dark.** A dark, bias or dark flat frame above a fifth of full scale is
  rejected by QA with the reason (light reached the sensor: a cover off or a flat panel on), and a flat build passes
  over a built dark-flat master that bright for the next calibrator (a dark at that exposure, else the bias). A set of
  KStars "dark flats" at 29,400 ADU, as bright as the flats, had calibrated a flat set down to nothing.
  A re-match that starts while an earlier one is still going waits for it (three ran side by side and slowed each
  other).
