# Tasks: Plate solving

Verified against the code on 10 October 2026: no solver exists yet. Open items name the files to touch and
the requirement they close.

## Phase 1: Existing groundwork (built)

- [X] P1 Header-pointing centre (median RA/DEC of up to 15 lights) used for suggestions; the fallback this spec replaces [009-DR-01, fallback]
  - `backend/apps/catalogue/services/library.py` `centre`, `separation`, `suggest`

## Phase 2: Governance and image

- [X] P2 Owner decision: amend constitution IV to allow ASTAP for plate solving behind its own adapter [009-DR-01] — resolved 2026-10-10: owner chose Siril's solver; no amendment needed
  - `.specify/memory/constitution.md` (owner), see plan Complexity tracking
- [X] P3 Worker image: ASTAP CLI and D05 database pinned by version and SHA-256 per architecture; optional D50 mount documented [009-DR-01] — replaced 2026-10-10: Siril's local KStars catalogues on the T7 (SHA-1 verified) mounted read-only at ~/.local/share/kstars in the worker
  - `docker/worker.Dockerfile`, `docker/compose.example.yml`, `docs/user/install.md`

## Phase 3: Engine and model

- [X] P4 ASTAP adapter: run with hint, radius, FOV, downsample, output to the work dir, timeout; parse `.ini`/WCS into centre, rotation, scale, field; map failures to reasons [009-DR-01, 009-DR-02] — done 2026-10-10 as the Siril solver (apps/processing/solving.py): load, `platesolve -force -downscale`, parse centre, rotation, scale and field
  - new `backend/apps/engine/astap.py`; `backend/apps/engine/README.md`
- [X] P5 Adapter tests: parse fixtures for solved and failed output; live solve of a real NGC 7000 sub when ASTAP is installed (skipped otherwise) [009-DR-01] — done 2026-10-10: tests/processing/test_solving.py on Siril 1.4.2's real output; live solves of M 31, M 33, Heart and M 81 subs in 0.3–0.4 s
  - new `backend/tests/engine/test_astap.py`, fixtures under `backend/tests/fixtures/astap/`
- [X] P6 `PlateSolve` model (state, centre, rotation, scale, field, offsets, solver, version, duration, time, hint used, reason) [009-DR-02] — done 2026-10-10: PlateSolve (state, centre, rotation, scale, field, solver, seconds, reason)
  - `backend/apps/processing/models.py` + migration
- [X] P7 Plate solving settings and availability probe ("ASTAP not found" turns solving off) [009-DR-01, edge case] — done 2026-10-10: solving is on when all four local catalogues are present; Settings says how to install them otherwise
  - `backend/apps/processing/config.py` `DEFAULTS["plate_solving"]`; `backend/apps/libraries/api.py` `SettingsOut.plate_solving_available`

## Phase 4: Jobs

- [X] P8 `solve_light` task after `calibrate_measure`, header fallback or unsolved per setting, logged reason, `frame.solved` event [009-DR-01] — done 2026-10-10: solve_light queued after each measurement; failure reason in plain English
  - `backend/apps/processing/tasks.py`; `backend/substation/events` (event name)
- [X] P9 Low-priority backfill job and management command, labelled "Solving" in Activity [009-DR-04] — done 2026-10-10: backfill_solves at low priority, labelled Solving in Activity, and a button in Settings
  - `backend/apps/processing/tasks.py` `solve_backfill`; new `backend/apps/processing/management/commands/solve_backfill.py`; `backend/substation/tasks/activity.py` (job type label)

## Phase 5: Framing and use

- [X] P10 Dataset and collection framing, offsets from the reference framing, field overlap on the tangent plane [009-DR-02, 009-DR-03]
  - new `backend/apps/catalogue/services/framing.py`; new `backend/tests/unit/test_framing.py`
- [X] P11 Suggestions and "Add datasets" ranking use solved centre distance, rotation difference and overlap, and say so in the note [009-DR-03, 006 FR-003] — done 2026-10-10: candidates rank by coverage of the reference field, then offset; note gives offset, rotation (mod 180°) and coverage
  - `backend/apps/catalogue/services/library.py` `suggest`, `rank_candidates` (006 L16)
- [X] P12 Framing API and overlays on collection cards and the Overview with field size, scale and overlap legend [006-DR-09] — done 2026-10-10 on the Overview (GET /collections/{id}/framing, SVG north up east left, legend table); card thumbnails keep the preview image
  - `backend/apps/catalogue/api_library.py` `GET /collections/{id}/framing`; new `frontend/src/features/library/Framing.tsx`; `Library.tsx`, `CollectionView.tsx` (006 L22)
- [X] P13 Settings → Plate solving: enabled, solver path, database path, header hint, on failure, radius, downsample, status line [008-DR-01, 009-DR-01] — done 2026-10-10: Settings → Plate solving (status, counts, backfill)
  - new `frontend/src/features/settings/PlateSolving.tsx` (`id="plate-solving"`); `SettingsPage.tsx`
- [X] P14 Sub detail "Plate solve" section with source tag "ASTAP · 1.4 s" and time, or the failure reason [009-DR-02, G40] — done 2026-10-10: sub detail Plate solve section, source "Siril · 0.3 s"
  - `backend/apps/processing/api.py` `frame_processing` sections

## Phase 6: Contract and validation

- [X] P15 Regenerate the client contract and the reference copy
  - `frontend/src/api/openapi.json`, `schema.d.ts`; `specs/001-ingest-catalogue/contracts/openapi.yaml`
- [X] P16 Validation on the phase 2 NGC 7000 panels (T7 copy): each centre within 2′ of its header pointing; the collection draws three overlapping fields [US1 independent test] — done 2026-10-10, criterion revised: the headers' RA/DEC drift by up to 0.9° within a session (mount pointing, not synced), while solves agree to a median 0.5–1′ within each dataset (cloudy subs aside). NGC 7000 (collection 2) draws as a four-panel mosaic: neighbouring panels overlap 16–41%, panel 1 Hα and OIII overlap 94% (6′ apart). Failed solves were all subs with 1–189 stars (cloud); their reason now says so

## Owner requests 2026-10-10 (afternoon)

- [X] P17 Framing shows each dataset's image (its best sub's preview) placed by that sub's own solve; corners checked against the WCS Siril writes, for mirrored and unmirrored solves (PlateSolve.flipped)
- [X] P18 Choose the dataset shown (click a row or Show), the reference (offsets and overlap), or All images; collections with panels default to All, so a mosaic assembles
- [X] P19 A dataset's outline averages its rotation on the doubled circle with the dataset's mirroring, so meridian flips (180°) don't scramble it
- [X] P20 Top-down captures (DSLR FITS, ROWORDER TOP-DOWN): Siril solves the calibrated copy upside down relative to the raw (mirrored, 180° − θ). PlateSolve.source records the file solved; framing flips such previews top-to-bottom. Found from the owner's Heart Nebula A7 III (Fish Head appeared east of the Heart); representative subs re-solved 2026-10-10

## Amendment 2026-10-12: annotations

- [X] A1 Vendor Siril 1.4.2 annotation catalogues to `backend/apps/processing/annotation_catalogues/` (not `data/`: the repo ignores every `data/` folder, which kept them out of the first build)
- [X] A2 `apps/processing/annotations.py`: catalogue load (Messier wins over its NGC alias), gnomonic projection,
  placement on the displayed preview from the solve's corners; large objects reaching into the field
- [X] A3 `GET /frames/{sha}/annotations`, `GET /stacks/{id}/annotations`
- [X] A4 Frontend `components/Annotations.tsx`: overlay, toggle, remembered switch; sub page and 100% view
- [X] A5 Fix sub-degree field parsing (`_span`) + test; migration 0012 drops misread solves
- [X] A6 Checked by drawing on real previews: M31 (M32, M110, NGC 206, ν And), Heart (IC 1805, NGC 1027)
- [X] A7 (2026-10-12) A master's annotations and framing follow the master file's own row order, not the dataset's
  first sub (M81 Hα mixes top-down NINA FITS with XISF: labels were upside down, M82 named in empty sky)
- [X] A8 (owner 2026-10-13) Masters are solved with SIP distortion (`platesolve … -order=3`) and keep the full
  WCS; labels are placed through it (`astropy.wcs`), not the centre-rotation-scale summary that drifted a few
  arcminutes towards the edges (NGC 3077 on M81); labels of close neighbours step apart instead of overprinting
- [X] P20 (owner 2026-10-13) `_master_image` for framing; masters drawn last; test (009-DR-10)
- [X] P21 (2026-10-14) `PlateSolve.wcs`; `solve_light` stores it for solves from the calibrated file; migration 0014
  (009-DR-11)
