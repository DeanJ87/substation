<!--
Sync Impact Report (2.2.0, 2026-10-17): I expanded: owner-chosen file operations (the bin, spec 011; archiving
collections, spec 013) are allowed only in libraries mounted read-write, and never change or overwrite content.
MINOR.

Earlier report (2.1.0, 2026-10-12): IV expanded with a second adapter boundary for optional external
finishing tools (spec 010). MINOR.

Earlier report:
- Version change: 1.0.0 → 2.0.0 (MAJOR: principle II redefined; VII redefined)
- Modified principles:
  - II. "Headers Are Truth, Content Is Identity" → "Content Is Identity, Metadata Is Resolved"
    (headers are the first source, not an assumption; path patterns and the user fill gaps;
    resolved values live in the database with provenance)
  - I. "Originals Are Read-Only" expanded: sources may move, be renamed, duplicated or reorganised
    outside SubStation and are tracked by content
  - VII. "Self-Hosted and Bounded" redefined: Docker Compose stack with a defined /data layout,
    real job queue for bulk ingest
- Added sections: VIII. Accounts and Access; licence (GPL-3.0) under Governance
- Removed sections: none
- Templates checked: plan-template.md, spec-template.md, tasks-template.md (read this file at runtime;
  no edit needed)
- Deferred TODOs: none
- Sources: docs/spikes/*, docs/design/*, owner feedback 2026-10-09
-->

# SubStation Constitution

SubStation watches the folders where a telescope's subs land, calibrates and grades each sub as it
arrives, and stacks datasets into masters, on the user's own hardware. It is free software under the
GNU General Public License v3.0.

## Core Principles

### I. Originals Are Read-Only

- SubStation MUST NOT modify, move, rename or delete any file in a source folder on its own initiative. Source
  mounts MUST work read-only. The only exceptions are actions the owner chooses, in a library the owner has mounted
  read-write: the bin (spec 011: quarantine, then deletion where allowed) and archiving a collection or bringing it
  back (spec 013: a verified copy to the same relative path in another library, then removal of the original). A
  file's content is never changed, and a different file is never overwritten.
- Users and other software may move, rename, copy, duplicate or reorganise source files at any time.
  SubStation MUST keep tracking them by content (Principle II) and MUST NOT treat a move as a loss.
- All derived data (catalogue, converted and calibrated frames, previews, stacks, masters) MUST live
  under SubStation's own writable area, never in source folders.
- Intermediates MUST be deletable at any time without losing user decisions; the catalogue, verdicts
  and stack recipes are the durable state.

Rationale: the user's subs are irreplaceable; "SubStation never deletes or moves your original subs".

### II. Content Is Identity, Metadata Is Resolved

- A frame's identity is the SHA-256 of its content. A cheap file fingerprint (device, inode, size,
  modification time) MAY be used to skip re-hashing unchanged files, but never to decide identity.
  Identical content under several paths is one frame with several copies. A `BAD_`-prefixed copy
  (NINA thumbs-down) is a user REJECT verdict on that frame, never a second frame. Sequence numbers
  MUST NOT be used as identifiers.
- Metadata (frame type, target, panel, filter, exposure, temperature, gain, offset, binning, camera,
  telescope, site, time) is resolved per field from sources in order: file headers, then
  user-configured folder and filename patterns, then the user. Headers are expected but not assumed:
  capture software may omit or mis-write them.
- Every resolved value MUST record its source (header, path pattern, inferred, user) and MUST be
  stored only in SubStation's database, never written back into source files. Once the user corrects
  or confirms a value, it applies to every copy of that content and future identical files.
- Disagreements between sources MUST be recorded and visible. Rules MUST prefer headers when present
  and plausible, and the user can override any value.
- The observing night MUST be computed from the resolved UTC start time and site longitude
  (date of UTC + longitude/15 h − 12 h), never from the host time zone.
- `OBJCTROT` MUST NOT be treated as the camera angle; actual orientation comes from plate solving.

Rationale: the spikes found unreliable filenames and folders, missing master headers, and NINA plus
Robocopy duplicates; the owner expects poorly behaved capture software too.

### III. Every Decision Explained

- Every sub verdict (Accepted, Down-weighted, Rejected) and every dataset or master state
  (Awaiting calibration, Integrating, Stale, Needs reconciliation) MUST carry the measurements behind
  it and a plain-English reason: the measurement, the comparison with the night median, the likely cause.
- Human verdicts (NINA thumbs-down, in-app overrides) and machine grades MUST be stored separately;
  the effective verdict is derived, and a human decision always wins.
- Re-grading MUST NOT silently change existing grades; changes require an explicit user action.
- Verdicts MUST be distinguishable by shape and glyph as well as colour, including night vision.

### IV. One Engine, One Boundary

- Image processing (conversion, calibration, star measurement, registration, stacking, plate solving)
  MUST go through Siril (pinned version, headless `siril-cli`) behind a single engine adapter.
  No other component calls Siril directly.
- The adapter MUST drive long-lived pipe-mode processes, keep one command in flight per process,
  detect completion from `status:` lines (not exit codes) and capture `log:` output per command.
- Every Siril command and flag used MUST be verified against the pinned version's `help` and the
  official documentation, and covered by an adapter test.
- Engine quirks found in the spikes MUST be encoded in the adapter (see Data and Engine Constraints).
- Optional external finishing tools for masters (GraXpert; RC-Astro's BlurXTerminator, NoiseXTerminator and
  StarXTerminator, spec 010) are not image processing in this sense. They MUST go through one separate adapter
  (`apps/processing/postprocess.py`), record their versions and parameters on every output, never modify the
  master, and be skipped with a reason when unavailable. Proprietary tools are installed and licensed by the
  admin and MUST NOT be bundled.

### V. Reconcile, Never Guess

- When a value needed for a decision cannot be resolved (Principle II), or files change in ways the
  catalogue cannot explain (content gone with no copy left, conflicting copies), the item MUST go to a
  reconciliation list with the reason and any suggestion, and the affected dataset MUST show
  "Needs reconciliation" or "Awaiting calibration" rather than proceed on a guess.
- Moves, renames and duplicates that content identity explains MUST be handled automatically and
  logged, not sent to reconciliation.
- Calibration validity is the user's decision. SubStation proposes matches by documented rules and
  shows evidence, but MUST NOT invalidate calibration frames by its own heuristics.
- Fallback rules MUST be explicit settings and visible on every result that used them.

### VI. Measured on Real Data

- Quality and performance claims MUST be backed by measurements on real captured data. Stack
  comparisons MUST use SNR, FWHM and roundness by region, never noise alone.
- Golden test fixtures MUST come from real NINA and WBPP files (subsets of the spike datasets),
  including the known traps: BAD_ duplicates, truncated readouts, failed registrations, sequence gaps,
  multi-image XISF masters, FITS row order, and files missing headers.
- Calibration frames MUST pass QA before they are used to build a master.

### VII. Self-Hosted, Queued and Bounded

- SubStation MUST ship as a Docker Compose stack runnable on a NAS or server (Unraid, Synology,
  TrueNAS, plain Linux), and MUST work fully offline; online plate solving is optional.
- The container filesystem layout is fixed and documented: everything SubStation reads or writes is
  under `/data`, with sources mounted read-only under `/data/library` (one or more) and SubStation's
  writable area at `/data/substation` (database files if embedded, work, previews, masters, stacks).
  Work storage MUST be a POSIX filesystem.
- All ingest and processing work MUST go through a persistent, prioritised job queue: live arrivals
  ahead of bulk ingests (for example 400 files after a holiday) and archive scans, resumable after a
  restart without repeating completed steps.
- Users MUST be able to ignore files and folders (by path pattern or by content); ignored content stays
  ignored wherever it reappears.
- Resource use MUST be bounded and configurable: workers, Siril memory and CPU, and a disk budget for
  intermediates.

### VIII. Accounts and Access

- The web interface and API MUST require sign-in with individual user accounts. Credentials MUST be
  stored with a modern password hash, sessions MUST be revocable, and administration of accounts MUST be
  restricted to admins.
- Two-factor authentication MUST be designed in (TOTP first) and be configurable: off, optional per
  user, or required for all users.
- Every human decision (verdicts, metadata corrections, calibration choices, deletions of SubStation
  outputs) MUST record which user made it and when.

## Data and Engine Constraints

These are verified facts from the spikes, binding on the engine adapter and catalogue.

- **Formats:** NINA lights are uncompressed XISF UInt16. WBPP masters are XISF Float32 with
  `integration`, `rejection_low` and `rejection_high`; only `integration` is used and its position MUST
  be checked. Siril `calibrate` and `calibrate_single` accept FITS only, so XISF inputs are converted
  (`load` + `save`) first.
- **Orientation:** Siril writes FITS bottom-up; XISF is top-down; Siril star lists measure Y from the
  top. Non-Siril pixel access MUST normalise orientation explicitly.
- **Sequences:** `select`/`unselect` take the 1-based position in the sequence, not the file number.
  Registered sequences keep file numbers but skip failed registrations; the adapter MUST map file number
  to position from the `.seq` `I` lines.
- **Scripts:** a script without `requires` first runs nothing yet reports success. Siril refuses to `cd`
  into read-only directories; inputs are staged. `-out=` keeps quote characters literally.
- **Defaults to override:** `core.mem_ratio` (0.9), update checks (`-o`), Python module bootstrap.
- **Inference:** dark flats are inferred from `OBJECT=FlatWizard` or exposure matching a flat set;
  the inference is visible and correctable.
- **Network shares:** change notifications are unreliable for files written by another machine; the
  watcher MUST include periodic scanning.

## Development Workflow and Quality Gates

- Work follows Spec Kit: constitution → specify → clarify → plan → tasks → implement. Specs describe what
  and why; technology choices live in plans and `docs/tech-stack-proposal.md`.
- Prefer established, maintained libraries (ORM and migrations, authentication, job queue, UI components,
  charts) over hand-written equivalents; a plan that hand-builds one MUST justify it.
- Every feature MUST have acceptance scenarios executable against the golden fixtures, plus adapter
  contract tests for each Siril command it uses.
- UI MUST use the SubStation design tokens (`--sst-*`) and design-system components, meet WCAG AA in
  dark, light and night-vision modes, and use tabular figures for numbers and timestamps.
- Copy follows the voice guide: calm, precise, British English; no exclamation marks, hype,
  "AI-powered" or "smart".
- Changes that affect stored verdicts, metadata provenance, the catalogue schema or the engine adapter
  MUST include a migration or replay plan.

## Governance

This constitution supersedes other practices for SubStation. Plans MUST include a Constitution Check
naming each principle a design touches; a violation MUST be justified in the plan's complexity tracking
or the design changed. Amendments are made by pull request that updates this file with a Sync Impact
Report, a semantic version bump (MAJOR: principle removed or redefined; MINOR: principle or section
added or materially expanded; PATCH: wording) and the dated reason. Spike reports in `docs/spikes/` are
the evidence base. All code is licensed GPL-3.0; dependencies MUST be GPL-3.0-compatible.

**Version**: 2.2.0 | **Ratified**: 2026-10-09 | **Last Amended**: 2026-10-17
