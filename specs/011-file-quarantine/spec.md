# Feature Specification: Binning files (quarantine and deletion)

**Feature Branch**: `poc-substation`
**Created**: 2026-10-13
**Status**: Implemented (first version)
**Input**: Owner request, 2026-10-13: a way to mark files for deletion from the UI. Marked files go to quarantine
and, after a set time, are deleted for good; rejected subs are binned automatically after a set time. The
database keeps every entry so history (frames taken, share binned, nights) can still be counted.

## Decisions (owner, 2026-10-13)

- Quarantine is a hidden folder, `.substation-quarantine/`, at the root of the file's own library: a move on the
  same disk is instant and uses no extra space; restoring moves it back to where it was.
- Every rejected sub (by the grader or by hand) is binned once it has been rejected for longer than the waiting
  period, unless it has been marked Keep. Quarantine is the window to change your mind.
- Defaults: binned 30 days after rejection; deleted 30 days after binning. Both are settings.

## User Scenarios & Testing

### User Story 1 — Bin a file by hand (P1)

From a sub's page (or a list of subs) the owner bins a file. It leaves its dataset at once, as an ignored file does,
and stacks no longer use it.

**Acceptance**:
1. **Given** a sub in a library SubStation may delete in, **When** the owner bins it, **Then** the file moves to
   `.substation-quarantine/<its path>` in that library and is listed under Settings → Library → Bin with the date it
   will be deleted.
2. **Given** a library SubStation may not delete in, **When** the owner bins a file, **Then** the file is not
   touched; it is hidden from SubStation instead, and listed as "hidden, not deleted".
3. **Given** a binned file, **When** the owner restores it, **Then** it moves back to its old path and is a sub
   again (regrouped, graded) with its old grade and measurements.

### User Story 2 — Rejected subs bin themselves (P1)

**Acceptance**:
1. **Given** a sub rejected more than 30 days ago (Settings), not marked Keep, **When** the daily tidy runs, **Then**
   it is binned, with the reason "Rejected for over 30 days: <grade reason>".
2. **Given** a binned file older than the purge period, **When** the tidy runs, **Then** its file is deleted from
   disk and the frame is recorded as deleted; SubStation's own working files for it (calibrated copy, 100% views) go
   too.

### User Story 3 — History survives (P2)

Stats count every frame ever catalogued, including binned and deleted ones: frames taken, nights, share binned.

### Edge cases

- A library mounted read-only, or not marked "SubStation may delete files here", never has a file moved or deleted:
  binning only hides. This is the default for every library.
- Quarantined files are never re-imported (folders starting with a dot are skipped) and never reported missing.
- A file with copies in several places is binned everywhere SubStation may delete; elsewhere its copies are hidden.
- Calibration frames and masters can be binned by hand; only lights are binned automatically.
- Nothing is deleted while its quarantine move or the purge date is unknown.

## Requirements

- **011-FR-01**: Frames gain two states, *binned* and *deleted*, with when, why, by whom and when it will be deleted.
  Binned and deleted frames leave their datasets; their grades, measurements and metadata stay.
- **011-FR-02**: Each library has "SubStation may delete files here" (off by default). Moving and deleting happen
  only when it is on and the library is writable; otherwise binning hides.
- **011-FR-03**: Settings → Library → Bin: the waiting period before rejected subs are binned (default 30 days; 0
  turns it off) and before binned files are deleted (default 30 days); what is in the bin, with Restore and the
  deletion date.
- **011-FR-04**: Bin from a sub's page and in bulk (a dataset's rejected subs; an ignore rule's files, e.g. the 8-bit
  captures).
- **011-FR-05**: A daily tidy bins rejected subs past the waiting period and deletes binned files past theirs.
- **011-FR-06**: Stored reasons state lasting facts ("Rejected for over 30 days: cloud").

## Success criteria

- Rejected subs older than the waiting period stop taking disk space within the purge period, with no step by hand.
- No file is moved or deleted in a library that hasn't been allowed.

## Amendment 2026-10-14: the bin has its own page

- **011-DR-07**: The bin is a page in the main menu (`/bin`): readouts (files in the bin, space in quarantine, only
  hidden, deleted so far), what the daily tidy does and a "Tidy now", and a table of binned files with a preview,
  why and by whom, when binned and when they go, filterable by reason, with a multi-select Restore. How long things
  wait and which libraries may be deleted from stay in Settings → Library → Bin, which links to the page. A binned
  file in a read-only library is only hidden, so its preview is still drawn from the file.

## Amendment 2026-10-17: a disabled switch says why

- **011-DR-08**: Settings → Library → Bin keeps "SubStation may delete files here" in view for a library mounted
  read-only, disabled, with the reason beside it and the compose setting that mounts that library read-write (spec
  013, 013-DR-02). The API refuses switching it on for a read-only library with the same reason. As in spec 013, a
  library mounted read-write is writable for the bin and for archiving alike.
- **011-DR-09** (2026-10-22) The Bin is the only way SubStation deletes the owner's files; every other put-away verb
  leaves files where they are or, for Archive, moves them (006-DR-38).
