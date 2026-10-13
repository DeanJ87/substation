# Feature Specification: Stacking and masters

**Feature Branch**: `004-dataset-stacking`

**Created**: 2026-10-09 · **Revised**: 2026-10-09 (owner feedback: flexible scopes and inclusion,
stack history, stack everything)

**Status**: Draft

**Input**: Scope: stack subs into masters with full flexibility (one night, several nights, a date range, a whole
dataset across years, or everything), using the effective verdicts or another inclusion rule up to every sub
regardless of grade; keep every stack with the recipe that made it so earlier stacks can be browsed, compared and
reproduced; report quality by SNR and regional PSF; keep masters in step with their inputs; write them to
SubStation's output area. Sources: phase 1 step 4e,
phase 2 steps 4 and 5, design states Integrating and Stale, owner feedback.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stack a chosen scope with a chosen inclusion rule (Priority: P1)

The user picks what to stack (a night, several nights, a date range, a whole dataset across years, or
several datasets of the same target and filter) and how to choose subs (effective verdicts, which is the
default; accepted only; every graded sub; or everything including rejected). SubStation shows how many
subs and how much integration that is before starting.

**Why this priority**: stacking is the end product, and the owner wants to explore freely.

**Independent Test**: For NGC 7000 Panel 1 OIII: stack the 10-07 night with default rules (10 subs,
6,000 s), then "everything" (15 subs); both are produced, and each master lists exactly its subs.

**Acceptance Scenarios**:

1. **Given** a scope and the default rule, **When** the user starts a stack, **Then** only effective
   Accepted and Down-weighted subs are used (down-weighted at their weight), and the preview before
   starting states the count, integration and nights.
2. **Given** the "everything" rule, **When** stacked, **Then** all subs in scope are used, including
   rejected ones, and the master is labelled as such.
3. **Given** a scope across several years, **When** stacked, **Then** subs are registered to one
   reference chosen by quality, and each night's calibration is applied to its own subs.
4. **Given** a sub that fails registration, **When** stacking, **Then** it is excluded, recorded with the
   reason "could not match stars", and the stack completes.
5. **Given** the output area is not writable, **When** the master is written, **Then** the error reads
   "Couldn't write the master … Your subs and grades are safe" with Retry.

---

### User Story 2 - Every stack is kept and can be revisited (Priority: P1)

Each stack is saved with its recipe (scope, inclusion rule, options, calibration used, engine version,
who ran it and when). The user can browse previous stacks for a dataset or night, open any of them, and
re-run a recipe.

**Why this priority**: the owner wants to see previous stacks and compare approaches.

**Independent Test**: After two stacks of the same dataset with different rules, both are listed with
their recipes and quality reports; re-running one produces the same inclusion list.

**Acceptance Scenarios**:

1. **Given** a dataset with several stacks, **When** opened, **Then** its stacks are listed newest first
   with scope, rule, sub count, integration, key quality figures and state (current or Stale).
2. **Given** an older stack, **When** the user chooses Re-run, **Then** the same recipe runs on the
   current inputs and the result is a new stack; the old one is kept.
3. **Given** a stack the user no longer wants, **When** deleted, **Then** only SubStation's output file
   and record are removed, after confirmation, and the deletion records who did it.

---

### User Story 3 - The user sees how good a stack is and compares stacks (Priority: P1)

Each stack has a quality report: subs and integration used, background noise, SNR, star count, FWHM and
roundness in the centre and each corner, and a preview with 100% crops. Any two stacks of the same
target and filter can be compared side by side.

**Why this priority**: noise alone misleads; regional PSF reveals optical issues that selection cannot fix.

**Independent Test**: For NGC 7000 Panel 3 the report shows the top-right corner about 75% softer than
the centre; comparing "default" and "everything" shows the SNR and FWHM differences the spike measured.

**Acceptance Scenarios**:

1. **Given** a stack, **When** its report opens, **Then** centre and corner FWHM and roundness are shown,
   with a note when corners differ markedly ("Top-right stars are 74% larger than the centre: check
   sensor tilt").
2. **Given** two stacks, **When** compared, **Then** they are compared on SNR, regional FWHM and roundness,
   star count and integration, never noise alone.

---

### User Story 4 - Stacks stay in step with their inputs (Priority: P2)

When new subs arrive in scope, grades change, or calibration changes, affected stacks are marked Stale
with the reason, and can be re-run from their recipe.

**Independent Test**: Override one sub in a stacked night; that night's default stack shows Stale with the
reason; the "everything" stack does not, because its inclusion did not change.

**Acceptance Scenarios**:

1. **Given** a change that alters a stack's inclusion list or calibration, **When** it happens, **Then** that
   stack shows Stale (square outline, slash) with the reason; stacks unaffected by the change stay current.

---

### User Story 5 - Optional automatic stacks and options (Priority: P3)

The user can switch on automatic stacking (for example a default-rule stack of each night when the night
ends) and can use options (noise weighting, distortion correction, drizzle) compared against the default.

**Independent Test**: With automatic nightly stacks on, replaying a night produces one stack at the end;
stacking Panel 1 OIII with noise weighting shows lower SNR than the default, as in the spike.

**Acceptance Scenarios**:

1. **Given** automatic nightly stacks are on, **When** a night ends (no new subs for a configurable time
   after astronomical dawn), **Then** a default-rule stack of that night is queued.
2. **Given** an option, **When** a comparison stack runs, **Then** both results are shown side by side with
   the time each took.

### Edge Cases

- Fewer than 3 usable subs: stacking is allowed with a warning; automatic stacks skip it.
- Mosaic panels are stacked separately.
- Meridian flips are handled by registration.
- Different calibration per night inside one stack is expected and recorded.
- Large scopes (for example thousands of subs across years) are queued, use the disk budget, and show
  progress and an estimate; if the budget would be exceeded the stack waits and says why.
- Restart during stacking: the job restarts cleanly; partial outputs are never presented as masters.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to define a stack's scope as any of: one night, selected nights, a date
  range, a whole dataset, or several datasets with the same target, filter, camera and telescope.
- **FR-002**: Users MUST be able to choose an inclusion rule: effective verdicts (default), accepted only,
  all graded subs, or everything in scope; plus manual inclusion or exclusion of individual subs.
- **FR-003**: Before starting, System MUST preview the sub count, integration time, nights and any subs
  that cannot be used (for example awaiting calibration).
- **FR-004**: System MUST register subs, exclude those that fail registration with a recorded reason, and
  stack with the defaults measured best in the spikes (winsorized sigma clipping, additive with scale
  normalisation, weighting by weighted FWHM), applying each sub's own calibration.
- **FR-005**: System MUST save every stack with its recipe (scope, rule, manual changes, options,
  calibration, engine version, user, time) and its exact inclusion list and weights.
- **FR-006**: Users MUST be able to browse stacks by dataset and night, open any stack, re-run its recipe,
  and delete SubStation's stack outputs.
- **FR-007**: System MUST produce a quality report per stack (subs, integration, noise, SNR, stars, centre
  and corner FWHM and roundness, previews) and compare stacks on SNR and regional PSF.
- **FR-008**: System MUST mark a stack Stale when a change alters its inclusion list or calibration, with
  the reason, leaving unaffected stacks current.
- **FR-009**: System MUST write stacks as FITS to SubStation's output area, with headers recording
  provenance and the first and last sub times.
- **FR-010**: Stacking MUST run through the job queue with progress, respect the disk budget, and clean up
  intermediates after outputs and previews are written.
- **FR-011**: System MUST offer optional automatic nightly stacks (off by default) and optional stacking
  options (exclude down-weighted, noise weighting, distortion correction, drizzle) with comparison against
  the default.

### Key Entities

- **Stack recipe**: scope, inclusion rule, manual inclusions and exclusions, options.
- **Stack**: a run of a recipe: inclusion list and weights, calibration per sub, output file, quality
  report, state (queued, integrating, current, stale, failed), user and time.
- **Quality report**: the measures above, plus comparisons.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A 24-sub, 26-megapixel stack completes in under 5 minutes on the owner's NAS.
- **SC-002**: Stacks of the spike datasets reproduce the spike's quality figures (regional FWHM within 3%,
  SNR within 3%).
- **SC-003**: 100% of stacks list exactly the subs used; no sub outside the chosen rule is ever included.
- **SC-004**: Re-running a recipe on unchanged inputs produces an identical inclusion list.
- **SC-005**: A Stale stack is flagged within 1 minute of the change that made it stale.
- **SC-006**: Peak disk use stays within the configured budget (spike reference: about 200 MB per sub in
  flight).

## Assumptions

- Stacks are linear FITS; post-processing (stretching, colour combination, mosaics) is out of scope.
- Spike stacking defaults stand until new evidence shows a better choice.
- Registration and stacking are Siril's.

## Amendment 2026-10-10: v2 design (docs/design/v2, D5, A1, A4)

- Stacks are **masters**, numbered per dataset (**Master v1, v2, …**). The dataset's Masters tab shows the
  integration in progress at the top with its pipeline steps (Select inputs, Calibrate, Register,
  Normalise, Integrate, Write), progress and time left, View in Activity and Cancel; then finished
  versions with preview, sub and session counts, date, method, integration and FWHM, state (**Current**,
  **Superseded** with the reason, **Stale** with the reason), Download and Inputs.
- Defaults (Settings · Stacking): winsorised σ clip 3.0 / 3.0; weighting by grade (alternatives SNR,
  equal); registration reference by best FWHM (alternatives most stars, manual); auto-stack after each
  session, every 10 new subs, or never; output XISF or FITS, 32-bit float.
- Combined masters per collection (one per filter, registered to the reference framing) follow spec 006.

## Amendment 2026-10-10: design review

From the full design review (`docs/design/design-review.md`, sections B–D): every SubStation design file and the brand guidelines were checked against the build. These requirements add to the ones above; where the design files disagree, the decisions in spec 007 apply.

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

## Amendment 2026-10-11 (owner): combine within a project

- **004-DR-07 No combining across projects.** When a collection has projects, combining needs one: under
  "All datasets" the Masters tab shows each project's combined masters, each with its own button. The request
  carries the project (it hadn't, so every run combined everything and failed).
- **004-DR-08 Older masters out of the way.** Superseded, failed and cancelled masters are hidden behind
  "Show N older or failed", since an old image can look like another panel's.
- **004-DR-09 Combined masters at 100%.** A combined master has a 100% view and aberration inspector, made after
  combining.

## Amendment 2026-10-12: tilt on the photo, calibration you can see, fewer warnings

The master page had too many warning notices, its calibration frames couldn't be opened, its tables were hard to
read, and across-the-field quality was a table rather than something drawn on the photo.

- **004-DR-20**: A master's details MUST show the master at its own aspect ratio with switchable overlays: Tilt
  (each zone's FWHM and roundness drawn on the part of the image it describes, shaded by softness against the
  sharpest zone) and Annotate. The facts sit beside the image, not in a table.
- **004-DR-21**: The calibration masters a master used MUST be viewable from it (hover preview, click for 100%).
- **004-DR-22**: Informational notes (not calibrated yet, stale reasons, few subs) are plain muted text; colour is
  for verdicts and failures.
- **Fix**: zones had top and bottom swapped (Siril's y runs from the top); stored reports are corrected by
  migration 0013, so earlier tilt notes named the wrong corners.
