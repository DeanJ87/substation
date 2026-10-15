# Tasks: Database backup and restore (spec 014)

- [X] K1 `substation/backup.py`: make (COPY per table, manifest, temporary name), list, prune, restore (one
  transaction, schema check, sequence reset), daily due check (FR-001..006, FR-008, FR-009)
- [X] K2 Queued jobs `backup_database` (then prune) and `restore_database` (pause, wait, restore, unpause); API at
  `/backups`: list, back up now, download, restore with confirmation; admin only (FR-007, FR-008)
- [X] K3 Supervisor enqueues the daily backup when due (FR-005)
- [X] K4 `backup` settings with defaults and validation; `BACKUP_DIR` env; install guide section (FR-006)
- [X] K5 Settings → Backups tab: schedule, keep, folder, writable warning, list, Back up now, Download, Restore with
  typed confirmation (FR-007)
- [X] K6 Tests: round trip, refused schema, prune, settings validation (SC-001, SC-002)
- [ ] K7 First real backup on the NAS after deploy; screenshot
