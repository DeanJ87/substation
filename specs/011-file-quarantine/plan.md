# Plan: Binning files (spec 011)

- **Model**: `FrameStatus.BINNED`, `FrameStatus.DELETED`; `Frame.binned_at`, `bin_reason`, `binned_by`,
  `purge_after`, `deleted_at`. `Copy.binned_from` (the path to restore to). `Library.allow_delete` (default off).
- **Service** `apps/catalogue/services/binning.py`: `bin_frames(shas, reason, user)`, `restore_frames(shas)`,
  `purge_due()`, `auto_bin()`. Moves use `os.rename` within the library (same filesystem) into
  `.substation-quarantine/<rel_path>`; the copy's `rel_path` follows. A move that fails leaves the file hidden, not
  moved, and says so.
- **Tasks**: `catalogue.tidy_bin` daily (auto-bin, then purge), queued by the supervisor's daily jobs; also
  runnable from Settings.
- **Ingest**: sweeps don't treat quarantined copies as missing; frames binned/deleted aren't marked missing.
- **Settings**: `processing.bin = {auto_bin_rejected_days: 30, purge_after_days: 30}`.
- **API**: `POST /frames/bin`, `POST /frames/restore`, `GET /bin`, `PATCH /libraries/{id}` (allow_delete),
  `POST /bin/tidy`.
- **UI**: sub page Bin/Restore; dataset Subs "Bin N rejected"; Settings → Ignored "Bin these files"; Settings →
  Library → Bin.
- **Deploy**: the library mounts become writable only when the owner sets `SUBSTATION_LIBRARY_MODE=rw` (default
  `ro`); "may delete" is a separate switch per library.
