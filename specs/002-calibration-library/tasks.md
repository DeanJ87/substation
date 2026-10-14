# Tasks: Calibration library (POC)

- [X] C1 `apps/processing` with `CalibrationMatch`; calibration settings (temperature tolerance, later-flat fallback)
- [X] C2 Matching rules with reasons and value sources; unit tests on the phase 2 cases
- [X] C3 Re-match triggers: light catalogued, master catalogued or corrected, settings changed
- [X] C4 Master FITS cache: convert a master's integration image to FITS once (engine)
- [X] C5 Build masters from raw sets (dark flats, bias, flats) with the truncated-readout check; provenance
  - `apps/processing/calibration.py`: `qa_calibration_set` (per-frame stats against the set's robust median,
    thumbnails, verdict and reason; FR-002, FR-004) and `build_master` (Siril; darks, dark flats and bias
    unnormalised; flats calibrated by the nearest master dark flat, a master dark at the same exposure, or a
    master bias, else blocked with a reason; FR-005). Built masters are catalogued under an internal disabled
    library at `MASTERS_DIR` with inferred values and the set as their source, and join matching.
  - Flat report: falloff per corner, radial profile, dust motes with an overlay preview (FR-006).
  - API: `/calibration-sets/{id}/detail|qa|build`, `/calibration-sets/build-missing`, `/calibration-qa/override`,
    thumbnails and previews. UI: `/calibration/sets/$id` contact sheet and master report.
  - Siril test: `test_masters_are_built_from_raw_calibration_frames`.
  - Darks, dark flats and bias: star-like spots (15 ADU stars; self-test with synthetic stars on each set) and
    large-scale structure (FR-003), flagged against the set's own typical values.
  - Not yet: comparing a new master with the previous one (FR-007).
- [X] C6 API: a light's match on the frame detail; "Awaiting calibration" state and note on datasets
- [X] C7 Validation on the phase 2 tree: every light matched or waiting with a reason (running on the T7 copy) — done 2026-10-10: 4,710 lights, 4,186 matched, 524 waiting, every one with a reason (missing 120 s darks at gain 100/offset 50: 145; 60 s darks at bin 1: 79; A7 III bias: 69; …), none without a match row

## Phase 2: Convergence

- [X] C8 [002-DR-02] List what blocks grading at the top of the Calibration screen: add `GET /calibration/blocking` (in `backend/apps/processing/api_calibration.py`) returning, per dataset and night with awaiting lights, "<Collection> · <Rig> · <Filter> is waiting for a <type>", the count of subs and the night, and what SubStation is looking for (type, filter, exposure, gain, temperature) from structured needs returned by `match_dark` / `match_flat` in `backend/apps/processing/matching.py`; render it first in `frontend/src/features/calibration/CalibrationLibrary.tsx`, with "Use nearest flat" (pins the nearest later flat on those lights' `CalibrationMatch`) only when the later-flat fallback applies per 002-DR-02, US1/AC2, FR-009 (missing) — partial 2026-10-10: GET /calibration/blocking and the list at the top of Calibration; "Use nearest flat" still to do (needs a per-dataset later-flat choice) — done 2026-10-10: GET /calibration/blocking and the list at the top of Calibration
- [X] C9 [002-DR-03] Replace the two tables with one masters table in `frontend/src/features/calibration/CalibrationLibrary.tsx`: columns Type, Matches, Frames, Created, Used by ("N datasets · M sessions") and State (Current, "Kept for <year> data", "Weak match for N" on evidence only, Missing, "Unused · <age>"), with tabs All, Darks, Flats and Bias showing counts; extend `MasterOut` in `backend/apps/catalogue/api_calibration.py` with frame count, created, usage counts (from `CalibrationMatch` and `SubMeasurement` dark/flat) and state per 002-DR-03, 002-DR-04, FR-012 (usage), US4/AC1 (missing)
- [X] C10 [002-DR-07] Add per-session "Change": `POST /datasets/{id}/sessions/{night}/calibration` (dark, flat, bias) in `backend/apps/processing/api.py` pins `CalibrationMatch` for that session's lights, resets their `SubMeasurement` and re-queues `calibrate_measure` (re-grading only that session, `UserVerdict` untouched); a Change dialog on each row of `frontend/src/features/dataset/CalibrationTab.tsx` per 002-DR-07 (missing)
- [X] C11 [FR-013] Stop silent re-pointing of calibrated lights: in `rematch_lights` / `update_match` (`backend/apps/processing/tasks.py`, `matching.py`) keep the match a measured light was calibrated with and record the proposed new match (new fields on `CalibrationMatch`, migration), list affected datasets on the Calibration screen and dataset Calibration tab, mark their masters Stale ("new calibration"), and re-calibrate only after an Accept action (new endpoint) per US1/AC4, FR-013 (partial) — partial 2026-10-10: calibrated subs are not re-measured silently; the dataset Calibration tab offers "Re-calibrate" for subs whose match changed (the match row itself still updates). Done 2026-10-10: the sub keeps the masters it was calibrated with (SubMeasurement.dark/flat) while the match row holds the proposal; GET /calibration/recalibration lists affected datasets on the Calibration screen; Re-calibrate on the dataset tab is the accept step and marks masters Stale
- [X] C12 [002-DR-01] Title the screen "Calibration" with the summary "<N> masters across <R> rigs from <calibration folder> · last scan <relative time>", a Rescan action (calls `POST /libraries/{id}/rescan` for calibration libraries) and a rig filter (rig of each master from camera and telescope via `ensure_rig` / `Rig` in `backend/apps/catalogue/services/library.py`), in `CalibrationLibrary.tsx` and `calibration.module.css` per 002-DR-01 (missing) — partial 2026-10-10: title, summary line and rig filter; Rescan waits on a calibration-folder role (008 T11) — done 2026-10-10: \"<N> masters across <R> rigs · <S> raw sets from <F> folders · last scan <ago>\" and Rescan (all enabled folders)
- [X] C13 [US4] Let the user retire a master or set a validity window: fields (retired, valid from, valid to) on the master (migration in `backend/apps/catalogue` or `apps/processing`), skipped by `masters()` in `backend/apps/processing/matching.py`, affected datasets marked Stale and listed, re-match on request; actions on the master detail in the calibration UI per US4/AC2, FR-013 (missing) — partial 2026-10-10: Retire on the masters table (an ignore rule recorded with who and when, undone in Settings → Ignored) with a rematch; validity windows still to do — done 2026-10-10: retire = content ignore rule (Retire button, undo in Settings → Ignored); MasterWindow (valid from/to) skipped by matching outside the window; PUT /masters/{sha}/window rematches; Window… editor in the masters table
- [X] C14 [FR-008a] Record and show the source of every value a match used: store per-value sources (exposure, gain, offset, temperature, filter, night; header, pattern, user) as JSON on `CalibrationMatch` in `backend/apps/processing/matching.py` / `models.py`, return it on `/frames/{sha256}/processing`, and show it on `frontend/src/features/sub/SubDetail.tsx` and the dataset Calibration tab per FR-008a, plan "the source of every value used" (partial) — done 2026-10-10: the sub's Calibration panel lists Matched on (exposure, gain, offset, temperature, filter, binning, time) with each value's source (header keyword, path pattern, set by you), computed from the winning metadata rather than copied onto the match
- [X] C15 [002-DR-06] Add a Bias (or dark-flat) column to `frontend/src/features/dataset/CalibrationTab.tsx`, with `bias` and `bias_note` on `SessionOut` in `backend/apps/processing/api.py` (for "flats" rigs the master bias now held in `CalibrationMatch.dark` belongs in this column, the Dark column reading "Not used: calibrated with flats and bias") per 002-DR-06 (missing) — done 2026-10-10 as a "Dark or bias" column, with "Calibrated in the camera" shown for in-camera rigs
- [X] C16 [US2/AC2] Make star contamination in darks, bias and dark flats a reject with evidence: return spot sizes and positions from `star_spots` in `backend/apps/processing/imaging.py`, give the count and typical size in the reason, save a close-up crop of the strongest spots next to the QA thumbnail in `backend/apps/processing/calibration.py`, and show it on `frontend/src/features/calibration/CalibrationSetView.tsx` (keep SC-001: 0 false rejects on the phase 2 tree) per US2/AC2 (partial) — done 2026-10-10: plainly starry darks (>25 spots, >8× the set) are rejected, fainter cases warn; close-up crop still to add
- [X] C17 [FR-010] Make calibration fallbacks user-switchable and visible: expose `temp_tolerance_c`, `later_flat_fallback` and `weak_flat_days` through the settings API in `backend/apps/libraries/api.py` (Settings UI belongs to spec 008), re-match on change, and label lights matched to a later flat "Later flat (fallback): N days after" in `match_flat` per FR-010, Constitution V (partial) — done 2026-10-10: Settings → Calibration matching (temperature tolerance, later-flat fallback) with a rematch on save
- [X] C18 [002-DR-05] Keep raw calibration sets reachable once the masters table replaces the sets table: link a built master (`BuiltMaster.frame`) to `/calibration/sets/$id` from its masters-table row and from its master detail (`frontend/src/features/frames/FrameDetail.tsx`, `CalibrationLibrary.tsx`; set id on `MasterOut`) per 002-DR-05 (partial)
- [X] C19 [002-DR-08] Flag weak flat matches on evidence only: in `match_flat` (`backend/apps/processing/matching.py`) stop marking an undated flat weak (note "Flat date not recorded" as information) and keep warn colouring in `CalibrationTab.tsx` and `SubDetail.tsx` for evidence-based weak matches only per 002-DR-08, owner amendment 2026-10-10, FR-011 (contradicts)

## Owner requests 2026-10-10 (afternoon)

- [X] C20 8-bit colour sessions take 8-bit colour flats: masters are built from colour flat sets (no bias/dark flat), matched only to 8-bit colour lights (flat only, "approximate"), and raw lights never take them
- [X] C21 Session Change offers flat sets by date (same camera and size, other filters marked), not only built masters; choosing an unbuilt set builds it at live priority and applies it when done (CalibrationMatch.pending_flat_set)
- [X] C22 Session Filter…: set the filter for every sub in a session (stored as user corrections, regrouped, rematched, re-measured)
- [X] C23 Flat thumbnails in the session table and as picture cards in Change, each opening at 100% (002-DR-09)
- [X] C24 Calibration library search, filter and date range over masters and raw sets; master thumbnails (002-DR-10)
- [X] C25 Built masters dated by their calibration set's night (002-DR-11)
- [X] C26 Shorter QA reasons; existing reasons rewritten in place (002-DR-12)
- [X] C27 Session filter change shows "Moving to …" and a link to the new dataset (002-DR-13)
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
- [X] C32 (owner 2026-10-13) `_register` uses the header's INSTRUME/TELESCOP; NAS: built masters relabelled from
  their headers (17 changed), 17 empty leftover ATR2600M datasets settled; test (002-DR-22)
- [X] C33 (2026-10-14) `auto_builds` (settled sets, grown sets, blocked flats retried after a helper master) in the
  supervisor under a lease; `RAW_TYPES`/`BUILD_PRIORITY` moved to `calibration.py`; tests (002-DR-23). The two
  new bias sets and the 15 blocked flat sets were built by hand the same day
- [X] C34 (2026-10-14) `_night` evening fallback; flat sets tolerate 5% exposure jitter; migration 0018 merges split
  flat sets; tests (002-DR-24)
- [X] D-25 (2026-10-14) `enqueue(..., fresh=True)`: joins a waiting run, queues after a running one; every re-match
  request uses it with one shared key (002-DR-25); test
- [X] D-26 (2026-10-14) Session dark choices carry `mismatch`, notes show gain/offset/temperature, fitting first;
  picker groups them and warns; `automatic: true` resets a session (002-DR-26); tests
- [X] D-27 (2026-10-14) A hand-picked flat or dark alone no longer marks a session ready: the other comes from
  matching or the session waits; a pinned match missing one goes back to waiting on a rematch (002-DR-26); tests
- [X] D-28 (2026-10-14) QA rejects darks, bias and dark flats above 20% of full scale; `flat_calibrator` skips
  built dark-flat masters that bright (002-DR-27); tests
- [X] D-29 (2026-10-14) A re-match waits for an earlier one still running (002-DR-25); test
- [X] D-30 (2026-10-14) A master with no build record (its set merged away) is measured from its file before it may
  calibrate flats (002-DR-27); test
