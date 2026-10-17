# Tasks: Binning files (spec 011)

- [X] Q01 Model: frame states and fields, copy restore path, library switch; migration
- [X] Q02 Service: bin, restore, purge, auto-bin; tests (move, hide-only, restore, purge, auto-bin rules)
- [X] Q03 Ingest: sweeps skip quarantined copies; missing-marking skips binned/deleted frames
- [X] Q04 Tidy task, daily, and from Settings
- [X] Q05 API endpoints; tests
- [X] Q06 UI: sub page, dataset bulk, ignore rules, Settings → Library → Bin
- [X] Q07 Compose: `SUBSTATION_LIBRARY_MODE` for the library mounts (default read-only)
- [X] Q08 Stats count binned and deleted frames

Notes (2026-10-13): frames keep `binned_dataset` (the dataset they left) so Library stats still count binned and
deleted subs, with a `binned` total. Libraries report `writable`; "may delete" can only be switched on where the
mount is writable. Tests: `tests/unit/test_binning.py` (move, hide-only, restore, purge, auto-bin, API, history).
- [X] T20 (2026-10-14) `/bin` page (readouts, tidy, reason filter, multi-restore), menu item; settings section slimmed;
  glance falls back to a hidden copy (011-DR-07)
- [X] T21 (2026-10-17) The bin's delete switch disabled with the read-only reason beside it; `PATCH /libraries/{id}`
  refuses `allow_delete` on a read-only library with the reason (011-DR-08); tests
