# Feature Specification: Database backup and restore

**Feature Branch**: `poc-substation`
**Created**: 2026-10-15
**Status**: Built 2026-10-15
**Input**: Owner request, 2026-10-15: back up SubStation's database to a folder of the owner's choosing as a
.tar.gz, and restore from one. Backing up the image files themselves is out of scope (the owner already keeps
off-site copies of them).

## Why

Everything SubStation has learnt about the files (grades, calibration matches, pinned choices, masters and their
history, collections, rigs, settings, users) lives only in its database. The files can be re-scanned; the decisions
can't. A daily backup in a folder the owner can mount anywhere, plus a restore that can't half-apply, makes that
work safe to lose a disk over.

## User scenarios

1. **Nightly backup.** With nothing set up, SubStation writes one backup a day at 03:30 into its own station folder
   and keeps the newest 14. Settings → Backups changes the time, how many are kept, and the folder.
2. **Somewhere else.** The owner mounts another disk into the containers (for example `/backups`) and sets the
   folder to it. If SubStation can't write there, the page says so and the day's backup fails once, on Activity.
3. **Back up now.** Before a risky change the owner presses Back up now; the list shows the new backup when done.
4. **Download.** Any backup downloads from the page as its .tar.gz.
5. **Restore.** The owner chooses Restore on a backup and types "restore" to confirm. New work pauses, running jobs
   finish, the database is replaced in one transaction, and work resumes. A backup made by a different version of
   SubStation is refused with a plain reason naming the version that made it.

## Requirements

- **FR-001** A backup is one `.tar.gz` holding a CSV of every table and a `manifest.json` (format, time made,
  SubStation version, schema migrations, rows per table). It needs no database client tools.
- **FR-002** Work in flight, live events, sign-in sessions and the migration ledger are not saved or replaced.
- **FR-003** All tables are read at one consistent moment.
- **FR-004** A backup appears in the folder only when complete (written under a temporary name, then renamed).
- **FR-005** Daily at the set time if switched on; one attempt a day; then older backups beyond "keep" are deleted.
- **FR-006** Settings: on/off (default on), time HH:MM (default 03:30), keep 1–365 (default 14), folder (empty =
  the station's `backups` folder, or `BACKUP_DIR`; otherwise an absolute path inside the containers).
- **FR-007** The page lists backups newest first with time, file name and size; shows the folder and whether it can
  be written; offers Back up now, Download and Restore. Admins only.
- **FR-008** Restore requires typing "restore"; pauses the queue, waits for running jobs, applies all-or-nothing,
  carries every id sequence on past the restored rows, then unpauses.
- **FR-009** Restore refuses a backup whose schema differs from the running SubStation's, saying which side is newer.

## Out of scope

Backing up image files or masters on disk; off-site copies; encryption (the folder's own storage handles these).

## Success criteria

- **SC-001** A backup restored into an empty database gives back identical rows (test).
- **SC-002** A backup from another schema is refused without changing anything (test).
