# Implementation Plan: Ingest and catalogue

**Branch**: `001-ingest-catalogue` | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-ingest-catalogue/spec.md`

## Summary

Build SubStation's foundation: a single-container Django + React application that watches read-only
libraries under `/data/library/*`, identifies every image by SHA-256 content (skipping unchanged files by
fingerprint), follows files through moves, renames, copies and `BAD_` thumbs-down copies, resolves
metadata per field from headers, then user path patterns, then the user (stored with its source in
SQLite, never in source files), groups lights into multi-year datasets browsable by night and
calibration frames into sets, and lists what it cannot resolve for reconciliation. All work runs through
a persistent, prioritised job queue (Django Tasks API, SubStation's SQLite backend, in-container
supervisor). No Siril is needed in this feature: cataloguing is header-only. This feature also lays down
the project skeleton every later spec uses: container, settings, accounts (sign-in), API, event stream
and UI shell with the design tokens.

## Technical Context

**Language/Version**: Python 3.12 (backend, workers); TypeScript 5.x (frontend)

**Primary Dependencies**: Django 5.2 LTS (upgrade to 6.2 LTS in 2027), Django Ninja (API, behind
`substation.api` wrapper), django-allauth headless (accounts, sessions; MFA later in spec 003), Django
Tasks API (`django-tasks` backport on 5.2), astropy (FITS headers), `xisf` (XISF headers), `parse`
(path patterns), watchdog (inotify), psutil (worker metrics), uvicorn (ASGI). Frontend: React 18,
Vite, TanStack Query/Router/Table, Radix UI, visx (later specs), openapi-typescript client.

**Storage**: SQLite (WAL, `transaction_mode=IMMEDIATE`, busy timeout) at
`/data/substation/substation.db`; files under `/data/substation/{work,previews,stacks,config}`.

**Testing**: pytest + pytest-django (unit, integration, contract), header fixtures extracted from the
real spike files, optional full golden run against the spike trees (`SUBSTATION_GOLDEN_DIR`); Vitest +
Testing Library (frontend); Playwright (end-to-end).

**Target Platform**: Linux container (amd64, arm64) under Docker Compose on any host.

**Project Type**: Web application (Django API + workers, React SPA) in one image.

**Performance Goals**: SC-001 new sub catalogued ≤10 s after the file is complete (p95), also during
bulk ingest; SC-005 400-file drop in ≤15 min; SC-006 rescan of 10,000 unchanged frames ≤2 min.

**Constraints**: libraries read-only (often SMB or NFS); `/data/substation` on local disk; no pixel reads
while cataloguing; bounded workers and memory; offline; GPL-3.0-compatible dependencies.

**Scale/Scope**: up to ~100,000 frames and ~1,000 datasets per installation; bursts of hundreds of files;
a handful of users.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this design complies | Status |
|---|---|---|
| I. Originals are read-only | Libraries mounted `:ro`; code has no write path to `/data/library`; a test hashes the golden tree before and after | Pass |
| II. Content is identity, metadata is resolved | `Frame` keyed by SHA-256; `Copy` per path with fingerprint (dev, inode, size, mtime_ns) used only to skip re-hashing; `MetadataValue` per field with source; resolution order header → path pattern → user; resolved values only in SQLite; night from UTC + longitude | Pass |
| III. Every decision explained | Classification reason, metadata source and header conflicts stored per frame and shown; NINA verdicts stored as `UserVerdict`, separate from machine grades (spec 003) | Pass |
| IV. One engine, one boundary | Not used in this feature (header-only); the engine adapter package is created empty with its contract so later specs plug in | Pass (n/a) |
| V. Reconcile, never guess | `ReconciliationItem` for unresolved fields, frames with no copies left, ambiguous masters; moves, renames and duplicates handled automatically and logged as `CopyEvent` | Pass |
| VI. Measured on real data | Header fixtures extracted from the real NINA and WBPP files; golden run reproduces spike counts (SC-002); performance checks on the owner's hardware | Pass |
| VII. Self-hosted, queued, bounded | One container; fixed `/data` layout; persistent prioritised queue in SQLite; ignore rules; configurable worker count and limits | Pass (one justified deviation, see Complexity Tracking) |
| VIII. Accounts and access | allauth headless session sign-in; admin-created accounts, signup closed; all API routes require auth; `UserVerdict`, metadata corrections, ignore rules record user and time | Pass |

Post-design re-check (after Phase 1): unchanged, all pass; deviations listed below.

## Project Structure

### Documentation (this feature)

```text
specs/001-ingest-catalogue/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── openapi.yaml     # REST API for this feature (Django Ninja)
│   ├── events.md        # Server-Sent Events stream
│   ├── path-patterns.md # Pattern grammar and precedence
│   └── container.md     # Filesystem, environment and process contract
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml
├── manage.py
├── substation/                 # Django project
│   ├── settings.py             # SQLite WAL settings, allauth, tasks backend, paths from env
│   ├── urls.py
│   ├── asgi.py
│   ├── api/                    # thin wrapper over Django Ninja: router registry, auth, errors
│   ├── tasks/                  # SubStation task backend (Django Tasks API) + supervisor + worker
│   └── events/                 # event table writer + SSE endpoint
├── apps/
│   ├── accounts/               # allauth config, admin-created users, roles
│   ├── libraries/              # Library model, mount discovery, settings (site fallback)
│   ├── catalogue/              # Frame, Copy, CopyEvent, MetadataValue, UserVerdict, Dataset, Night,
│   │                           # CalibrationSet, ReconciliationItem, IgnoreRule, PathPattern
│   ├── ingest/                 # scanner, watcher, stability check, hashing, header readers,
│   │                           # metadata resolution, classification, grouping
│   └── engine/                 # Siril adapter package (contract only in this feature)
└── tests/
    ├── unit/
    ├── integration/
    ├── contract/
    └── fixtures/headers/       # header-only extracts of real NINA/WBPP files + manifest

frontend/
├── package.json
├── src/
│   ├── api/                    # generated TypeScript client from contracts/openapi.yaml
│   ├── design/                 # substation-tokens.css, theme switch (dark, light, night vision)
│   ├── components/             # Radix-based primitives, VerdictBadge, ReadoutCard, Tabs
│   ├── features/
│   │   ├── datasets/           # dashboard list, dataset view, nights
│   │   ├── frames/             # frame list and detail (metadata with sources, copies, history)
│   │   ├── reconciliation/
│   │   ├── settings/           # libraries, path patterns, ignore rules
│   │   └── queue/              # compact queue indicator (full console in spec 005)
│   └── routes/
└── tests/

docker/
├── frontend.Dockerfile + Caddyfile   # built React app on Caddy, proxies the API
├── api.Dockerfile                    # Django API, no Siril
├── worker.Dockerfile                 # watcher + workers + Siril 1.4.2 (pinned Debian snapshot)
├── compose.example.yml               # the three services
└── entrypoint.sh                     # api or worker role
```

**Structure Decision**: Web application split into `backend/` (Django project plus apps) and `frontend/`
(Vite React app). Revised 2026-10-09 at the owner's request: three services instead of one container.
`frontend` (Caddy serving the built app and proxying the API), `api` (Django, no Siril, no library mounts)
and `worker` (the supervisor running the watcher and N workers, with Siril; the only service that mounts
libraries). They share the SQLite catalogue on `/data/substation`, so they run on one host.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Own task execution backend and supervisor (constitution: prefer libraries) | Spec 005 needs live worker scaling, separate Siril-heavy slots, per-job progress and per-process CPU/RAM, all on SQLite | Huey runs one consumer per instance with a fixed worker count; Procrastinate needs PostgreSQL; Celery/RQ need Redis; django-tasks-db has no retries or slots. The enqueue side still uses Django's standard Tasks API, so the backend is swappable |
| Own process supervisor in the worker container | Worker count changes from the UI without restarting the container or needing the Docker socket | s6/supervisord need restarts or config rewrites to change process counts; our supervisor is a small loop over subprocesses with psutil |
| Header conflict and metadata provenance tables (more schema than a flat frame table) | Constitution II requires per-field source and user corrections that outlive file moves | A flat frame table cannot keep per-field provenance or corrections across copies |
