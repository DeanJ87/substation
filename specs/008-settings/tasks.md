# Tasks: Settings

Done items were verified against the code on 10 October 2026. Open items name the files to touch and the
requirement they close. G57 and G58 refer to `docs/design/design-review.md` section C.

## Phase 1: Existing foundations (built)

- [X] T1 Settings route with Rigs, Path patterns and Ignored sections [008-DR-01, partial]
  - `frontend/src/features/settings/SettingsPage.tsx`, `Rigs.tsx`, `PathPatterns.tsx`, `IgnoreRules.tsx`
- [X] T2 Installation settings store: site, filter aliases, worker count, heavy slots, pause, processing JSON with spec defaults
  - `backend/apps/libraries/models.py` `InstallationSettings`; `backend/apps/processing/config.py`
- [X] T3 `GET/PATCH /settings` (admin-only writes, `updated_by` recorded) with tests
  - `backend/apps/libraries/api.py`; `backend/tests/integration/test_settings_api.py`
- [X] T4 Watched folders as `Library` rows with status, last sweep and rescan
  - `apps/libraries/models.py`, `apps/libraries/api.py` (`/libraries`, `/libraries/{id}/rescan`)
- [X] T5 Rigs list with camera, focal length, image scale and session count; rename and merge [008-DR-09, partial]
  - `features/settings/Rigs.tsx`
- [X] T6 Admin and standard roles; admin-only writes [008-DR-07, partial]
  - `backend/apps/accounts/roles.py`

## Phase 2: Page frame and save model

- [X] T7 One scrolling page with a sticky left rail and anchors for all twelve sections, scroll-spy [008-DR-01, G57]
  - `features/settings/SettingsPage.tsx`, `settings.module.css`, new `features/settings/SettingsRail.tsx`
- [X] T8 Settings draft with labelled changes, sticky save bar with Discard and Save or "Save and re-grade", in-page leave guard [008-DR-04, G58, edge case]
  - new `features/settings/draft.ts`, `features/settings/SaveBar.tsx`; `SettingsPage.tsx` (TanStack `useBlocker`, 007 B24 `Confirm`)
- [X] T9 Settings API: `processing` (validated partial), `priority_mode`, `notifications`, read-only `cpu_threads` [008-DR-03, 008-DR-05, 008-DR-06] — partial 2026-10-10: processing (validated), can_edit, cpu_threads done; priority_mode and notifications still to do. Done 2026-10-10: priority_mode (processing.queue: new_first / in_order) applied by priority_for; Work order in Settings → Workers; notifications done earlier
  - `backend/apps/libraries/api.py` `SettingsIn`, `SettingsOut`; `models.py` fields + migration
- [X] T10 Re-grade preview and save: `POST /settings/preview` returns datasets that would be re-graded; `regrade: true` bumps `grading.version` and enqueues `regrade_datasets`; overrides untouched [008-DR-04]
  - `backend/apps/libraries/api.py`; `backend/apps/processing/tasks.py` `regrade_datasets`; `processing/grading.py` (in-memory grade for preview)

## Phase 3: Sections

- [X] T11 Folders: role, status with dot and last file, Edit, output folder with free and total space, "Add folder" guidance and rediscovery [008-DR-02]
  - `apps/libraries/models.py` `Library.role` + migration; `api.py` `LibraryOut.role`, `last_file_at`, `POST /libraries/discover`; new `features/settings/Folders.tsx`
- [X] T12 Grading: "Each sub is compared with the median of its own session.", per-measure down-weight and reject with direction and explanation, "Use SQM and cloud when recorded" switch [008-DR-03, G58]
  - new `features/settings/Grading.tsx`; `processing/config.py` `grading.use_sqm_cloud`; `processing/grading.py` (flag, never reject, on SQM or cloud alone)
- [X] T13 Stacking: rejection, sigma, weighting, reference, auto stack [008-DR-01]
  - new `features/settings/Stacking.tsx`
- [X] T14 Workers: "N of M CPU threads" and priority (New subs first, In order); Activity's "Worker settings" lands here [008-DR-05] — partial 2026-10-10: read-only workers summary; editable count waits on 005 T001/T002 — done 2026-10-10: editable worker count, stacking slots and work budget (005 T001/T004); priority mode stays "New subs first"
  - new `features/settings/Workers.tsx` (`id="workers"`); `backend/substation/tasks/claim.py` (`priority_mode`); `features/activity/Activity.tsx` link already targets `#workers`
- [X] T15 Notifications: ntfy, webhook and email channels, event choices, "Send test", description copy [008-DR-06] — done 2026-10-10 for ntfy and webhook (master finished, job failed hooks; test send); email waits on SMTP settings
  - new `backend/substation/notify.py` (`send_notification` task); hooks in `apps/processing/masters.py`, `substation/tasks/worker.py`, `apps/processing/matching.py`; `POST /settings/notifications/test`; new `features/settings/Notifications.tsx`
- [X] T16 Users: list with role and last sign-in, "Add user", role change, read-only role ("can review, can't override") enforced on write endpoints [008-DR-07]
  - new `backend/apps/accounts/api.py` (`/users`), `roles.py` (`readonly`, `writer_required`); decorate writes in `apps/processing/api.py`, `apps/catalogue/api_library.py`, `api_metadata.py`, `apps/processing/api_masters.py`; new `features/settings/Users.tsx`
- [X] T17 Appearance: segmented Dark / Light / Night vision with "Press N anywhere for night vision" [008-DR-08, 007-DR-06]
  - new `features/settings/Appearance.tsx`; `design/useTheme.ts` (007 B11)
- [X] T18 Rigs: mount type, Edit dialog (rename, merge), "Add rig" [008-DR-09] — done 2026-10-10: mount type per rig; rename, calibration and merge in the row; Add rig (POST /rigs) before its first sub
  - `apps/catalogue/models/library.py` `Rig.mount` + migration; `api_library.py` `POST /rigs`, `RigOut.mount`; `features/settings/Rigs.tsx`
- [X] T19 Metadata sources: site name and position, filter aliases, header sources in use [008-DR-01] — partial 2026-10-10: site and filter aliases shown; header sources in use still to do. Done 2026-10-10: Sources in use (GET /settings/sources): each field's winning keyword, pattern or user value with file counts
  - new `features/settings/MetadataSources.tsx` (existing `/settings` fields)
- [X] T20 Plate solving section (delivered by spec 009 P13) [008-DR-01] — done (009 P13)
- [X] T21 Read-only view: controls disabled and no save bar for non-admins [edge case] — done 2026-10-10: can_edit disables controls, hides Users, no save bar; the API refuses writes
  - `features/settings/*.tsx` via a `useCanEdit()` hook in `draft.ts`; session role from `api/auth.ts`

## Phase 4: Tests, contract, validation

- [X] T22 Tests: settings validation, preview counts, re-grade keeps overrides, users API and read-only enforcement, change labels in the save bar — done 2026-10-10 (tests/processing/test_settings_regrade.py, tests/contract/test_users_api.py, tests/unit/test_notify.py; save bar checked in a browser)
  - `backend/tests/integration/test_settings_api.py`, new `test_users_api.py`; new `features/settings/draft.test.ts`
- [X] T23 Regenerate the client contract and the reference copy — done 2026-10-10: client regenerated; full generated contract at specs/001-ingest-catalogue/contracts/openapi.generated.json beside the hand-written subset the contract test checks
  - `frontend/src/api/openapi.json`, `schema.d.ts`; `specs/001-ingest-catalogue/contracts/openapi.yaml`
- [X] T24 Independent test: change the FWHM reject threshold, the bar names it and the datasets to re-grade; Save and re-grade queues them; Discard restores [US1] — done 2026-10-10 (tests/processing/test_settings_regrade.py, tests/contract/test_users_api.py, tests/unit/test_notify.py; save bar checked in a browser)
- [X] T21 Settings lists sort: path-pattern preview by its headings; ignore rules (newest, kind, files held back) and users (name, role, last sign-in)

- [X] T25 Tabbed settings with hash links (008-DR-10)
- [X] T26 Paged ignore rules (limit, offset, sort) with infinite scroll (008-DR-11)
- [X] T27 Rig rows on a grid (008-DR-12)

## Amendment 2026-10-12: file paths

- [X] P1 `file_path` on masters and combined masters; `processing.paths.map` setting
- [X] P2 `FilePath` component (mapping, Copy path) replaces Download; File paths section with per-browser overrides; tests
- [X] T28 (2026-10-14) Pushover channel in `notify.send`, settings validation, keys hidden from non-admins,
  Settings → Notifications fields; tests (008-DR-13)
- [X] T29 (2026-10-15) File mode setting (per browser), Download in `FilePath` with fallback when unmapped,
  processed-version download endpoint (008-DR-14); test
- [X] T30 (2026-10-17) Folders: mount mode, role and archive controls with the read-only reason, archive suggestion
  days; `archive` settings section validated (008-DR-15); tests
