# Feature Specification: Archive collections (active and archive libraries)

**Feature Branch**: `poc-substation`
**Created**: 2026-10-14
**Status**: Proposed 2026-10-14; built 2026-10-17 (see the amendment)
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

## Amendment 2026-10-17: built; which libraries may take part

The station's storage is now in place: a fast NVMe share is where the capture machines' new deep-sky subs land,
and the existing organised library on the hard disks (later moving to the large disk) holds finished work. In
SubStation the NVMe share is the *active* library and the organised library its *archive*. A further existing
library stays as it is, with no role.

- **013-DR-01 Writable means writable for everything.** A library mounted read-write is writable for every file
  operation SubStation makes: archiving to it, bringing collections back from it, and the bin's permanent deleting
  (where Settings also allows that, spec 011). A library mounted read-only can do none of them. FR-001's and FR-011's
  "only libraries SubStation may write to" means mounted read-write; there is no separate per-library switch for
  archiving.
- **013-DR-02 Disabled controls say why.** A control that can't be used because its library is read-only stays in
  view, disabled, with the reason beside it and the setting that changes it ("Mounted read-only. Mount it
  read-write (SUBSTATION_LIBRARY_2_MODE=rw) to allow this."). The containers learn which compose slot each library
  is from `SUBSTATION_LIBRARY_NAMES`; a library mounted by an override file gets a generic reason.
- **013-DR-03 Per-library mount modes.** The reference compose file has three library slots, each with its own
  mode: `SUBSTATION_LIBRARY_MODE` (the first), `SUBSTATION_LIBRARY_2_MODE` and `SUBSTATION_LIBRARY_3_MODE`, the
  last two defaulting to the first's so existing installs are unchanged. An unset slot mounts its own empty hidden
  folder (`.no-library`, `.no-library-3`), since two mounts at one path clash.
- **013-DR-04 Roles.** Settings → Library → Folders sets each library's role (active, archive, neither) and an active
  library's archive. Only a read-write library takes a role; an archive library that loses its role is cleared as
  any active library's archive. Several active libraries may each name an archive.
- **013-DR-05 The move.** A move is one job on the bulk priority (`ingest.move_collection`), with a row per file
  copy. Its files are chosen when it first runs. Each file is copied beside its destination under a hidden name,
  read back and checked against its catalogue hash, linked into place (never replacing a file that appeared there
  meanwhile), recorded as the frame's copy in the destination, then removed from the source. A failure on one file
  is recorded against that file and the move carries on. A restart resumes from the files not yet done; a file
  already at the destination with the same hash is not copied again. Cancel stops between chunks and removes the
  hidden copy, so the file being copied stays untouched.
- **013-DR-06 Calibration.** Archiving moves the calibration frames the collection's lights use (the masters matched
  to them, what built those masters, and the raw frames of their sets) unless lights still in the active library,
  of any other collection or none, use them too. Bringing back moves every calibration frame the collection uses
  that is in the archive. Masters SubStation built live in its own folder and never move.
- **013-DR-07 Where a collection is.** The collection's Overview shows its files by library (active, archive, both,
  with sizes), the move under way or the last one (progress, files left where they were and why, Cancel), and
  Archive or Bring back with a confirm step naming the file count, bytes, source and destination. The Library's
  collections can be filtered by where their files are, or to those worth archiving, and cards say "Archived",
  "Partly archived" or "Worth archiving".
- **013-DR-08 Suggestions.** A collection is worth archiving when it has files in an active library that has an
  archive, its newest sub was shot more than the set number of days ago (Settings → Library → Folders, default 60,
  0 turns suggestions off), it has a current master, and no move of it is waiting or running. "Not now" dismisses
  it until a newer sub is shot.
- **013-DR-09 Undo.** Archive and Bring back are recorded as changes (spec 016). Undoing one that hasn't started
  cancels it; undoing one under way or finished queues the move back, which waits for the first to stop.
- **013-DR-10 Who.** Read-only accounts can't archive, bring back, cancel a move or dismiss a suggestion; library
  roles are for admins.
- **013-DR-11** (2026-10-22) A project's Done state (006-DR-36) is not archiving: it moves no files. Archiving stays a
  whole-collection action.
