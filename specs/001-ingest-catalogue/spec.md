# Feature Specification: Ingest and catalogue

**Feature Branch**: `001-ingest-catalogue`

**Created**: 2026-10-09 · **Revised**: 2026-10-09 (owner feedback: metadata resolution, file tracking,
queue, ignore rules, mount layout)

**Status**: Draft

**Input**: Scope: SubStation watches the folders where subs land and builds a catalogue of
every light, flat, dark, dark flat, bias and master. Frames are known by content, so duplicates, BAD_
copies, renames, moved folders and reorganised datasets are understood. Metadata comes from headers
where present, otherwise from configurable folder and filename patterns, otherwise from the user, and
resolved values are stored in SubStation's database with their source. Work is queued so bulk arrivals
and outside changes are handled, and files can be ignored. Sources: docs/spikes phase 1 and 2,
docs/design brand guidelines, owner feedback.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - New subs appear in the catalogue as they land (Priority: P1)

An imager's capture software writes subs into a folder mounted into SubStation. During a live session
each new sub appears within seconds, filed under the right dataset and night, with its key values shown.

**Why this priority**: nothing else can happen until frames are found, identified and grouped.

**Independent Test**: Copy the phase 2 test tree into a watched folder file by file at capture pace;
every frame is catalogued within the time limit and grouped as the spike reports describe (for example
NGC 7000 Panel 3 Hα, 24 subs, night 2026-09-28).

**Acceptance Scenarios**:

1. **Given** a watched folder, **When** a light is written into it, **Then** within 10 seconds of the
   file being complete it appears under its dataset with target, panel, filter, exposure, temperature,
   time and night.
2. **Given** a file still being written, **When** seen, **Then** it is not catalogued until its size is
   stable and it parses; partial files never produce entries.
3. **Given** lights taken after local midnight, **When** catalogued, **Then** they belong to the same
   observing night as the evening's lights.
4. **Given** subs for two mosaic panels, **When** catalogued, **Then** each panel is its own dataset.

---

### User Story 2 - Files are known by content wherever they go (Priority: P1)

The imager renames, copies, reorganises and moves folders outside SubStation, syncs with tools that
leave duplicates, and uses NINA thumbs-down (which renames files with a `BAD_` prefix). SubStation keeps
one entry per unique frame, follows it to its new location, and keeps all grades and decisions.

**Why this priority**: double counting and lost decisions corrupt everything downstream.

**Independent Test**: Catalogue the phase 2 tree, then move a dataset's folder, rename half its files,
copy one night to a second folder and add `BAD_` copies; the frame count, grades and verdicts are
unchanged, the new paths are recorded, and the BAD_ frames carry user REJECT verdicts.

**Acceptance Scenarios**:

1. **Given** `BAD_x.xisf` and `x.xisf` with identical content, **When** both are seen, **Then** there is
   one frame with a user REJECT verdict and both paths are listed as copies.
2. **Given** a catalogued folder that is moved or renamed outside SubStation, **When** the change is
   seen, **Then** the frames are matched by content to their new paths, their grades and decisions are
   kept, and the move is logged (not sent to reconciliation).
3. **Given** a file copied to a second location, **When** seen, **Then** it is one frame with two copies.
4. **Given** a frame whose every copy has disappeared, **When** detected (and its share is reachable),
   **Then** the frame is marked missing, its datasets show "Needs reconciliation" with the count, and its
   grades are kept in case it returns.
5. **Given** a file is replaced by different content under the same name, **When** seen, **Then** it is
   treated as a new frame and the old frame's copy at that path is removed.
6. **Given** an unchanged file (same device, inode, size and modification time), **When** rescanned,
   **Then** it is not re-hashed.

---

### User Story 3 - Metadata is resolved even from poorly behaved software (Priority: P1)

Headers are used when present, but some capture software omits or mis-writes them. The user can define
folder and filename patterns (for example `{target}/{date}/{filter}/` or
`{date}_{filter}_{exposure}s_{seq}`) that fill gaps, and can correct any value. Corrections and inferred
values are stored in SubStation's database with their source and applied to every copy and to identical
future files.

**Why this priority**: without resolved metadata nothing can be grouped or matched.

**Independent Test**: Strip FILTER and EXPTIME from copies of 20 phase 1 lights; with a filename pattern
configured they group correctly, each value shows "from filename"; without a pattern they appear on the
reconciliation list, and one bulk correction resolves all 20.

**Acceptance Scenarios**:

1. **Given** a frame with complete headers, **When** catalogued, **Then** each value shows "from header".
2. **Given** a frame missing FILTER, **When** a configured pattern provides it, **Then** the value shows
   "from folder pattern" or "from filename pattern", with the pattern named.
3. **Given** a value no source provides, **When** catalogued, **Then** the frame goes to reconciliation
   with the missing field named and any suggestion shown.
4. **Given** the user corrects a value for a selection of frames, **When** saved, **Then** it applies to
   them, records who changed it and when, and affected datasets regroup; no source file is modified.
5. **Given** a header and a path pattern disagree, **When** catalogued, **Then** the header wins (unless
   the user has set a rule to prefer the pattern for that folder) and the disagreement is shown.

---

### User Story 4 - Bulk arrivals and outside changes are queued (Priority: P1)

After a holiday the imager drops 400 files in at once, or another tool adds subs while SubStation was
off. Everything is queued, shown with progress, and processed without blocking live subs.

**Why this priority**: bursts are normal and must not stall or overload a NAS.

**Independent Test**: Start SubStation stopped, add the 653-file phase 2 tree, start it, and feed live
subs into another folder; live subs meet the 10-second limit, the bulk set completes, and the queue
survives a restart midway.

**Acceptance Scenarios**:

1. **Given** hundreds of new files, **When** seen, **Then** they are queued, the dashboard shows the queue
   length and estimated completion, and live arrivals are processed first.
2. **Given** SubStation restarts mid-queue, **When** back, **Then** it resumes without repeating finished
   work.
3. **Given** SubStation was off while files changed, **When** it starts, **Then** a scan finds every
   addition, move and deletion since it last ran.

---

### User Story 5 - The user ignores what should not be processed (Priority: P2)

The user can ignore folders and filename patterns (for example test shots, a `_old` folder) and
individual frames. Ignored content stays ignored if it reappears elsewhere.

**Why this priority**: keeps the catalogue clean; not needed on the first night.

**Independent Test**: Ignore one frame and one folder; move the frame elsewhere and copy the folder; neither
is processed, and both are listed under Ignored with an undo.

**Acceptance Scenarios**:

1. **Given** an ignored frame, **When** its content appears at another path, **Then** it remains ignored.
2. **Given** an ignore rule, **When** undone, **Then** the matching files are queued for processing.

---

### User Story 6 - Calibration frames and masters are recognised (Priority: P2)

Flats, darks, dark flats, bias frames and existing masters (including PixInsight WBPP masters) are
catalogued and grouped into calibration sets for spec 002.

**Independent Test**: On the phase 2 tree the catalogue reports 6 flat sets of about 50 frames, 3 dark-flat
sets (2 s ×150, 1 s ×50, 0.01 s ×50) and 36 WBPP masters.

**Acceptance Scenarios**:

1. **Given** NINA darks with OBJECT "FlatWizard" at a flat exposure, **When** catalogued, **Then** they are
   classified as dark flats with the reason shown and changeable.
2. **Given** raw flats, **When** grouped, **Then** sets form by filter, session (more than 2 hours apart
   starts a new session), exposure, gain, offset and binning.
3. **Given** a WBPP master with integration and rejection-map images, **When** catalogued, **Then** only
   the integration image is the master.

---

### User Story 7 - Datasets span years and are browsable by night (Priority: P2)

A target may be imaged over many nights across years. A dataset collects them all, and the user can
look at the whole dataset or any single night.

**Independent Test**: Combine the phase 1 and phase 2 NGC 7000 data; the dataset shows both nights, each
night separately browsable with its own counts.

**Acceptance Scenarios**:

1. **Given** a dataset with subs from several nights, **When** opened, **Then** it lists its nights with
   counts and integration per night, and each night opens on its own.

### Edge Cases

- AppleDouble (`._*`) and `.DS_Store` files, including `._*.xisf`, are ignored and never parsed.
- Unreadable or non-image files are listed with the error and skipped.
- A network share disappears: nothing is marked missing until it is reachable again.
- FILTER values differing only by case or spaces are one filter; aliases are user-editable.
- Sequence numbers repeat and are never identity.
- Missing site longitude: night uses the configured site, flagged.
- Two cameras or telescopes in the same folder produce separate datasets.
- The same content in two watched libraries is one frame.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST watch one or more configured libraries recursively, detecting new, changed,
  moved and deleted files by change notification where reliable and by periodic scanning always.
- **FR-002**: System MUST treat libraries as read-only and MUST NOT write, rename, move or delete anything
  in them.
- **FR-003**: System MUST read FITS (including compressed) and XISF headers, including multi-image XISF,
  without reading pixel data during cataloguing.
- **FR-004**: System MUST consider a file complete only once its size is stable and it parses.
- **FR-005**: System MUST identify frames by SHA-256 of content, use a file fingerprint (device, inode,
  size, modification time) only to skip re-hashing, and fold identical content into one frame with all
  copies recorded.
- **FR-006**: System MUST follow frames across moves, renames, copies and folder reorganisations without
  losing grades, verdicts or corrections, and log each such change.
- **FR-007**: System MUST record a user REJECT verdict for any frame with a `BAD_`-prefixed copy, separate
  from machine grades.
- **FR-008**: System MUST resolve each metadata field from headers, then user-configured folder and
  filename patterns, then user input; store the value with its source in the database; and never write
  to source files.
- **FR-009**: Users MUST be able to correct metadata for one or many frames at once; corrections apply to
  all copies and future identical content and record user and time.
- **FR-010**: System MUST classify frames as light, flat, dark, dark flat, bias or master, show the reason,
  and allow override.
- **FR-011**: System MUST group lights into datasets by target, panel, filter, camera, telescope, binning,
  gain and offset; datasets span any number of nights and years and are browsable per night.
- **FR-012**: System MUST compute each frame's observing night from the resolved UTC start and site
  longitude.
- **FR-013**: System MUST group calibration frames into sets by type, filter (for flats), exposure, gain,
  offset, binning, set temperature and session.
- **FR-014**: System MUST maintain a reconciliation list for unresolved values and unexplained changes
  (content missing, conflicting copies), with reasons and suggestions, and mark affected datasets
  "Needs reconciliation".
- **FR-015**: All ingest work MUST go through a persistent, prioritised queue (live first, then bulk, then
  archive scans), visible with progress, and resumable after restart.
- **FR-016**: Users MUST be able to ignore folders, path patterns and individual frames; ignored content
  stays ignored wherever it reappears; ignores can be undone.
- **FR-017**: System MUST normalise filter names (case, whitespace, user aliases) for grouping and keep the
  original value.
- **FR-018**: System MUST provide empty and error states in the design's voice.

### Key Entities

- **Frame**: unique content (hash); resolved metadata with per-field source; classification; night;
  status (present, missing, ignored).
- **Copy**: a path where a frame's content exists; fingerprint; first and last seen.
- **Metadata value**: field, value, source (header, folder pattern, filename pattern, inferred, user),
  who and when for user values.
- **Path pattern**: user-defined rule mapping folder and filename tokens to fields, scoped to a library
  or folder, with precedence.
- **User verdict**: human decision on a frame (NINA BAD_ or in-app), with user and time.
- **Dataset**: lights sharing the grouping keys; spans nights; has a state.
- **Night**: an observing night at a site.
- **Calibration set**, **Master**: as in spec 002.
- **Reconciliation item**: unresolved value or unexplained change, with reason, suggestion, resolution.
- **Ignore rule**: folder, pattern or content; who and when.
- **Job**: queued work item with priority, state, attempts and timings.
- **Library**: a mounted source root and its scan status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% of new subs appear within 10 seconds of the file being complete during a live session
  on the owner's NAS, including while a bulk ingest is running.
- **SC-002**: On the phase 1 and 2 trees, grouping, BAD_ folding, night assignment and the reconciliation
  list match the spike reports (0 differences).
- **SC-003**: After moving, renaming and duplicating test folders outside SubStation, 100% of grades,
  verdicts and corrections are preserved and no frame is double counted.
- **SC-004**: No file in a library changes (content, name, timestamps) as a result of SubStation.
- **SC-005**: A 400-file bulk drop is fully catalogued within 15 minutes on the owner's NAS, and a
  10,000-frame archive scan completes without breaching SC-001.
- **SC-006**: Rescanning an unchanged 10,000-frame library takes under 2 minutes (no re-hashing).

## Assumptions

- Deployment follows the constitution's layout: libraries mounted read-only under `/data/library`,
  SubStation's writable area at `/data/substation`.
- Capture software is NINA first; others are handled through headers plus path patterns.
- Mosaic assembly is out of scope; panels are separate datasets.
- Hashing reads every new file once; on a NAS this is the dominant ingest cost and is queued.

## Amendment 2026-10-10: v2 design (docs/design/v2)

- Navigation is **Library · Review · Calibration · Activity · Settings**, with counts on Review (subs to
  review) and Activity (jobs running), and "Watching N folders" in the header. The Datasets dashboard becomes
  the Library (spec 006). The reconciliation list stays, reached from the Library's "Needs reconciliation"
  notices and states.
- Datasets are shown as "Rig · Filter" (spec 006), inside their collection.

## Amendment 2026-10-10: design review

From the full design review (`docs/design/design-review.md`, sections B–D): every SubStation design file and the brand guidelines were checked against the build. These requirements add to the ones above; where the design files disagree, the decisions in spec 007 apply.

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
   SubStation, Solve, Header, Pattern or User. A field with no value MUST
   show "Not recorded".
5. **001-DR-05**: The system MUST read sky quality (SQM keyword), weather (AMBTEMP, HUMIDITY, DEWPOINT, CLOUDCVR,
   WINDSPD), guiding RMS and capture software (SWCREATE) from headers when present, and MUST treat all of them as
   optional.

8. **001-DR-08**: Each session header on the Subs tab MUST list the conditions recorded for that night (SQM,
   ambient temperature, humidity, guiding RMS, cloud periods with their source), omitting any that are not
   recorded.
## Amendment 2026-10-11 (owner): mislabelled calibration frames

- **001-DR-09 Folder and name beat a Light header.** When a capture program wrote IMAGETYP Light but a folder
  on the path and the file name both name the same calibration type (…/Darks/Dark_180s_….fits), the frame is that
  type, with the reason "Header says Light, but the folder and file name say dark". A light that merely sits in a
  Darks folder stays a light.

## Amendment 2026-10-11 (owner): a reconcile group says what it is

Reconcile groups gave too little to tell what each group was.

- **001-DR-10 Each reconcile group explains itself.** A group shows, from one example file: its frame type as
  classified (Master dark, Light, Unknown), the library and full folder it lives in, the example's file name and a
  thumbnail (click for the close look), the number of files and the nights they span, and the header values that
  are known (camera, exposure, filter, gain, offset, set and sensor temperature, date and night, binning, image
  size) as label: value chips, with any missing one marked "missing" in the warn colour. One plain line says what
  is needed and why ("Needs gain and offset so it can be matched to lights shot at −20 °C"). Next to the answer
  form, "Ignore this folder" and "Ignore files like this" (a file-name glob with digit runs as `*`) add an ignore
  rule scoped to the library; the group leaves the list at once with a toast, and Undo is in Settings → Ignored.
  The list leaves out files an active ignore rule covers even before the worker marks them ignored. The API keys
  each item's group (kind, field, library, folder) and puts the example on the group's first item only: two extra
  queries for all examples (open fields, image sizes), none per file.
- **001-DR-11 Already-processed copies are not subs.** A light that PixInsight (or anything leaving FITS HISTORY
  ImageCalibration/StarAlignment/Debayer lines) has already calibrated, registered or debayered is classified
  "processed", not "light", so WBPP's calibrated/_c and registered/_r copies don't double a night's subs or skew its
  stretch. (Owner 2026-10-11.)

## Amendment 2026-10-13: 8-bit captures are set aside

Early Sony A7 III files were saved as 8-bit RGB and are of no use for calibration or stacking. Any catalogued file whose image is 8-bit (BITPIX=8 or UInt8), whatever
its type (light, flat, dark), gets its own content ignore rule noted "8-bit capture: camera-processed data, not raw".
It leaves its dataset and calibration, shows in Settings → Ignored, and can be undone there. Nothing is deleted;
the files stay where they are for the owner to remove. New 8-bit files are set aside when catalogued. (The library
held 326, all Sony A7 III: 118 lights, 157 flats, 51 darks.)

## Amendment 2026-10-13: no site details in the repository

The repository holds nothing specific to one installation: no host names, domain names, user names or storage
paths. `docker/compose.nas.yml` takes them as required stack variables (`SUBSTATION_DOMAIN`, `SUBSTATION_STATION`,
`SUBSTATION_CATALOGUES`, `SUBSTATION_LIBRARY`, `SUBSTATION_ARCHIVE`), so a missing one stops the deploy rather than
starting on an empty folder; `docker/nas-prepare.sh` takes `NAS`, `ROOT` and `CATALOGUES`; the post-processing
helper needs `--url` or `SUBSTATION_URL`.

## Amendment 2026-10-14: guiding RMS from NINA's file names

NINA doesn't write guiding RMS into the header, so the rig's lights pattern carries it in the name
(`…_600.00s_RMS$$RMSARCSEC$$_$$FRAMENR$$`). When nothing was guided, NINA writes `_RMS_` and the frame number
follows; that number must never be read as the RMS. After `_` or a space only a decimal counts (`_RMS0.62_`,
`guiding_0.8`); after `-`, `=` or nothing, any number does.

## Amendment 2026-10-14: rules hold for files already queued

Darks shot in daylight were ignored with a file-name rule while Robocopy was still copying them; one queued before
the rule was saved was still read and catalogued. A queued file is now checked against the folder and file-name
rules again when it is read, and left out if one matches.

### Amendment 2026-10-14: a stack is not a sub

- **001-DR-12 A light that holds many subs is a master light.** Some capture devices save their own running stack
  next to the subs with the same light type and sub exposure (a Seestar's Stacked_153_….fit says STACKCNT 153). A
  light whose header says it combines more than one sub (STACKCNT or NCOMBINE) is catalogued as a master light, with
  the reason, so it is never graded or stacked with the subs. Frames already catalogued are re-read.
