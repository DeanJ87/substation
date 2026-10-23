# Implementation Plan: Finished projects and the render read API

**Branch**: `poc-substation` | **Date**: 2026-10-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/020-finished-projects-api/spec.md`, including amendments 020-DR-01..20,
which supersede earlier text (FR-006 typed processing steps by DR-14; FR-014 and Story 5 by DR-12; the
"progressive stacks are a later spec" assumption by DR-15).

**Note**: retrospective. The feature is built and deployed; this plan records the design as built, taken from the
code. Where the code and the spec differ, the difference is listed in [research.md](research.md#open-questions)
rather than resolved here.

## Summary

A library with the Completed role holds the owner's hand-finished work, one folder per project
(`<Astro|Nightscapes|Videos>/<subject>/<name>/{exports,web,social,project}`). SubStation scans it stat-only, records
each folder as a `FinishedProject` with its output files and their guessed roles (final, starless, stars,
per-filter, progressive, processing step), and lets the owner link an astro project to the catalogue projects whose
subs made it. A separate renderer app reads the result over a small bearer-token API (`/api/v1/render/...`): a list
of offered projects changed since a time, one project's render data (schema version 1, built on request from the
catalogue), and its files by role with ETags. Render data never carries a site finer than whole degrees. SubStation
also builds cumulative progressive stacks (one per night or group of nights) with Siril in a queued background job,
stored in its own cache. The contract is [contracts/render-api.openapi.yaml](contracts/render-api.openapi.yaml).

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript ~5.9 (frontend)

**Primary Dependencies**: Django 5.2, django-ninja (routers, schemas, `HttpBearer`), django-tasks (the station
queue), astropy (alt/az tracks via `apps/processing/sky.py`), numpy (progression planes, level matching), Pillow
(thumbnails, previews, progression JPEGs), Siril 1.4.2 headless behind `apps/engine/siril.py` (registration and
stacking for progressions); React 19, Vite 8, TanStack Router and Query, openapi-typescript for the generated client.
SIMBAD TAP over HTTPS for the distance look-up only, on the owner's request (stdlib `urllib`, no new dependency).

**Storage**: PostgreSQL (`apps/finished` models; migrations 0001..0004). Completed library mounted under
`/data/library/...`, read-only by default (a fourth optional library slot in compose). Thumbnails and previews under
`STATION_ROOT/cache/finished/`, progression JPEGs under `STATION_ROOT/cache/progression/fp<id>/`, both in
SubStation's writable area and safe to delete.

**Testing**: pytest (`backend/tests/integration/test_finished_render.py`, `backend/tests/unit/test_progression_plan.py`,
`test_progression_task.py` with mocked Siril; `backend/tests/engine/test_progression_siril.py` marked `siril`, run in
the worker image); vitest (`frontend/src/features/finished/Finished.test.tsx`, `settings/ApiTokens.test.tsx`);
Playwright + axe (`frontend/tests/e2e/a11y.spec.ts` covers `/finished` and a project page); CI checks the exported
OpenAPI matches the code.

**Target Platform**: Docker Compose stack on a NAS or Linux server; web UI in current browsers; the renderer is
another app on the same network calling through the existing HTTPS reverse proxy.

**Project Type**: web application (Django API + React SPA + worker with Siril).

**Performance Goals**: a new project folder appears within one scan, at most 5 minutes (`SCAN_MAX_AGE_S = 300`,
SC-001); each render API call answers in under a second for a typical project, excluding image transfer (SC-003).

**Constraints**: scans are stat-only (no hashing of 60 MP TIFFs in a request); file ETags come from path, size and
time; thumbnails 640 px, app previews 1600 px; progression images at most 2400 px, at most 12 checkpoints; the
progression job runs in the `siril_heavy` slot at `PRIORITY_BULK` (below master builds at `PRIORITY_BULK + 5`); an
automatic start is skipped when more than 30% of the subs would need calibrating again.

**Scale/Scope**: tens of finished projects, each with up to tens of output files; one or a few render tokens; one
renderer polling with `since`.

## Constitution Check

*Gate re-checked after design: passes; no violations to track.*

| Principle | Touched by | Status |
|---|---|---|
| I. Originals are read-only | The Completed library is only read: `scan.py` walks with `os.scandir`/`stat`, the render API opens files read-only and refuses any path outside the project folder. SubStation never writes into it (FR-001, DR-12: `project.json` withdrawn). Thumbnails, previews and progression images live in `STATION_ROOT/cache/`, deletable at any time; durable state is the links, roles, labels and distance in the database. | Pass |
| II. Content is identity, metadata is resolved | Finished projects are keyed by folder path, files by path within it; a renamed export keeps its role by matching size and time (DR-06). Subs used for render data and progressions are catalogue frames identified by SHA-256 as everywhere else. Files are *not* content-hashed (see research, open question Q1). | Pass, with an open question |
| III. Every decision explained | `offered()` returns the reason a project is not offered ("not linked", "needs a final image", "its folder is missing"); not-a-project folders carry a reason; link suggestions carry reasons ("same target (IC 1805)", "same name", "same year"); progression `unavailable`/`failed`/skipped states carry a plain reason; render data uses effective verdicts (human wins). | Pass |
| IV. One engine, one boundary | Progression registration and stacking go through the Siril adapter (`engine()`, `heavy_memory()`); `select`/`unselect` take sequence positions (DR-18, Data and Engine Constraints) and are covered by the `siril`-marked engine test. | Pass |
| V. Reconcile, never guess | Folders that do not fit the layout are listed under "Not a project", never guessed; role guesses never override the owner's; unknown render fields are omitted, not zero-filled (FR-008); region and Bortle only from a source at the same whole-degree site (DR-07). | Pass |
| VI. Measured on real data | Progression weighting choice (noise, not sharpness) was verified on real Siril (DR-18); engine test builds real prefixes and checks noise falls. | Pass |
| VII. Self-hosted, queued and bounded | Progressions are a queued, deduplicated job (`progression:<id>`) in the heavy Siril slot at lower priority than masters, resumable (a restart re-queues), cancellable in Activity; images bounded in size and count; a periodic catch-up starts at most three per pass (DR-19). The SIMBAD look-up is optional and only on request; everything else works offline. | Pass |
| VIII. Accounts and access | Owner routes (`/finished`, `/tokens`) use the normal session auth; every change is `@admin_required`. Render routes accept only an active `render`-scope bearer token and no session; render tokens are not accepted anywhere else. Tokens are stored as SHA-256 digests, shown once, revocable, optionally expiring, with creator recorded. Link changes are recorded as undoable changes with the user (DR-20). | Pass |

## Project Structure

### Documentation (this feature)

```text
specs/020-finished-projects-api/
├── spec.md                      # with amendments 020-DR-01..20
├── plan.md                      # this file
├── research.md                  # decisions and open questions
├── data-model.md                # entities and states
├── quickstart.md                # validation guide
├── contracts/render-api.openapi.yaml
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
backend/
├── apps/finished/
│   ├── models.py          # FinishedProject, FinishedFile + FileRole, ApiToken + TokenScope, Progression + ProgressionState
│   ├── scan.py            # Completed library walk, not-a-project reasons, role guesses, step labels
│   ├── render.py          # render data v1, offered(), role_files(), data fingerprint and changed_at()
│   ├── api_render.py      # /render: RenderToken bearer auth, list, project, files (ETag/304, thumb, progression/<n>)
│   ├── api_manage.py      # /finished (owner): list/rescan, detail, images, suggestions, links, roles, distance,
│   │                      #   progression, render-data preview; /tokens: list, create, revoke
│   ├── distance.py        # SIMBAD TAP look-up (median of measurements, in light years)
│   ├── progression.py     # plan, availability, start, build_progression task, rendering, cache
│   └── migrations/0001..0004
├── apps/libraries/models.py        # LibraryRole.COMPLETED; site_region, site_bortle on Library and InstallationSettings
├── apps/catalogue/services/collections.py, api_projects.py   # unlink with a warning on delete; merge refused when an absorbed project is linked
├── substation/api/routes.py        # registers /finished, /tokens, /render under /api/v1
├── substation/tasks/management/commands/supervise.py           # _auto_progressions catch-up (DR-19)
└── tests/{integration/test_finished_render.py, unit/test_progression_*.py, engine/test_progression_siril.py}

frontend/
├── src/features/finished/{FinishedPage.tsx, FinishedProject.tsx, queries.ts, finished.module.css, Finished.test.tsx}
├── src/features/settings/{ApiTokens.tsx, ApiTokens.test.tsx, LibrarySite.tsx}
├── src/routes/router.tsx            # /finished, /finished/$id
└── tests/e2e/a11y.spec.ts           # /finished in the axe screens

docker/compose.yml                   # SUBSTATION_LIBRARY_4, _4_NAME, _4_MODE (read-only by default)
```

**Structure Decision**: one new Django app, `apps/finished`, beside the existing catalogue, processing and libraries
apps; it reads the catalogue (projects, datasets, frames, grades, measurements, plate solves) and never changes it.
The frontend adds one feature folder and a Settings section. No new service or container.

## Complexity Tracking

None. No principle is bent.
