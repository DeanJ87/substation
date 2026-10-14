---
description: "Task list for spec 001 ingest and catalogue"
---

# Tasks: Ingest and catalogue

**Input**: Design documents from `/specs/001-ingest-catalogue/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The constitution (VI, Development Workflow) requires acceptance scenarios executable
against golden fixtures and contract tests for every interface. Write each story's tests first and see
them fail.

**Organization**: grouped by user story (spec.md US1–US7) so each can be delivered and tested on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: US1–US7 from spec.md
- Paths follow plan.md: `backend/`, `frontend/`, `docker/`

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: repository, toolchains and the container skeleton.

- [X] T001 Create the directory layout from plan.md (`backend/substation/{api,tasks,events}`, `backend/apps/{accounts,libraries,catalogue,ingest,engine}`, `backend/tests/{unit,integration,contract,fixtures/headers}`, `frontend/src/{api,design,components,features,routes}`, `docker/`) with a root `README.md`, `LICENSE` (GPL-3.0 full text) and `backend/apps/engine/README.md` describing the Siril adapter interface from the constitution (pipe-mode process, one command in flight, `status:` completion, `log:` capture; no implementation in this feature)
- [X] T002 Initialise the backend with uv in `backend/pyproject.toml`: Python 3.12; dependencies Django 5.2.*, django-ninja, django-allauth[mfa], django-tasks, astropy, xisf, parse, watchdog, psutil, uvicorn; dev dependencies pytest, pytest-django, pytest-asyncio, ruff, mypy, django-stubs, pyyaml, openapi-spec-validator
- [X] T003 [P] Create the Django project (`backend/manage.py`, `backend/substation/{settings.py,urls.py,asgi.py}`) reading paths and secrets from the environment per `contracts/container.md`
- [X] T004 [P] Initialise the frontend with Vite React TypeScript (React 19, Vite 8, TypeScript pinned to 5.9 for openapi-typescript) in `frontend/package.json`: TanStack Query, TanStack Router, TanStack Table, Radix UI primitives, openapi-typescript and openapi-fetch; dev: Vitest, Testing Library, Playwright, ESLint, Prettier
- [X] T005 [P] Configure ruff, mypy (django-stubs) and pytest (`DJANGO_SETTINGS_MODULE`, markers `golden` and `slow`) in `backend/pyproject.toml`
- [X] T006 [P] Configure oxlint (the Vite template's linter, replacing ESLint), Prettier and Vitest in `frontend/` (`.oxlintrc.json`, `.prettierrc`, `vite.config.ts` test block)
- [X] T007 [P] Write the images (revised: three services): `docker/worker.Dockerfile` (Debian forky pinned to a snapshot.debian.org date, `siril=1.4.2-1*`, Python 3.12 via uv), `docker/api.Dockerfile` (Python slim, no Siril), `docker/frontend.Dockerfile` + `docker/Caddyfile` (built React app on Caddy proxying the API); non-root uid 1000
- [X] T008 [P] Write `docker/entrypoint.sh` (refuses to start if `/data/substation` is missing or not writable; warns if it is a network filesystem; `api` role runs migrations, bootstrap admin and uvicorn; `worker` role waits for the schema then runs `supervise --no-web`) and `docker/compose.example.yml` with the three services, as in `contracts/container.md`
- [X] T009 [P] Add CI workflow `.github/workflows/ci.yml`: ruff, mypy, pytest (non-golden), frontend lint and tests, image build for amd64 and arm64

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: database, accounts, API wrapper, queue, supervisor, events, base models, header readers and
the UI shell. No user story can start until this phase is done.

### Database and settings

- [X] T010 Configure SQLite in `backend/substation/settings.py`: database at `/data/substation/substation.db`, `OPTIONS = {"transaction_mode": "IMMEDIATE", "timeout": 20, "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;"}`, `ATOMIC_REQUESTS = False` (research R1)
- [X] T011 [P] Write a test in `backend/tests/integration/test_sqlite_concurrency.py` that runs 8 processes each writing 500 short transactions concurrently and asserts no "database is locked" errors

### Accounts (constitution VIII, research R11)

- [X] T012 Configure django-allauth headless in `backend/apps/accounts/`: `HEADLESS_ONLY = True`, `HEADLESS_CLIENTS = ("browser",)`, `ACCOUNT_LOGIN_METHODS = {"username", "email"}`, an account adapter whose `is_open_for_signup` returns False, and roles via Django groups `admin` and `standard`
- [X] T013 Implement bootstrap admin creation from `SUBSTATION_ADMIN_USERNAME` / `SUBSTATION_ADMIN_PASSWORD` when no users exist in `backend/apps/accounts/management/commands/bootstrap_admin.py`
- [X] T014 [P] Test in `backend/tests/integration/test_auth.py`: API returns 401 without a session; sign-in through `/_allauth/browser/v1/auth/login` works; signup is refused; a standard user gets 403 on admin endpoints

### API wrapper (keeps Django Ninja swappable)

- [X] T015 Create `backend/substation/api/__init__.py` exposing `register_router(prefix, router)`, a session-auth dependency, an `admin_required` guard, cursor pagination helpers and an error handler returning `{code, message}` per `contracts/openapi.yaml`; no app module imports Django Ninja directly except through this package
- [X] T016 [P] Implement `GET /api/v1/health` (database, libraries, worker heartbeat status) in `backend/substation/api/health.py`
- [X] T017 [P] Contract test that the generated OpenAPI schema covers every path and schema in `specs/001-ingest-catalogue/contracts/openapi.yaml` in `backend/tests/contract/test_openapi_contract.py`

### Queue and supervisor (research R2, R3)

- [X] T018 Create `Task`, `Worker` and `ResourceSample` models in `backend/substation/tasks/models.py` with fields exactly as data-model.md: Task `priority` int "-100..100", `slot` enum `light`/`siril_heavy`, `status` enum `ready`/`running`/`succeeded`/`failed`/`cancelled`, `dedupe_key` "text unique nullable", `run_after`, `heartbeat_at`, `progress` "float, nullable 0–1"; indexes on (status, priority, enqueued_at)
- [X] T019 Implement a Django Tasks API backend in `backend/substation/tasks/backend.py` (`enqueue` writes a `Task` row; honours `priority` and `queue_name`; `dedupe_key` collisions return the existing task) and set it as the default in settings
- [X] T020 Implement atomic claim in `backend/substation/tasks/claim.py`: one IMMEDIATE transaction running `UPDATE … WHERE id = (SELECT id … WHERE status='ready' AND run_after<=now AND slot has capacity ORDER BY priority DESC, enqueued_at LIMIT 1) RETURNING …` (SQLite ≥ 3.35)
- [X] T021 Implement the worker loop in `backend/substation/tasks/worker.py`: claim, run, heartbeat every 5 s, record progress, retry with exponential backoff up to `max_attempts`, mark `failed` with error text, sample CPU and RSS with psutil every 2 s into `ResourceSample`
- [X] T022 Implement recovery in `backend/substation/tasks/recovery.py`: tasks `running` with heartbeat older than 30 s go back to `ready` with attempts + 1; prune `ResourceSample` older than 15 min
- [X] T023 Implement `substation supervise` in `backend/substation/tasks/management/commands/supervise.py`: start uvicorn, the watcher and N workers (`SUBSTATION_WORKERS`, default 2); restart crashed children with backoff; re-read the worker count from settings every 5 s and scale up or down (surplus workers finish their current task then exit); forward signals for clean shutdown
- [X] T024 [P] Tests in `backend/tests/integration/test_queue.py`: priority order; dedupe; retry with backoff; dead-worker recovery; scaling 2 → 4 → 1 workers loses and duplicates no task; a restart re-queues running tasks

### Events (research R12, contracts/events.md)

- [X] T025 Create the `Event` model and `emit(type, payload)` helper in `backend/substation/events/models.py` and `backend/substation/events/emit.py` (id autoincrement, pruned after 24 h)
- [X] T026 Implement `GET /api/v1/events` as an async Server-Sent Events view in `backend/substation/events/views.py`: 500 ms polling of `Event`, `Last-Event-ID` resume, 15 s heartbeat comments, `resync` when the id was pruned
- [X] T027 [P] Test SSE resume, heartbeat and resync in `backend/tests/integration/test_events.py`

### Base catalogue models (data-model.md)

- [X] T028 Create the `Library` model in `backend/apps/libraries/models.py` (name unique, mount_path, enabled, site_name/site_lat/site_lon nullable, status enum `ok`/`unreachable`/`scanning`, last_full_sweep_at, sweep_interval_active_s default 60, sweep_interval_idle_s default 900) plus a singleton `InstallationSettings` (site_name, site_lat, site_lon nullable; filter_aliases JSON; seeded from `SUBSTATION_SITE_NAME`/`_LAT`/`_LON`) with an admin endpoint `GET/PATCH /settings`, and discovery of subdirectories of `/data/library` at start-up in `backend/apps/libraries/discovery.py`
- [X] T029 Create `Frame`, `Copy`, `CopyEvent` and `HeaderSnapshot` in `backend/apps/catalogue/models/frames.py` exactly as data-model.md: Frame `sha256` "char(64) PK", `frame_type` enum (`light`, `flat`, `dark`, `dark_flat`, `bias`, `master_dark`, `master_flat`, `master_bias`, `master_dark_flat`, `unknown`), `status` enum `catalogued`/`missing`/`ignored`/`error`, resolved fields and indexes (dataset, date_obs_utc), (night), (frame_type, filter_norm, exptime_s), (status); Copy unique (library, rel_path) with fingerprint fields st_dev, st_ino, st_size, st_mtime_ns
- [X] T030 Create `MetadataValue`, `ContentCorrection` and `HeaderConflict` in `backend/apps/catalogue/models/metadata.py`: MetadataValue `source` enum `header`/`folder_pattern`/`filename_pattern`/`inferred`/`settings`/`user`, unique (frame, field, source, source_detail), `is_winner`
- [X] T031 Create `Night`, `Dataset`, `DatasetNight` and `CalibrationSet` (type, filter_norm, exptime_s, gain, offset, xbin, ybin, set_temp_c, session_start_utc, session_end_utc, night, frame_count, filter_blocks JSON) in `backend/apps/catalogue/models/grouping.py`: Dataset unique on (target, panel, filter_norm, camera, telescope, xbin, ybin, gain, offset), `state` enum `ok`/`needs_reconciliation`/`awaiting_calibration`/`integrating`/`stale`; Night unique (site_key, date)
- [X] T032 Create `UserVerdict` and `ReconciliationItem` in `backend/apps/catalogue/models/decisions.py`: UserVerdict `source` enum `nina_bad_prefix`/`override`; ReconciliationItem `kind` enum `missing_field`/`frame_missing`/`master_metadata`/`ambiguous_master`/`classification_unknown`/`bad_without_twin`, `status` enum `open`/`resolved`/`dismissed`
- [X] T033 Generate and check in the initial migrations for all apps in `backend/apps/*/migrations/` and `backend/substation/*/migrations/`

### Header readers and fixtures (research R7, R13)

- [X] T034 Write `backend/tests/fixtures/make_header_fixtures.py`: given a spike tree path, extract real files' headers verbatim into tiny files (FITS: the header plus a 2×2 array; XISF: the XML header with a minimal attachment, multi-image layout preserved) and write `manifest.json` recording the source path and original SHA-256 of each
- [X] T035 Generate and commit the fixture set in `backend/tests/fixtures/headers/`: NINA lights (09-28 and 10-07), BAD_ twin pairs and the twinless BAD_, WBPP master dark, flat and bias (three images), raw flats, FlatWizard dark flats, the truncated dark flat header, AppleDouble `._x.xisf`, a FITS light, a tile-compressed `.fz` copy of it generated with astropy `CompImageHDU` (synthetic, real header), and lights with FILTER and EXPTIME stripped
- [X] T036 Implement header readers in `backend/apps/ingest/headers.py`: `read_header(path) -> HeaderResult` for FITS (`astropy.io.fits.getheader`, including `.fz`) and XISF (`xisf` metadata only; images with id, geometry, sample format, keywords, properties); never read pixel data; return a parse error instead of raising
- [X] T037 [P] Unit tests for the readers against every fixture in `backend/tests/unit/test_headers.py`, including a guard that fails if pixel data is read (patch the array readers)

### UI shell

- [X] T038 Copy `docs/design/design-system/substation-tokens.css` into `frontend/src/design/` and implement the theme switch (dark, light, night vision; N toggles; stored per user in localStorage) in `frontend/src/design/theme.ts`
- [X] T039 [P] Implement design-system primitives on Radix in `frontend/src/components/`: Button (outlined), Tabs (accent underline), ReadoutCard (mono figures, tabular-nums), Label, Table wrapper, EmptyState, ErrorState (voice guide)
- [X] T040 [P] Implement `VerdictBadge` with the seven shapes, glyphs and tokens from the design guidelines section 07 in `frontend/src/components/VerdictBadge.tsx`
- [X] T041 Generate the typed client from `specs/001-ingest-catalogue/contracts/openapi.yaml` into `frontend/src/api/schema.d.ts` with an npm script `api:gen`, and a client wrapper with session cookie and CSRF handling in `frontend/src/api/client.ts`
- [X] T042 Implement sign-in, sign-out and the app frame (header with lockup, nav Datasets · Review · Calibration · Settings, queue indicator slot, "watching …" status) in `frontend/src/routes/` using the allauth headless browser endpoints
- [X] T043 Implement the SSE client hook with resume and resync in `frontend/src/api/events.ts`

**Checkpoint**: the container starts, an admin signs in to an empty shell, workers run tasks, events stream.

---

## Phase 3: User Story 1 - New subs appear as they land (Priority: P1) 🎯 MVP

**Goal**: lights written into a library appear within 10 s under the right dataset and night with header
values.

**Independent Test**: replay one spike night into `/data/library/capture` at capture pace; every sub is
catalogued ≤10 s after completion and grouped as in the spike reports (quickstart V3, V4, V5).

### Tests for User Story 1

- [X] T044 [P] [US1] Unit tests for night computation (UTC + longitude/15 h − 12 h; 2026-10-07 lights after midnight stay on 2026-10-07; missing longitude uses library then installation site) in `backend/tests/unit/test_night.py`
- [X] T045 [P] [US1] Unit tests for OBJECT target/panel parsing (`NGC 7000 Panel 3` → NGC 7000, 3; no panel) and dataset key building in `backend/tests/unit/test_grouping.py`
- [X] T046 [P] [US1] Integration test: files appearing in a temporary library are catalogued; a file growing in chunks is not catalogued until stable; AppleDouble and `.DS_Store` are skipped, in `backend/tests/integration/test_live_ingest.py`
- [X] T047 [P] [US1] Contract tests for `GET /datasets`, `GET /datasets/{id}`, `GET /frames`, `GET /frames/{sha256}`, `GET /libraries` in `backend/tests/contract/test_catalogue_api.py`

### Implementation for User Story 1

- [X] T048 [US1] Implement the path check in `backend/apps/ingest/pathcheck.py` (research R4): skip `._*`, `.DS_Store` and non-image extensions (`.fit`, `.fits`, `.fts`, `.fz`, `.xisf` accepted, case-insensitive); compare fingerprint with the `Copy`; unchanged → update `last_seen_at`; else enqueue `ingest.hash` with `dedupe_key = hash:<library>:<rel_path>:<mtime_ns>` and priority 80 if mtime is within 15 min, else 40
- [X] T049 [US1] Implement the watcher in `backend/apps/ingest/watcher.py` as a leased singleton (a `Lease` row `watcher` with holder and 15 s expiry, renewed every 5 s; only the holder watches, another worker container takes over when it lapses, so `compose --scale worker=N` is safe): watchdog observers on enabled libraries (closed-write and move events) feeding the path check; scheduled sweeps per library at the active or idle interval; a library whose mount is empty or erroring is marked `unreachable` and its sweep aborted
- [X] T050 [US1] Implement the sweep in `backend/apps/ingest/sweep.py`: `os.scandir` walk using cached stat data, the path check per file, progress events (`library.status`), and a completed-sweep marker per library
- [X] T051 [US1] Implement the `ingest.hash` task in `backend/apps/ingest/tasks/hash.py`: stability check (size and mtime unchanged across 2 s, else reschedule +2 s, give up after 5 min with "file kept changing"), streamed SHA-256 in 8 MiB chunks, upsert `Frame` and `Copy`, emit `CopyEvent(discovered)`, enqueue `ingest.catalogue` for new content
- [X] T052 [US1] Implement the `ingest.catalogue` task in `backend/apps/ingest/tasks/catalogue.py`: read headers, store `HeaderSnapshot` rows, write header `MetadataValue` rows, resolve winners (header-only resolution in this story), set resolved fields, classify, compute the night, assign dataset or calibration set, update `DatasetNight` counts, emit `frame.catalogued` and `dataset.updated`
- [X] T053 [US1] Implement header field extraction and normalisation in `backend/apps/ingest/fields.py`: keyword maps for NINA, WBPP and common FITS (OBJECT; FILTER; EXPTIME/EXPOSURE; CCD-TEMP; SET-TEMP; GAIN; OFFSET; XBINNING/YBINNING; INSTRUME; TELESCOP; DATE-OBS; SITELAT/SITELONG or LAT-OBS/LONG-OBS); filter normalisation (strip, case-fold, aliases from settings); numeric parsing
- [X] T054 [US1] Implement light classification in `backend/apps/ingest/classify.py` from IMAGETYP variants and XISF imageType (research R9), storing `classification_reason` text
- [X] T055 [US1] Implement night and dataset assignment in `backend/apps/catalogue/services/grouping.py` (research R10) with `Dataset.display_name` such as "NGC 7000 · Panel 3 · Hα" and maintained sub_count, integration_s, first_utc, last_utc
- [X] T056 [US1] Implement API routers for libraries, datasets and frames (read-only) in `backend/apps/catalogue/api.py` and `backend/apps/libraries/api.py` per `contracts/openapi.yaml`, registered through `substation.api`
- [X] T057 [US1] Implement the Datasets dashboard in `frontend/src/features/datasets/DatasetsDashboard.tsx`: readout cards (subs catalogued tonight, integration, queue, free disk), dataset rows (target, description, filters, integration, counts, state badge, note) per design screen 9a, live updates via SSE, and the empty state "No subs yet. SubStation is watching <folder>…"
- [X] T058 [US1] Implement the dataset view (header line with night, subs × exposure, gain, temperature; frames table with time, file, filter, exposure, temperature, user verdict) in `frontend/src/features/datasets/DatasetView.tsx` and the frame detail drawer (headers per image, values) in `frontend/src/features/frames/FrameDetail.tsx`
- [X] T059 [US1] Write the replay tool in `backend/scripts/replay.py` (copies files from a source tree into a target folder in DATE-OBS order with `--speedup` and `--chunked` slow-writer mode) for quickstart V3 and V4

**Checkpoint**: US1 works alone: live subs appear in the dashboard and dataset view within 10 s.

---

## Phase 4: User Story 2 - Files are known by content wherever they go (Priority: P1)

**Goal**: one frame per content; moves, renames, copies, BAD_ thumbs-down, deletions and replacements
handled without losing decisions.

**Independent Test**: quickstart V2 (BAD_ folding counts), V6 (moves and renames), V7 (missing content),
V8 (replaced content), V9 (no re-hashing).

### Tests for User Story 2

- [X] T060 [P] [US2] Integration tests in `backend/tests/integration/test_content_tracking.py`: BAD_ twin → one frame with a `UserVerdict(source=nina_bad_prefix)`; twinless BAD_ → one frame with REJECT and a `bad_without_twin` informational item; plain duplicate → one frame, two copies; folder move and rename → copies updated, `CopyEvent(moved)`, no reconciliation; all copies deleted → frame `missing` only after one further complete sweep and a `frame_missing` item; reappearance clears it; same path with new content → new frame and `CopyEvent(replaced)`; unreachable library marks nothing missing
- [X] T061 [P] [US2] Integration test that a rescan of an unchanged library enqueues no hash tasks, and that a same-inode file at a new path is recorded as moved without hashing, in `backend/tests/integration/test_fingerprint.py`

### Implementation for User Story 2

- [X] T062 [US2] Extend the path check in `backend/apps/ingest/pathcheck.py`: a fingerprint (st_dev, st_ino, st_size, st_mtime_ns) known at another path of the same library is a move of the same unchanged file object → update the `Copy` path and emit `CopyEvent(moved)` and `copy.moved` without hashing
- [X] T063 [US2] Extend `ingest.hash` in `backend/apps/ingest/tasks/hash.py`: content already known → new `Copy` on the existing frame; classify the event as `copied`, or `moved` if a copy of that frame went missing in the current or previous sweep; same path with a different digest → detach the old copy (`CopyEvent(replaced)`) and continue as new content
- [X] T064 [US2] Implement BAD_ handling in `backend/apps/catalogue/services/verdicts.py`: a copy whose name starts with `BAD_` sets `is_bad_prefixed` and creates one `UserVerdict(verdict=reject, source=nina_bad_prefix, copy=…)` per frame (idempotent); a frame whose only copies are BAD_ gets a `bad_without_twin` item
- [X] T065 [US2] Implement end-of-sweep reconciliation of disappearances in `backend/apps/ingest/sweep.py`: copies not seen in a complete sweep of a reachable library → `present=False`, `missing_since`, `CopyEvent(missing)`; frames with no present copies after one further complete sweep → `status=missing` and a `frame_missing` item (dataset → `needs_reconciliation`); a reappearing copy restores the frame and resolves the item
- [X] T066 [US2] Implement dataset state maintenance in `backend/apps/catalogue/services/state.py`: `needs_reconciliation` while any open item references a frame in the dataset, with `state_reason` such as "7 files are missing from disk. Review before stacking."
- [X] T067 [US2] Show copies, user verdicts and movement history on the frame detail in `frontend/src/features/frames/FrameDetail.tsx`, and NINA rejects in dataset tables with the Rejected badge and "Rejected by you in NINA"

**Checkpoint**: US1 and US2 work together; golden counts match the spike reports.

---

## Phase 5: User Story 3 - Metadata is resolved even from poorly behaved software (Priority: P1)

**Goal**: headers first, then user path patterns, then the user; every value with its source; corrections
apply by content.

**Independent Test**: quickstart V10 (20 stripped lights: reconciliation without patterns; "from filename
pattern" with the NINA pattern; one bulk correction resolves the rest).

### Tests for User Story 3

- [X] T068 [P] [US3] Unit tests for the pattern grammar in `contracts/path-patterns.md` (every token, typed converters, `{*}` and `**`, BAD_ stripping, NINA filename and folder examples) in `backend/tests/unit/test_patterns.py`
- [X] T069 [P] [US3] Unit tests for resolution precedence (user > prefer_over_header pattern > header > pattern > inferred > settings) and conflict recording in `backend/tests/unit/test_resolution.py`
- [X] T070 [P] [US3] Integration test for the V10 scenario in `backend/tests/integration/test_metadata_resolution.py`
- [X] T071 [P] [US3] Contract tests for `/path-patterns`, `/path-patterns/preview`, `/frames/metadata`, `/frames/classification`, `/reconciliation` in `backend/tests/contract/test_metadata_api.py`

### Implementation for User Story 3

- [X] T072 [P] [US3] Create the `PathPattern` model with its migration in `backend/apps/catalogue/models/patterns.py` (library nullable, scope_glob, kind enum `folder`/`filename`, pattern, prefer_over_header JSON list of fields, priority int, enabled, created_by, created_at)
- [X] T073 [US3] Implement the pattern compiler and matcher (a small regex compiler: `parse` cannot express `**` or folder-bounded captures; see the module docstring) in `backend/apps/ingest/patterns.py` per `contracts/path-patterns.md` (validation errors in plain English)
- [X] T074 [US3] Implement the resolver in `backend/apps/ingest/resolve.py`: gather candidate values per field from header, matching patterns (most specific scope, then priority), inference and settings; apply `ContentCorrection`; pick winners by precedence; record `HeaderConflict`; open `missing_field` items for required fields with no value (lights: target, filter, exptime, date_obs; calibration frames: exptime and type-specific fields), with a suggestion where one exists
- [X] T075 [US3] Wire the resolver into `ingest.catalogue` (replacing header-only resolution) in `backend/apps/ingest/tasks/catalogue.py`, and add `ingest.reresolve` (re-resolve and regroup frames matched by a changed pattern, in batches of 500) in `backend/apps/ingest/tasks/reresolve.py`
- [X] T076 [US3] Implement user corrections in `backend/apps/catalogue/services/corrections.py`: write `ContentCorrection` and user `MetadataValue` rows (user and time) for any field including `frame_type` (classification overrides use this same path, constitution VIII), re-resolve and regroup in the same transaction per frame, close matching `missing_field` items, emit `frame.updated` and `dataset.updated`
- [X] T077 [US3] Implement API routers for path patterns (CRUD, preview), bulk metadata, classification override (stored via the T076 corrections service as a user `MetadataValue` for `frame_type` plus a `ContentCorrection`, recording user and time; `Frame.classification_source` becomes `user`) and reconciliation (list, resolve with `apply_to_similar`, dismiss) in `backend/apps/catalogue/api_metadata.py` per `contracts/openapi.yaml`
- [X] T078 [US3] Show each value's source on the frame detail ("from header FILTER", "from filename pattern #3", "set by admin on 9 Oct") and conflicts, plus a "Change type" action showing the classification reason, in `frontend/src/features/frames/FrameDetail.tsx`
- [X] T079 [US3] Implement the reconciliation screen (grouped by kind and reason, bulk resolve, accept suggestion, dismiss) in `frontend/src/features/reconciliation/ReconciliationList.tsx`
- [X] T080 [US3] Implement the path pattern editor with live preview on sample paths in `frontend/src/features/settings/PathPatterns.tsx`
- [X] T081 [US3] Implement multi-select bulk metadata editing (all resolvable fields including frame type) in the frames table in `frontend/src/features/frames/BulkEdit.tsx`
- [X] T082 [US3] Write `backend/scripts/strip_headers.py` (copies files with chosen keywords removed) for quickstart V10

**Checkpoint**: frames with missing or wrong headers can be fixed without touching files.

---

## Phase 6: User Story 4 - Bulk arrivals and outside changes are queued (Priority: P1)

**Goal**: hundreds of files, or changes made while SubStation was off, are processed through the queue
without delaying live subs.

**Independent Test**: quickstart V11 (stop, add 400 files, start, replay live subs; live ≤10 s; bulk ≤15 min;
restart mid-queue resumes).

### Tests for User Story 4

- [X] T083 [P] [US4] Integration test: 400 queued hash tasks at priority 40 and live files at 80 → live files finish first; restart mid-run resumes without re-hashing finished files, in `backend/tests/integration/test_bulk_ingest.py`
- [X] T084 [P] [US4] Contract test for `GET /queue/summary` and `queue.changed` events in `backend/tests/contract/test_queue_api.py`

### Implementation for User Story 4

- [X] T085 [US4] (Done by the leased watcher, T049: taking the lease sweeps every library at once.) Run a full sweep of every enabled library on start-up (priority 10 for archive sweeps; files found then are classified live or bulk by mtime) in `backend/apps/ingest/startup.py`
- [X] T086 [US4] Implement `GET /api/v1/queue/summary` (ready by priority class, running, failed in the last hour, ETA from recent throughput) in `backend/substation/tasks/api.py`, and emit throttled `queue.changed` events (at most every 2 s) from the worker loop
- [X] T087 [US4] Implement the compact queue indicator ("Queue 412 · about 6 min") linking to a placeholder queue page in `frontend/src/features/queue/QueueIndicator.tsx`

**Checkpoint**: P1 stories complete: this is the POC ingest slice.

---

## Phase 7: User Story 5 - The user ignores what should not be processed (Priority: P2)

**Goal**: ignore folders, globs and content; ignored content stays ignored anywhere; undo re-queues.

**Independent Test**: quickstart V12.

- [X] T088 [P] [US5] Integration test for ignore rules (folder, glob, content follows the content to a new path; undo queues files) in `backend/tests/integration/test_ignore.py`
- [X] T089 [P] [US5] Create the `IgnoreRule` model (kind enum `folder`/`glob`/`content`, library nullable, value, note, created_by, created_at, active) with its migration in `backend/apps/catalogue/models/ignore.py`
- [X] T090 [US5] Apply folder and glob rules in the path check and content rules in `ingest.hash` (frame → `ignored`) in `backend/apps/ingest/pathcheck.py` and `backend/apps/ingest/tasks/hash.py`; undo re-queues matching files
- [X] T091 [US5] Implement `/ignore-rules` endpoints in `backend/apps/catalogue/api_ignore.py` and the Ignored list with undo, plus "Ignore" actions on frames and folders, in `frontend/src/features/settings/IgnoreRules.tsx`

---

## Phase 8: User Story 6 - Calibration frames and masters are recognised (Priority: P2)

**Goal**: flats, darks, dark flats, bias and masters (including WBPP multi-image XISF) catalogued and grouped
into sets.

**Independent Test**: on the phase 2 tree, 6 flat sets of about 50, 3 dark-flat sets (2 s ×150, 1 s ×50,
0.01 s ×50) and 36 WBPP masters (quickstart V2).

- [X] T092 [P] [US6] Integration tests: FlatWizard darks → `dark_flat` with reason; WBPP master → `integration_index` set and only the integration image's headers used; a multi-image XISF without an `integration` image → `ambiguous_master` item; session splitting at 2 h and merging when a frame bridges two sessions, in `backend/tests/integration/test_calibration_catalogue.py`
- [X] T093 [P] [US6] Implement calibration-set queries (list by type and night with frame counts, filter blocks and member frames) in `backend/apps/catalogue/services/calibration_queries.py` (the `CalibrationSet` model is created in T031)
- [X] T094 [US6] Extend classification for calibration frames and masters (FlatWizard and flat-exposure rule for dark flats; `Master …` IMAGETYP and XISF `integration` id; `integration_index`) in `backend/apps/ingest/classify.py`
- [X] T095 [US6] Implement incremental calibration set maintenance with session clustering in `backend/apps/catalogue/services/calibration_sets.py`; whenever a flat set is created or grows, re-check darks on the same night with the same exposure, gain, offset and binning and re-classify them as dark flats (reason "exposure matches the Hα flat set on 28 Sep"), unless the user has overridden their type
- [X] T096 [US6] Open `master_metadata` items for masters missing gain, offset, CCD-TEMP or SET-TEMP, with path-derived suggestions (for example `-20c` → set_temp −20), in `backend/apps/ingest/resolve.py`
- [X] T097 [US6] Implement `/calibration-sets` and `/masters` endpoints in `backend/apps/catalogue/api_calibration.py` and the Calibration library list screen (sets and masters with metadata sources) in `frontend/src/features/calibration/CalibrationLibrary.tsx`

---

## Phase 9: User Story 7 - Datasets span years and are browsable by night (Priority: P2)

**Goal**: a dataset collects any number of nights; each night can be opened on its own.

**Independent Test**: quickstart V13 (phase 1 and 2 NGC 7000 data: nights listed per panel, each browsable).

- [X] T098 [P] [US7] Contract tests for `/datasets/{id}/nights` and `/nights/{date}` in `backend/tests/contract/test_nights_api.py`
- [X] T099 [US7] Implement the nights endpoints in `backend/apps/catalogue/api_nights.py`
- [X] T100 [US7] Add a nights list with per-night counts and integration, and a night filter on the dataset view, in `frontend/src/features/datasets/DatasetNights.tsx`
- [X] T101 [US7] Implement a Night page listing every dataset and calibration set catalogued that night in `frontend/src/features/datasets/NightView.tsx`

---

## Phase 10: Polish and cross-cutting concerns

- [X] T102 [P] Read-only guarantee test (quickstart V1): hash every file in a fixture library before and after a full ingest, and assert there is no write-mode `open` on `/data/library` paths (runtime guard in tests), in `backend/tests/integration/test_read_only.py`
- [X] T103 [P] Golden test suite `-m golden` against `SUBSTATION_GOLDEN_DIR` comparing frame, dataset, set, BAD_ and reconciliation counts with docs/spikes phase 2 in `backend/tests/golden/test_golden_counts.py`
- [X] T104 [P] Performance checks for SC-001, SC-005 and SC-006 (replay timing, 400-file drop, 10,000-frame unchanged rescan) in `backend/tests/golden/test_performance.py`, marked `slow`
- [X] T105 [P] Playwright end-to-end: sign in, see the dashboard update during a replay, fix a stripped file via reconciliation, in `frontend/tests/e2e/ingest.spec.ts`
- [X] T106 [P] Accessibility checks (axe) on all screens in dark, light and night vision in `frontend/tests/e2e/a11y.spec.ts`
- [X] T107 [P] Copy review of every user-facing string against the voice guide in `frontend/src/` and `backend/apps/*/messages.py`
- [X] T108 [P] User docs (MkDocs Material with `docs/design/design-system/mkdocs/stylesheets/substation.css`): install with Compose, the `/data` layout, path patterns, reconciliation, in `docs/user/`
- [X] T109 Run every quickstart.md scenario on the owner's live session and record results in `specs/001-ingest-catalogue/validation.md`

---

## Dependencies and execution order

### Phase dependencies

- **Setup (1)** → **Foundational (2)** → user stories.
- **US1 (3)** depends on Foundational.
- **US2 (4)** depends on US1 (path check, hash and catalogue tasks).
- **US3 (5)** depends on US1 (catalogue task); independent of US2.
- **US4 (6)** depends on US1; independent of US2 and US3.
- **US5 (7)** depends on US1 and US2 (content rules follow content).
- **US6 (8)** depends on US1 (and US3 for master metadata suggestions).
- **US7 (9)** depends on US1.
- **Polish (10)** after the stories it checks.

### Within each story

Tests first (fail) → models → services and tasks → API → UI.

### Parallel opportunities

- Setup: T003–T009 in parallel after T001–T002.
- Foundational: accounts (T012–T014), API wrapper (T015–T017), queue (T018–T024), events (T025–T027),
  headers and fixtures (T034–T037) and the UI shell (T038–T043) are independent tracks once settings
  (T010) and models (T028–T033) exist.
- After US1: US2, US3, US4, US6 and US7 can proceed in parallel by different people.

## Parallel example: User Story 1

```text
T044 test_night.py   |  T045 test_grouping.py  |  T046 test_live_ingest.py  |  T047 test_catalogue_api.py
then T048 → T049 → T050 (watcher and sweep) alongside T053, T054 (fields, classify)
then T051 → T052 → T055 → T056, then T057 and T058 (UI) in parallel, T059 any time
```

## Implementation strategy

1. **MVP**: Phases 1–3 (US1). Demo: live subs from the owner's session appearing in the dashboard.
2. **POC ingest slice**: add US2, US3 and US4 (all P1). This is the spec 001 part of the POC in
   docs/tech-stack-proposal.md.
3. **Complete 001**: US5, US6, US7, then Polish and the live-session validation (T109).

## Phase 11: Convergence

- [X] T110 [001-DR-01] Replace the Library's readouts and lists with the first-run state until the first light is catalogued, in `frontend/src/features/library/Library.tsx` and `library.module.css`: "No subs yet", every watched lights folder path in mono (`/data/library/<name>` from `GET /libraries`), "New FITS or XISF files will appear here within a few seconds of landing.", and the actions "Change watched folders" (Settings → Folders) and "Import an existing archive" per 001-DR-01, FR-018 (partial)
- [X] T111 [001-DR-03] Reach reconciliation from where the problem shows: remove the "N to reconcile" header link from `frontend/src/routes/AppFrame.tsx`; make "Needs reconciliation" badges and notices on Library cards (`features/library/Library.tsx`), collection rows (`CollectionView.tsx`) and the dataset header (`features/dataset/DatasetScreen.tsx`) link to `/reconcile`, filtered to that dataset (add a `dataset` filter to `GET /reconciliation` in `backend/apps/catalogue/api_metadata.py` and to `ReconciliationList.tsx`) per 001-DR-03, FR-014 (partial) — done 2026-10-10: Library notice replaces the header link
- [X] T112 [001-DR-02] Rework the header folder indicator in `frontend/src/routes/AppFrame.tsx` and `frame.module.css`: "Watching N folders" in mono with an `--sst-ok` dot when every library is reachable; a different colour and shape when any is unreachable or scanning; folder-by-folder status in a popover reachable by hover and keyboard focus (not only a `title`) per 001-DR-02 (partial)
- [X] T113 [001-DR-04] Tag every sub-detail value with its real source: in `frame_processing` (`backend/apps/processing/api.py`) take Capture fields (camera, gain, offset, filter, telescope, temperatures, exposure) from the resolved values and their sources (`value_sources` in `backend/apps/catalogue/services/calibration_queries.py`) as Header, Pattern or User instead of the hard-coded "header"; Measured stays SubStation and plate-solve values Solve per 001-DR-04, FR-008 (partial) — done 2026-10-10 for resolved values (camera, gain, sensor temperature, filter, telescope); keyword-only conditions stay Header
- [X] T114 [001-DR-08] List each session's recorded conditions with their source on the Subs tab session header: add per-condition source and cloud periods to `SessionOut.conditions` in `backend/apps/processing/api.py`, render them in `frontend/src/features/dataset/SubsTab.tsx` (`conditionsText` in `DatasetScreen.tsx`), omitting what isn't recorded per 001-DR-08 (partial) — partial: session lines list SQM, ambient, humidity, guiding RMS and cloud when recorded; sources and cloud periods still to do — done 2026-10-10: SessionOut.condition_sources (header keyword per condition, or file name for guiding) shown on each session header of the Subs tab; cloud periods are shaded on the Quality chart (G14)
- [ ] T117 [SC-001] Finish validation: repeat the † scenarios (V3 live arrivals, V11 bulk drop) on the owner's NAS during a live NINA session and V13 with a two-session dataset, recording results in `specs/001-ingest-catalogue/validation.md` per SC-001, SC-005, US7/AC1 (partial)
- [X] T118 Classification rule for calibration frames saved as Light (001-DR-09); the 30 A7 III 180 s darks re-resolved and their master queued
- [X] T119 Reconcile groups explain themselves (001-DR-10): group key and example (type, place, header values, needs, size, nights) on `GET /reconciliation`, ignored files left out; group card with type, folder, chips, need line, glance thumbnail with close look, "Ignore this folder" / "Ignore files like this" (optimistic, toast); tests in test_metadata_resolution.py and describe.test.ts
- [X] T120 FrameType "processed" from PixInsight signatures and HISTORY; NAS also ignores */calibrated, */registered, */debayered, */approved (001-DR-11)
- [X] T121 (owner 2026-10-13) 8-bit captures of any type set aside by a content ignore rule at catalogue time
  (`apps/ingest/processed.py`); existing ones set aside once on the NAS; test in `tests/unit/test_processed_copies.py`
- [X] T122 (owner 2026-10-13) Site values out of the repo: compose variables, prepare-script variables, helper URL
  required, spike reports and e2e defaults without local paths
- [X] T123 (2026-10-13) Regrouping a frame whose dataset was removed during a long re-read no longer fails
  (`assign_dataset` looks the old dataset up); test
- [X] T123 (2026-10-14) `rms_from_name` ignores the frame number after an empty `_RMS_`; NINA's lights pattern on the
  rig set to carry `RMS$$RMSARCSEC$$`, and its dark, bias and flat patterns to file into `_CalibrationFrames`
- [X] T124 (2026-10-14) `hash_file` re-checks path rules before reading; test
