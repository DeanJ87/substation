# Plan: Settings

One scrolling Settings page with a left rail and a sticky save bar. Three sections exist (Rigs, Path
patterns, Ignored) and most values already live on `InstallationSettings`; the work is the page frame, the
draft-and-save model with the re-grade offer, the missing sections and the backend fields and endpoints
behind them.

## Technical context

- Storage: singleton `InstallationSettings` (`backend/apps/libraries/models.py`): site, `filter_aliases`,
  `worker_count`, `siril_heavy_slots`, `queue_paused`, and `processing` JSON (calibration, grading, stacking,
  equipment aliases) merged over `DEFAULTS` in `backend/apps/processing/config.py`. Libraries (watched
  folders) are `Library` rows discovered under `/data/library` (`apps/libraries/discovery.py`).
- API: `GET/PATCH /settings` (`apps/libraries/api.py`, admin-only writes, `updated_by` recorded),
  `/libraries` list, patch and rescan. Grading thresholds are not exposed yet.
- Grading: `apps/processing/grading.py` `grade_session(dataset_id, night_id)`; `MachineGrade.thresholds_version`
  records the threshold version a grade used; human verdicts are separate rows
  (`apps/catalogue/models/decisions.py`), so re-grading never touches overrides.
- Roles: groups `admin` and `standard` (`apps/accounts/roles.py`), `admin_required` in `substation/api`.
  No user-management API yet.
- Frontend: `features/settings/SettingsPage.tsx` renders `Rigs`, `PathPatterns`, `IgnoreRules`;
  `#rigs` anchor exists; Activity links to `/settings#workers`, which does not exist yet.

## Design

- **Page frame** (008-DR-01): a two-column layout, rail on the left (sticky, anchors `#folders #rigs
  #grading #stacking #plate-solving #metadata #patterns #ignored #notifications #workers #users
  #appearance`, scroll-spy with IntersectionObserver), sections stacked on the right. Each section is its
  own component in `features/settings/`.
- **Draft and save bar** (008-DR-04): `useSettingsDraft()` holds the server value and a draft; every
  control writes to the draft with a human label. The bar lists each change ("FWHM reject threshold
  1.60× → 1.50×"), calls `POST /settings/preview` with the draft to get `regrade_datasets` (datasets with
  measured subs whose `thresholds_version` would change and whose verdict would differ, computed by running
  the grader in memory per session), and offers Discard and "Save and re-grade" (or Save when nothing
  re-grades). Leaving with unsaved changes uses TanStack Router `useBlocker` with the in-page confirmation
  (007 B24). Path patterns, ignore rules and rigs keep their own immediate actions (they already preview
  their effects).
- **Settings API**: `SettingsIn/SettingsOut` gain `processing` (partial, validated per key: thresholds
  positive and down-weight below reject in the right direction), `worker_count`, `priority_mode`,
  `notifications`, and read-only `cpu_threads` and `plate_solving_available`. `PATCH /settings` with
  `regrade: true` bumps `grading.version` and enqueues `regrade_datasets` (process queue, bulk priority).
- **Grading** (008-DR-03): per measure (FWHM, stars, background relative to the session median;
  eccentricity absolute) down-weight and reject levels with direction and a one-line explanation; switch
  "Use SQM and cloud when recorded" (`grading.use_sqm_cloud`); the grader flags but never rejects on SQM or
  cloud alone.
- **Stacking**: rejection, sigma low and high, weighting, reference, auto stack (from `stacking`).
- **Folders** (008-DR-02): `Library.role` (lights, lights archive, calibration; migration) and
  `last_file_at` (latest catalogued file per library) in `LibraryOut`; status line with dot ("Watching ·
  last file 3 min ago", "idle since 28 Sep"); Edit (role, enabled, sweep intervals); the output folder with
  free and total space from `/health`. "Add folder" explains mounting a folder under `/data/library` in
  Compose and offers "Look for new folders" (`POST /libraries/discover`, admin).
- **Workers** (008-DR-05): worker count as "N of M CPU threads" and priority "New subs first" or "In order"
  (`InstallationSettings.priority_mode`; `claim.py` keeps live priority ahead when "new first", otherwise
  orders by enqueue time inside each queue).
- **Notifications** (008-DR-06): `InstallationSettings.notifications` JSON (ntfy server and topic, webhook
  URL, email via Django SMTP settings; events). `substation/notify.py` `notify(event, text)` enqueues a
  `send_notification` task (default queue); hooks on master finished (`processing/masters.py`), job failed
  (`substation/tasks/worker.py`), awaiting calibration (`processing/matching.py`, once per dataset) and a
  session summary after a night's grading. `POST /settings/notifications/test`.
- **Users** (008-DR-07): `apps/accounts/api.py` `GET /users` (role, last sign-in), `POST /users`,
  `PATCH /users/{id}` (role, active), admin-only; a third group `readonly` ("can review, can't override");
  a `writer_required` decorator on verdict, collection, correction and stack endpoints.
- **Appearance** (008-DR-08): segmented Dark / Light / Night vision (tint and accent text) with "Press N
  anywhere for night vision", using `useTheme` (per-user persistence from 007 B11).
- **Rigs** (008-DR-09): mount type (`Rig.mount`, user-entered; headers rarely carry it), Edit dialog for
  rename and merge, "Add rig" for equipment not yet seen (`POST /rigs`).
- **Plate solving** section is delivered by spec 009 (P13); **Metadata sources** shows site and filter
  aliases (already in the API) and the header sources in use.
- **Read-only users** see every section with controls disabled and no save bar.

## Constitution check

- VII (bounded resources): worker count and priority become user-visible settings. Pass.
- VIII: user administration is admin-only, every settings change records `updated_by`; the read-only role
  narrows access. Pass.
- III: re-grades keep overrides and every new grade states its reason. Pass.

## Project structure

```text
backend/apps/libraries/models.py, api.py        role, last_file_at, priority_mode, notifications, preview, discover
backend/apps/processing/config.py, grading.py,  grading.use_sqm_cloud, regrade_datasets task
  tasks.py
backend/apps/accounts/api.py, roles.py          users API, readonly role, writer_required
backend/substation/notify.py                    notifications
backend/substation/tasks/claim.py               priority_mode
frontend/src/features/settings/                 SettingsPage.tsx (rail), draft.ts, SaveBar.tsx, Folders.tsx, Grading.tsx,
                                                Stacking.tsx, MetadataSources.tsx, Notifications.tsx, Workers.tsx,
                                                Users.tsx, Appearance.tsx, Rigs.tsx, settings.module.css
```

## Complexity tracking

Notifications add the first outbound network calls; they are optional, off by default, and the app stays
fully offline without them (constitution VII).
