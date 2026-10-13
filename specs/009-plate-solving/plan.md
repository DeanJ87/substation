# Plan: Plate solving

Every light is solved locally with the ASTAP command-line solver in the worker image, using the header
pointing as a hint. Solves are stored per light, aggregated per dataset, and feed spec 006's suggestions,
"Add datasets" ranking and framing overlays. Nothing is built yet; the header-pointing centre in
`apps/catalogue/services/library.py` (`centre`) is the fallback this replaces.

## Technical context

- Worker image `docker/worker.Dockerfile`: Debian forky pinned by digest, apt pinned to a
  snapshot.debian.org date, `siril=1.4.2-1*`. ASTAP is not in Debian, so the same discipline is applied by
  hand: an exact ASTAP CLI release and star database fetched by URL with `ARG`s for version and SHA-256,
  verified with `sha256sum -c`, per architecture (`TARGETARCH` amd64 / arm64).
- Engine boundary: `backend/apps/engine/` (`siril.py` is the only Siril caller; `README.md` documents the
  adapter). Adapter tests in `backend/tests/engine/`.
- Pipeline: `apps/processing/tasks.py` `calibrate_measure(sha256)` (process queue) calibrates and measures a
  light and leaves the calibrated FITS in the work cache; grading follows. Tasks use `station_task` /
  `enqueue` with priorities `PRIORITY_LIVE` and `PRIORITY_BULK`.
- Settings: `processing` JSON on `InstallationSettings`, merged over `apps/processing/config.py` `DEFAULTS`.
- Sub detail sections come from the server (`GET /frames/{sha}/processing` `sections`), so the
  "Plate solve" section is a backend change plus no new frontend layout.

## Design

- **Install** (009-DR-01): in `worker.Dockerfile`, after the Siril layer, download
  `astap_command-line_version_Linux_<arch>.zip` (pinned `ASTAP_VERSION`, `ASTAP_SHA256_AMD64`,
  `ASTAP_SHA256_ARM64`) to `/opt/astap/astap_cli`, and the D05 star database (small, fields from about
  0.6°) to `/opt/astap/db`. A denser database (D50) can be mounted at `/data/substation/astap` and selected
  with the database path setting. Exact URLs, sizes and checksums are confirmed when the task runs, against
  the pinned release's `-h` output (constitution IV, "verified against the pinned version").
- **Adapter** (`apps/engine/astap.py`): `solve(path, hint) -> SolveResult` runs
  `astap_cli -f <fits> -o <work>/<sha> -d <db> -r <radius> -fov <deg> -ra <h> -spd <dec+90> -z <downsample>
  -wcs`, with a timeout. It reads `<work>/<sha>.ini` (`PLTSOLVD`, `CRVAL1/2`, `CD1_1..CD2_2`, `CROTA2`,
  `WARNING`/`ERROR` lines) and derives centre, rotation (signed, east of north), pixel scale and field size
  from the CD matrix and image size. Output goes to the work directory, never beside the original
  (constitution I). The input is the calibrated FITS from the cache (ASTAP does not read XISF); a light
  without one is solved after `calibrate_measure`. Failure reasons map ASTAP messages to the voice guide
  ("Too few stars (cloud): 12 detected, 30 needed.").
- **Model** `apps/processing/models.py` `PlateSolve` (one per frame): state (`solved`, `header`,
  `failed`, `off`), `ra_deg`, `dec_deg`, `rotation_deg`, `scale_arcsec_px`, `field_w_deg`, `field_h_deg`,
  `offset_arcmin` and `rotation_offset_deg` from the dataset's reference framing, `solver`,
  `solver_version`, `duration_s`, `solved_at`, `hint_used`, `reason`.
- **Settings** (`config.py` `DEFAULTS["plate_solving"]`): `enabled`, `astap_path`, `database_path`,
  `use_header_hint`, `on_failure` (`header` or `unsolved`), `search_radius_deg`, `downsample`. Availability
  is probed once per worker start (`astap_cli -h`, version string) and reported through `/settings` as
  `plate_solving_available`; when missing, solving is off and Settings says so.
- **Tasks**: `solve_light(sha256)` (process queue, after `calibrate_measure` succeeds, live priority) and
  `solve_backfill()` (bulk priority minus 20, enqueues `solve_light` for lights without a solve in chunks;
  started when solving is switched on and by `manage.py solve_backfill`). Both appear in Activity with the
  verb "Solving" (009-DR-04). Each solve emits `frame.solved`.
- **Framing** (`apps/catalogue/services/framing.py`): a dataset's framing is the median solved centre,
  rotation and field of its lights; a collection's reference framing is its reference dataset (006 L15).
  Overlap is the area of intersection of two fields projected on the tangent plane at the reference centre
  (rotated rectangles, clipped with Sutherland–Hodgman; no new dependency), as a share of the smaller field.
- **Use in spec 006** (009-DR-03): `suggest` and `rank_candidates` prefer solved centres, rotation
  difference and overlap, and say so ("Centre 6′ away, 88% overlap (plate solved)."); they fall back to
  header pointing and name it ("from headers").
- **Framing API**: `GET /collections/{id}/framing` returns each dataset's field corners in the reference
  preview's pixel space plus field size, scale and overlap, for the overlays (006-DR-09).
- **Sub detail** (009-DR-02): a "Plate solve" section: centre ("20h 58m 47s +44° 19′ 52″"), rotation
  ("+5.1°"), scale ("1.58″/px"), field ("2.71° × 1.81°"), offset from reference ("3′ 12″"), source tag
  "ASTAP · 1.4 s" and time, or the failure reason.

## Constitution check

- **IV (One engine, one boundary)** says plate solving MUST go through Siril. ASTAP is a second engine. See
  Complexity tracking; the adapter keeps the boundary rule (one module, one caller, adapter tests).
- I: ASTAP output is written to the work directory, never next to an original. Pass.
- V: a fallback to the header position is an explicit setting and is shown on every solve that used it. Pass.
- VII: fully offline (local database); backfill is a bounded, low-priority queued job. Pass.

## Project structure

```text
docker/worker.Dockerfile                       ASTAP CLI + D05 database, pinned with checksums
docker/compose.example.yml                     optional /data/substation/astap note
backend/apps/engine/astap.py, README.md        adapter
backend/apps/processing/models.py, migrations  PlateSolve
backend/apps/processing/config.py, tasks.py    settings, solve_light, solve_backfill
backend/apps/processing/management/commands/   solve_backfill
backend/apps/catalogue/services/framing.py     framing and overlap
backend/apps/catalogue/services/library.py     suggestions use solves
backend/apps/catalogue/api_library.py          /collections/{id}/framing
backend/apps/processing/api.py                 Plate solve section
backend/tests/engine/test_astap.py, tests/unit/test_framing.py
frontend/src/features/settings/PlateSolving.tsx, features/library/Framing.tsx
docs/user/install.md                           solver and databases
```

## Complexity tracking

| Violation | Why needed | Simpler alternative rejected because |
|---|---|---|
| ASTAP beside Siril, against constitution IV's "plate solving MUST go through Siril" | Spec 009 names ASTAP: fast (about 1–2 s a sub), fully offline with a small database, robust with a header hint | Siril 1.4 `platesolve` needs large local catalogues or an online service for its own solver, or a local astrometry.net install, which is heavier than ASTAP. Owner to amend principle IV to "Siril, and ASTAP for plate solving, each behind one adapter" before P3 lands |
