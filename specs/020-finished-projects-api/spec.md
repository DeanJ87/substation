# Feature Specification: Finished projects and the render read API

**Feature Branch**: `poc-substation`
**Created**: 2026-10-21
**Status**: Draft
**Input**: Owner, 2026-10-21: a separate renderer app (dean0 render) needs a finished image plus SubStation's data
about how it was captured, to make branded videos and stills. SubStation is authoritative up to and including the
stacked masters; finishing happens by hand outside it. Builds on the roadmap item "Finished work and a public API".

## User Scenarios & Testing

### User Story 1 - Finished projects appear in SubStation (Priority: P1)

The owner keeps finished work in one folder per project in a library with the Completed role:
`<Astro|Nightscapes|Videos>/<subject>/<YYYY…> <name>/` with `project/`, `exports/`, `web/` and `social/` inside.
SubStation scans that library (read-only, like any source) and lists each project folder as a finished project, with
its exported image files, a thumbnail, and when it last changed.

**Why this priority**: nothing else works without knowing where finished images are.

**Independent Test**: point a Completed library at a folder with two project folders; both appear under Finished,
with their exports listed and thumbnails shown; adding a file to `exports/` updates the project within one scan.

**Acceptance Scenarios**:

1. **Given** a Completed library with `Astro/IC 1805/2026 Heart Nebula/exports/heart-final.png`, **When** it is
   scanned, **Then** a finished project "2026 Heart Nebula" (subject IC 1805, kind Astro) lists that file.
2. **Given** an export is replaced by a new version with the same name, **When** the library is rescanned,
   **Then** the project shows the new file (tracked by content) and its "updated" time moves on.
3. **Given** a folder that doesn't match the layout, **When** it is scanned, **Then** it is listed under "Not a
   project" with the reason, never guessed into a project.

### User Story 2 - Link a finished project to its data (Priority: P1)

The owner links each finished project to the SubStation project (and so its collection) whose subs made it, and
says which export is the final image and, where present, the starless, stars-only and per-filter images.
SubStation suggests the link by target name and plate-solve overlap.

**Why this priority**: without the link there is no capture data to show.

**Independent Test**: open an unlinked finished project, accept the suggested SubStation project, mark the final
and starless files; the project's data preview fills in.

**Acceptance Scenarios**:

1. **Given** a finished project named after IC 1805 and a SubStation collection "Heart Nebula" whose plate solves
   overlap it, **When** the owner opens the link dialog, **Then** that collection's project is the first suggestion,
   with the reason ("same target", "overlapping field").
2. **Given** a finished project with files `*-final.*`, `*-starless.*`, `*-stars.*`, **When** it is first linked,
   **Then** those roles are pre-selected and the owner can change any of them.
3. **Given** a finished project with no final image chosen, **When** the renderer asks for it, **Then** it is not
   offered (status "needs a final image"), never shown with a placeholder.

### User Story 3 - The renderer reads a project over a token API (Priority: P1)

The owner creates a personal API token in Settings (named, shown once, revocable) for the renderer. With it, the
renderer lists finished projects changed since a time, reads one project's render data, and downloads its files.
The token can only read this API: it can't log in, change anything or reach the rest of SubStation's API.

**Why this priority**: this is the interface the renderer is built against.

**Independent Test**: create a token; with it, list projects, fetch one project's data and its final image; the
same token is refused everywhere else; after revoking it, every call is refused.

**Acceptance Scenarios**:

1. **Given** a valid token, **When** the renderer asks for finished projects changed since a time, **Then** it gets
   only projects that are linked, have a final image, and changed after that time, oldest change first.
2. **Given** a valid token, **When** it asks for one project, **Then** it gets that project's render data (Story 4)
   with links to every file the project has.
3. **Given** a revoked, expired or wrong token, or no token, **When** any render API call is made, **Then** it is
   refused, and nothing about projects is revealed.
4. **Given** a valid render token, **When** it is used on any other SubStation endpoint, **Then** it is refused.

### User Story 4 - The render data describes how the image was made (Priority: P1)

For a linked project, SubStation builds the render data from what it already knows: target, capture totals, a
timeline per night, per-sub quality, plate-solve annotations, and the processing steps the owner entered.

**Why this priority**: the renderer's presets are built on this data.

**Independent Test**: for a linked two-panel Hα/OIII project, the data's totals match the collection's Overview
(integration, kept/down-weighted/rejected, nights, per-filter time), its timeline has one row per night, filter and
panel, and no field carries site coordinates.

**Acceptance Scenarios**:

1. **Given** a linked project, **When** its render data is built, **Then** the totals match the SubStation
   project's numbers on screen (integration counts accepted and down-weighted subs only).
2. **Given** a project with no plate solves, **When** its render data is built, **Then** RA/Dec, annotations and sky
   tracks are absent, not zero or invented.
3. **Given** subs shot at a site, **When** the render data is built, **Then** it carries only the site's region
   name, Bortle class and latitude rounded to whole degrees.

### User Story 5 - Write project.json into the project folder (withdrawn 2026-10-21, 020-DR-12)

The renderer reads the live render API; SubStation no longer writes into the project folder.

### Edge Cases

- A project folder holding several candidate finals (crops, versions): the owner picks one; the others stay listed
  as extra exports.
- A finished project whose SubStation project was deleted or merged: it shows as unlinked with the reason; the API
  stops offering it until relinked.
- A finished project made from more than one SubStation project (e.g. two seasons): it can link to several; totals
  add up and the timeline covers both.
- Exports in formats the renderer can't use (PixInsight XISF, linear FITS): listed, but not offered as render files;
  the API only offers display-ready images (PNG, JPEG, TIFF).
- Very large exports (60 MP TIFF): the API serves them as they are, plus a thumbnail; resizing is the renderer's job.
- A filter with an unusual name: passed through exactly as SubStation normalises it (e.g. "Hα" with a Greek alpha).
- The Completed library is unreachable: the API answers with the last known list and says the library is
  unreachable, rather than returning an empty list.

## Requirements

### Functional Requirements

- **020-FR-001** A library can have the Completed role (alongside Active and Archive, spec 013). It is scanned
  read-only; SubStation never writes into it (020-DR-12).
- **020-FR-002** In a Completed library, a folder at `<kind>/<subject>/<name>/` is a finished project when `<kind>` is
  Astro, Nightscapes or Videos. Files under its `exports/`, `web/` and `social/` are its outputs; `project/` holds
  working files and is listed but never served.
- **020-FR-003** Finished projects are tracked by folder path and their files by content, like other files
  (Principle II): a renamed or replaced export is the same project with a changed file, not a new project.
- **020-FR-004** The owner links a finished project to one or more SubStation projects. Suggestions rank by target
  name match (including the collection's other names) and plate-solve field overlap, each with a stated reason.
- **020-FR-005** The owner assigns file roles: final (required to be offered to the renderer), starless, stars-only,
  per-filter (one per filter name), progressive stacks (ordered). Names ending in -final, -starless, -stars and a
  filter name are pre-selected on first link.
- **020-FR-006** The owner can enter the processing steps for a finished project as an ordered list of short labels
  (e.g. GraXpert, BlurXTerminator); a default list can be set in Settings.
- **020-FR-007** The render data (schema version 1) contains, when known:
  - **project**: id, name, kind, subject, updated time.
  - **target**: name, common name, type, constellation, RA/Dec from plate solves, distance, angular size.
  - **capture**: total integration; subs total/accepted/down-weighted/rejected from effective verdicts; nights,
    first and last night; mosaic panels and layout; per-filter subs, exposure and integration; rigs (telescope,
    camera, pixel scale, field of view); site as region, Bortle and latitude rounded to whole degrees.
  - **timeline**: per night, filter and panel: subs, integration, and the target's altitude/azimuth track that
    night.
  - **quality**: per kept or rejected sub: time, filter, FWHM, star count, SNR, verdict.
  - **frames**: links for the files by role.
  - **annotations**: catalogue objects in the final image's field from the plate solve, with position as a fraction
    of the image.
  - **processing**: the steps from FR-006.
- **020-FR-008** Anything not known is omitted from the render data, never filled with zero, an empty string or a
  guess. Only the project id and name, the target name and the final image are always present.
- **020-FR-009** Totals in the render data equal the linked SubStation projects' totals shown in the app at the same
  moment (integration counts accepted and down-weighted subs; binned subs are excluded, as on screen).
- **020-FR-010** The render data never contains site coordinates, street-level place names or anything finer than a
  latitude rounded to whole degrees. Sub times are kept (they don't reveal location).
- **020-FR-011** The owner can create, name and revoke personal API tokens in Settings. A token is shown once when
  created and stored only in hashed form; the list shows each token's name, created time and last use. Tokens can
  have an expiry date.
- **020-FR-012** A token created for rendering can only call the render API (list, read, download). It can't log in,
  change data, or call any other endpoint. Refused calls reveal nothing about projects.
- **020-FR-013** The render API offers: list finished projects (linked, with a final image) changed since a given
  time; one project's render data; and each of its files by role, plus a thumbnail. Only display-ready image formats
  (PNG, JPEG, TIFF) are offered as files.
- **020-FR-014** *(Withdrawn 2026-10-21, 020-DR-12.)* SubStation no longer writes `project.json`; the renderer reads
  the live render API.
- **020-FR-015** The render API is described by a versioned contract published in this spec
  (`contracts/render-api.openapi.yaml`) and in the app's API schema; the renderer generates its client from it.
  Changing a field's meaning or removing a field needs a new schema version; adding optional fields doesn't.
- **020-FR-016** API calls are logged (time, token name, endpoint, outcome) without logging tokens themselves.

### Key Entities

- **Finished project**: a project folder in a Completed library: kind, subject, name, path, status (linked, needs a
  final image, unlinked, not a project), updated time.
- **Finished file**: a file in a finished project's outputs, tracked by content, with an optional role (final,
  starless, stars, per-filter + filter name, progressive + order).
- **Project link**: a finished project ↔ SubStation project, with how it was suggested.
- **API token**: name, hashed secret, scope (render read), created, expires, last used, revoked.
- **Render data**: the versioned description built on request.

## Success Criteria

### Measurable Outcomes

- **020-SC-001** A new project folder with exports appears under Finished within one library scan (by default
  within 5 minutes) without the owner doing anything.
- **020-SC-002** For the owner's existing finished projects, the top suggestion is the right SubStation project in at
  least 9 out of 10 cases.
- **020-SC-003** The renderer can go from "nothing" to a project's data and final image with three calls, each
  answering in under a second for a typical project (excluding image transfer time).
- **020-SC-004** Totals in the render data match the app's Overview for every linked project (automated check).
- **020-SC-005** No render data, log line or written project.json contains coordinates finer than whole degrees
  (automated check over all fixtures).
- **020-SC-006** A revoked token is refused on its next call.

## Assumptions

- The Completed library is the existing `Completed` share (the owner's PixInsight exports already live there); it
  is added to SubStation as a library with the new role, read-only by default.
- The renderer is a separate app run by the same owner on the same network, so plain bearer tokens over the
  existing HTTPS reverse proxy are enough; no OAuth.
- Progressive stacks for the "emergence" visuals are produced by the owner's own exports for now; generating them
  from SubStation's stacks is a later spec.
- Distance, type, constellation and size come from SubStation's target catalogue data where it has it; otherwise
  they're omitted.
- Region name and Bortle class are new site fields the owner enters once per site in Settings.

## Amendment 2026-10-21: review fixes before first deploy

- **020-DR-01** Sky tracks are worked out from the target's position at each sub's time for the site rounded to whole
  degrees, never from the stored positions: real altitude and azimuth at real times, with the target's coordinates,
  would locate the site to about a kilometre. A test recovers the site from the output and checks it can't do better
  than the whole-degree site (FR-010).
- **020-DR-02** URLs in render data and the project list are root-relative (`/api/v1/render/…`), so project.json and
  the API carry the same links and nothing depends on how the reverse proxy reports the scheme.
- **020-DR-03** A project's "changed" time also moves when the linked projects' subs, grades or verdicts change, so a
  renderer polling with `since` sees regrades. It is never later than now. A time without a zone is read as UTC.
- **020-DR-04** Per-sub quality reports `fwhm_arcsec` and `fwhm_px` separately; data with no filter keeps its totals
  (the filter has no name) so totals match the app.
- **020-DR-05** Files are tagged by path, size and time (not hashed in the request); thumbnails are made safely
  (temporary file, 16-bit and float images scaled) and a file outside the project folder is never served.
- **020-DR-06** A Completed library that looks empty is treated as unreachable (a dropped share leaves an empty
  folder): the last known projects stay listed. A renamed export keeps its role. Web and social crops are never
  guessed as the final. Only display-ready outputs can be given a role.
- **020-DR-07** (2026-10-21) A master can mix data from several places (home and a remote observatory), so the render
  data lists every site, not one: `capture.sites` has one entry per site rounded to whole degrees, with an id
  (s1, s2 … by integration), subs and integration, and region and Bortle only where a library or the installation
  settings describe that same place. Every timeline row and per-sub quality entry carries its site's id, and each
  sky track is worked out from its own site. The target's name prefers a catalogue designation (IC 434 over a
  nickname); the collection's name stays the common name.
- **020-DR-08** (2026-10-21) Every graded sub's site is listed in `capture.sites`, so each quality entry names its
  site; a site whose subs were all rejected has 0 used subs. The contract says what per-sub SNR measures and that
  `nights` counts every night with subs while the timeline lists only nights with used subs.
- **020-DR-09** (2026-10-21) A project folder SubStation can't write to (the library is mounted read-write but the
  folder's own permissions refuse its user) gets a plain reason, not a server error. The install guide says how to
  give SubStation's user write access on TrueNAS.
- **020-DR-10** (2026-10-21) Whether a finished image is a mosaic comes from the linked SubStation project's kind
  (the owner's word), not from the subs' panel numbers, which capture software can set on what is really one field
  (a mosaic template, a reframe between nights). A single-field project has no `mosaic` and its timeline rows
  aren't split by panel; every panel's subs still count.
- **020-DR-11** (2026-10-21) A project's `updated_at` follows a fingerprint of everything its render data is built
  from: the folder's files, roles, links and processing; the linked projects' kind, planned panels and collection;
  the datasets in them and their counts; their subs, grades, verdicts, measurements and plate solves; and the site
  descriptions. When the fingerprint changes, `updated_at` becomes that moment; otherwise it stays put. Moving a
  dataset into a linked project or changing a project's kind therefore shows up in `since` polling, which a
  newest-timestamp rule missed.
- **020-DR-12** (2026-10-21) Writing `project.json` is withdrawn (FR-014 and User Story 5). The renderer reads only
  the live render API with its token, and a file in the folder was a stale snapshot that disagreed with it. The
  button, the route and the stored hash are gone, and SubStation never writes into a Completed library. The two files
  it had written were removed after checking each still matched the hash SubStation recorded.
- **020-DR-13** (2026-10-21) The render data's `target` carries `distance_ly` (whole light years) and
  `distance_source`. The owner types the distance on the finished project's page (source "manual"), or presses Look
  up, which asks SIMBAD for the median of the published measurements of the first of the target's designations it
  knows (catalogue numbers first). The result is stored with where it came from. A manual figure is never replaced
  by a look-up until the owner clears it. Nothing is looked up while rendering.
- **020-DR-14** (2026-10-21) Processing steps come from images, not typed labels. A new file role, Processing step,
  is guessed from export names `<name>-step-<n>-<what>` (`heart-step-2-graxpert+nxt.png`): `n` is the order and the
  rest is the label, with common tools spelled out (GraXpert, NoiseXTerminator, BlurXTerminator, StarXTerminator,
  SPCC …). The owner can change a step's order and label; a rescan never undoes that. The render data lists them as
  `frames.steps: [{order, label, url}]` (file key `step/<n>`), and `processing` becomes those labels in order. The
  typed processing list and the default steps in Settings are gone. Link suggestions now need a shared catalogue
  number or name (a shared year only ranks them), at most five. The app shows each output file as a thumbnail with
  a larger preview.
- **020-DR-16** (2026-10-22) Nightscapes and videos have no subs, so they are offered with a final image alone and
  their page has no linking or distance section; their render data has no capture data. A file whose name says the
  stars were put back (`recombined`, `recomposed`, `stars-back`) is guessed as the final, whatever else its name
  says. The page asks for the render-data preview only when there is something to build, rather than logging a
  refused request on every load.
- **020-DR-15** (2026-10-22) SubStation builds cumulative progressive stacks for a finished project: a stack after
  each night in capture order (night 1; nights 1–2; …; all), grouped into at most 12 checkpoints with date-range
  labels when there are more nights. All kept subs are registered once to one pinned reference, then each
  checkpoint stacks its prefix per channel with the same options as master builds. Every checkpoint gets one crop,
  is level-matched to the full stack, and uses the full stack's stretch, so the signal stays put and the noise
  visibly falls. Channels are combined HOO, SHO, RGB or OSC from the filters. Images are JPEGs of at most 2400 px
  in SubStation's own cache, never in the Completed library; unchanged subs reuse them. It runs as a background job
  at lower priority than master builds, from Generate on the finished project's page, and after linking when no
  sub needs calibrating again. The render data lists them as `frames.progression` (file key `progression/<n>`) with
  `frames.progression_info`; the owner's own progressive exports (`frames.progressive`) stay and take precedence.
  First version: single-field projects with one pixel scale; L is left out of LRGB; no rebuild when subs change
  until Generate is pressed again.
- **020-DR-17** (2026-10-22) Whether a finished image is a mosaic follows the linked project's kind in force: the
  owner's choice when set (020-DR-10 still holds), otherwise worked out from its panels. A linked project is never
  merged into another automatically; deleting one unlinks it with a warning.
- **020-DR-18** (2026-10-22) Progression stacks are weighted by noise, whatever master builds use: checked against
  real Siril, sharpness weighting gave the softest sub of a two-sub stack almost no weight, hiding the noise drop the
  progression is there to show. Siril's select and unselect take positions in the registered sequence (a sub that
  failed to register leaves a gap in file numbers), and a stack without the reference image still aligns.
