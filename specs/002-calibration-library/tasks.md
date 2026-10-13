

- [X] C28 Matching waits for nearer pending flat sets; rematch re-calibrates subs when their own night's flat arrives (002-DR-14)

## Amendment 2026-10-12: flat table

- [X] T-F1 `session_choices`: structured filter, night, days, frames, telescope, same-filter flags; every
  same-filter set (up to 40) then up to 20 others; built sets not repeated as library masters
- [X] T-F2 `CalibrationTab` ChangePanel: full-width row, flat table with hover preview (Glance), other filters
  behind a toggle
- [X] T-F3 (2026-10-12 NAS check) Blank flats that stop Siril's normalisation ("MAD is null", the A7 III's 8-bit
  21 Oct 2025 set) are blocked with a plain reason, like other near-dark flats, instead of failing with Siril's log
- [X] T-F4 (2026-10-12) A flat set's calibrator (dark flat, dark, bias) must have a file on disk; a catalogued
  master with no copy left failed the 15 Aug RGB flat builds
- [X] T-O1 (2026-10-12) `oriented_master`: masters flipped to the light's row order (ROWORDER) before
  `calibrate_single`, and the flat calibrator in master builds; tests for mono and colour planes
- [ ] T-O2 Recalibrate the 900 affected subs on the NAS; their masters go stale
- [X] T-F5 (2026-10-12) A flat set's bias or dark flat must match its offset as well as gain (ATR2600M offset 50/60)
- [X] T-O3 (2026-10-12) Temporary names use a UUID, not the PID: worker containers share PIDs, and two converting
  or flipping the same master collided (3 of 900 recalibrations failed); a cached flipped master is trusted only
  at its source's size
- [X] T-F6 (2026-10-13) A pinned match keeps what the user chose but still fills what they didn't: a flat chosen for
  a session had pinned subs with no dark, waiting forever with a blank reason (NGC 7000 Panel 2); now the dark is
  matched, or the reason says why not
- [X] T-F7 (owner 2026-10-13) Cameras that record no sensor temperature (the A7 III) use the matching-ISO master
  bias when no dark at that exposure and ISO exists (setting `calibration.bias_for_uncooled`, on), noted on the sub
- [X] T-F8 (2026-10-13) A built master with no set temperature takes its frames' median sensor temperature
  (NINA left SET-TEMP out of the 13 Feb gain-100 darks; their CCD-TEMP said −20 °C); existing masters re-catalogued
- [X] T-F9 (2026-10-13) The uncooled-camera bias fallback only uses a bias with the same layers as the light: A7 III
  subs saved as colour images can't take a raw bias (47 failed overnight with "Images must have same dimensions");
  they now wait with that reason
- [X] C29 (owner 2026-10-13) `POST /calibration-sets/{id}/filter` + "Filter…" on a flat set's page; test (002-DR-18)
- [X] C30 (owner 2026-10-13) Flat picker names link to the set; Glance says when a frame can't be drawn; scaled
  16-bit FITS (BZERO) are read without memory-mapping so unbuilt Sony flats preview (002-DR-19)
- [X] C31 (owner 2026-10-13) `format_twin` + set-aside (`apps/ingest/processed.py`); `one_row_order` before
  stacking (`calibration.py`, report `flipped`); NAS: twins set aside, affected flat masters rebuilt and their subs
  recalibrated; tests (002-DR-20, 002-DR-21)
