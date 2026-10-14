# Feature Specification: Archive collections (active and archive libraries)

**Feature Branch**: `poc-substation`
**Created**: 2026-10-14
**Status**: Proposed 2026-10-14; not built
**Input**: Owner request, 2026-10-14: keep the subs being shot and edited on fast storage, and move a collection's
files to large, slower storage once it is older or finished, from inside SubStation.

## Why

The station is moving to a fast NVMe pool (4 TB) and a large hard disk (24 TB). Editing machines reach the NAS at
2.5 Gb/s (about 280 MB/s), which the NVMe sustains and the hard disk only manages on its outer tracks, and not while
it also takes CCTV recordings and library scans. New subs and the projects in progress belong on the NVMe; finished
work on the hard disk. Moving files outside SubStation works (it tracks files by content and finds them again), but a
scan that runs mid-move can see files as missing; a move SubStation makes itself is safe and can resume.

## User scenarios

1. **Archive a finished collection.** On a collection the owner chooses Archive. SubStation shows how many files and
   how much space will move, from which library to which, then moves them. The collection, its datasets, grades,
   masters and history are unchanged; its files now live in the archive library.
2. **Bring a collection back.** The owner reshoots an archived target. Archive → Bring back moves its files to the
   active library. New subs of an archived collection are not moved automatically; the collection shows that it is
   split across libraries.
3. **Suggestions.** The Library lists collections worth archiving: no new subs for 60 days (a setting) and a current
   master. Nothing moves without the owner choosing it.
4. **Interrupted move.** The NAS restarts during a move. When the worker comes back, the move carries on; no file is
   lost, duplicated in the catalogue, or left half-copied.

## Requirements

- **FR-001** A library has a role: *active*, *archive*, or neither (today's behaviour). One active library may name
  the archive library its collections move to. Only libraries SubStation may write to (spec 011's permission) take
  part.
- **FR-002** Archive moves every present copy of the collection's frames (lights, and calibration frames used only
  by this collection) in the active library to the archive library, at the **same path relative to the library
  root**, so the owner's folder structure is kept.
- **FR-003** Each file is copied, its hash checked against the catalogue, then the copy is recorded and the original
  removed. A file whose hash does not match stays where it was and the move reports it.
- **FR-004** A file already at the destination with the same hash is not copied again; one with a different hash
  stops that file's move and is reported (never overwritten).
- **FR-005** Calibration frames used by other collections that are not archived stay in the active library; masters
  built by SubStation stay where they are (the stacks folder).
- **FR-006** The move is a queued job on the bulk queue with progress (files and bytes), shown in Activity, and it
  can be cancelled; a cancelled move leaves every file either fully moved or untouched.
- **FR-007** While a collection is moving, library scans skip its files, so none is marked missing.
- **FR-008** Bring back is the same move in the other direction.
- **FR-009** The collection page shows where its files are (active, archive, or both, with sizes). The Library can
  filter by it.
- **FR-010** Suggestions use a setting (days without new subs, default 60) and require a current master; they can be
  dismissed per collection.
- **FR-011** Nothing outside the two libraries is written; read-only libraries are never moved from or to.

## Success criteria

- **SC-001** Archiving a 100 GB collection loses no file and leaves no file in both places; the catalogue counts are
  the same before and after.
- **SC-002** A restart part-way through a move resumes and completes with the same result as an uninterrupted move.
- **SC-003** No file is reported missing by a scan during or after a move.

## Out of scope

- Automatic archiving without the owner choosing it.
- Moving files between machines, or to cloud storage (backups stay the owner's restic job).
- Compressing or converting archived files.

## Assumptions

- The two libraries are mounted in the same containers (they are bind mounts on one NAS), so a move is a copy and a
  delete, not a network transfer.
- The capture machines keep writing into the active library (NINA's Robocopy target, Seestar imports).
