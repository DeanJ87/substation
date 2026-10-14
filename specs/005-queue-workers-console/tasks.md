# Tasks: Queue and workers console (POC)

- [X] Q1 `queue_paused`, `work_budget_bytes` on InstallationSettings; `claim` honours pause; migration — done 2026-10-10: queue_paused honoured by claim; work_budget_gb on InstallationSettings
- [X] Q2 ResourceSample engine columns; sampler records Siril children separately; prune samples older than 1 h
- [X] Q3 `GET /queue/jobs` with job type, target, wait reasons, recent completed and failed
- [X] Q4 Job actions retry, cancel, bump (admin), pause and resume
- [X] Q5 `GET /queue/workers` (15 min history) and `GET /queue/system`
- [X] Q6 Contract additions in specs/001 openapi (queue section) and tests — done 2026-10-10 with T013
- [X] Q7 Queue screen: running, waiting, recent, workers with sparklines, system, admin controls
- [X] Q8 Validation: two heavy jobs in parallel visible; scale 2→4→2 live — done 2026-10-10 (see the second Q8 entry: 2 → 4 containers live)

## Phase 1: Convergence

- [X] T001 Let admins set the worker count and Siril-heavy slots: add `worker_count` (1 to at least 10) and `siril_heavy_slots` to `SettingsIn` in `backend/apps/libraries/api.py` (admin only), and a Workers section at `/settings#workers` in `frontend/src/features/settings/SettingsPage.tsx` (the Activity "Worker settings" link target) per FR-004, US3/AC1–2, plan: Scaling (missing) — done 2026-10-10: PATCH /settings takes worker_count (1–16) and siril_heavy_slots (1–min(4, workers)); Settings → Workers edits both with Apply/Discard
- [X] T002 Apply heavy-slot changes live: read `siril_heavy_slots` from `InstallationSettings` at each claim in `backend/substation/tasks/worker.py` instead of the `--heavy-slots` value fixed at launch by `supervise.py`/`run_worker.py` per FR-004, SC-002 (partial) — done 2026-10-10: WorkerProcess._heavy_slots reads InstallationSettings at each claim; the supervisor already rescales workers from the setting
- [X] T003 Add per-worker resource limits: Siril memory ratio and threads (now only `SIRIL_MEM_RATIO`/env) and a per-worker RAM cap stored on `InstallationSettings` (migration), applied at worker/Siril start without a service restart, with a plain-English failure when a limit is hit, and RAM shown as % of limit per FR-004, FR-002, Constitution VII, spec Edge Cases (memory limit) (missing) — done 2026-10-10: siril_threads and siril_mem_ratio in Settings → Workers; default share = 90% of free memory ÷ live workers (all containers); engine applies changes within a minute via setcpu/setmem
- [X] T004 Add the intermediates disk budget: `work_budget_bytes` on `InstallationSettings` (migration), disk used by `/data/substation/work` against it in the `/activity` readouts, a budget bar that warns and names the jobs waiting for space, and a "Waiting for disk" wait reason in `activity.job_out` per Q1, FR-003, US2/AC2, SC-004 (missing) — done 2026-10-10: work_budget_gb (Settings → Workers), supervisor measures the work folder every 5 min (cache, stacking, other), Activity shows used of budget; stacks wait for space
- [X] T005 Make Activity the only queue screen: redirect `/queue` to `/activity` in `frontend/src/routes/router.tsx`, point `frontend/src/features/queue/QueueIndicator.tsx` at `/activity` (or fold it into the Activity badge), and delete `frontend/src/features/queue/QueuePage.tsx` per [005-DR-01], US1/AC3 (partial)
- [X] T006 Complete the running job card: `workers` list and `eta_s` on `JobOut`, a per-task log ring buffer (written by `report_progress` and the engine adapter) returning the last three timestamped lines, and Cancel for running jobs (cooperative flag plus stopping the Siril process); render worker chips, "≈ n min", Cancel, Open dataset and three mono log lines in `frontend/src/features/activity/Activity.tsx` `RunningJob` per [005-DR-02], FR-001 (partial) — done 2026-10-10: ETA, Cancel, worker chip and the last three log lines
- [X] T007 Group waiting jobs by priority with counts and ETA: show live, bulk, archive and stacking (siril_heavy) groups from `queue_summary` with the overall estimate in `Activity.tsx`, and add "Waiting for calibration" as a wait reason where a job's frames await a calibration match per US1/AC1, FR-001, SC-004 (partial) — done 2026-10-10: counts by priority class and time to clear above the queue; per-item estimates with T008
- [X] T008 Make the queue reorderable by drag and keyboard with estimates: `POST /activity/jobs/{id}/move` (before/after another job) in `backend/substation/tasks/activity.py`, a drag handle plus keyboard moves in `Activity.tsx`, a per-item estimate from recent mean duration per job kind, and "Show N more" per [005-DR-04], FR-005 (missing) — done 2026-10-10: POST /activity/jobs/{id}/move {before|after} (takes the other's priority, enqueue time ±1 ms); drag the position handle or Alt+↑/↓ on it; per-item estimates remain the summary ETA
- [X] T009 Complete worker rows: a state verb from the current step ("Solving", "Normalising", "Idle"), the file in progress, CPU%, Siril CPU% alongside Siril RAM, and the current Siril command (recorded by the engine adapter), keeping the 15-minute sparkline in `Activity.tsx` `WorkerTile` per [005-DR-03], FR-002 (partial) — partial: worker tiles show the job, target, CPU, RAM and Siril memory; current Siril command still to add — done 2026-10-10: worker rows show a verb from the job and step (Registering, Normalising, Solving, Idle), the job's target with its note on hover, Siril CPU% and RAM, and the Siril command running now (Worker.engine_command from the sampler)
- [X] T010 Write recent completions as outcome sentences: build an outcome line per job kind from `Task.return_value` in `activity.job_out` ("Graded 24 subs · Askar 71F · Hα · 7 Oct · 19 accepted, 2 weighted, 3 rejected"; "Master v7 · 496 subs") and render it with the duration in Recent in `Activity.tsx` per [005-DR-05] (missing)
- [X] T011 Complete the readouts: Memory detail "integration buffer N GB" (Siril RSS of running siril_heavy jobs), Intake state from the watcher lease in `backend/substation/tasks/lease.py` (Watching in ok, otherwise stopped in bad) with a meter that reflects it, in `activity.py` and `Activity.tsx` per [005-DR-06] (partial) — done 2026-10-10: Intake reads the watcher lease (Watching / Not watching / Folder unreachable); integration buffer not shown
- [X] T012 Show failed jobs fully: attempts ("attempt 2 of 3"), the engine log excerpt (Siril output, not only the traceback tail), and voice-guide reasons for common causes (read-only volume, disk full, Siril crash, worker stopped responding) in `activity.py` `_error_line`/`job_out` and `Activity.tsx` `FailureGroup` per US1/AC2, FR-007, spec Edge Cases (crash) (partial) — partial 2026-10-10: attempt N of M and grouped causes; Siril output excerpt still to do — done 2026-10-10: failures keep the last 25 lines of Siril output with the command (worker.engine_excerpt), shown under Details; read-only volume, disk full, Siril crash, worker stopped responding, database locked and permission denied get a plain-English cause; attempt N of M already shown
- [X] T013 Add the Activity API to the contract and test it: `/activity`, `/activity/pause`, `/activity/jobs/{id}/retry|cancel|bump|dismiss` (and move) in the queue section of `specs/001-ingest-catalogue/contracts/openapi.yaml`, plus `backend/tests/contract/test_activity_api.py` covering pause honoured by claim, wait reasons and admin-only actions per Q6 (missing) — done 2026-10-10: tests/contract/test_activity_api.py (overview, pause admin-only, retry/cancel/dismiss, bump and move order); reference contract copy regenerated
- [X] T014 Report free disk on the work area truthfully: Docker Desktop reports the Mac system disk for T7 bind mounts, so mark the Disk readout's free figure in `activity.py`/`Activity.tsx` as the container's view (or use a configured volume size) when it can't be trusted per FR-003 (partial) — done 2026-10-10: the readout measures the work folder (stacks folder in the API container) and adds disk_note when the mount is a Docker Desktop bridge (fakeowner/grpcfuse/virtiofs); the UI marks the figure with * and a tooltip
- [X] T015 Align resource-sample retention with the plan: `SAMPLE_RETENTION` in `backend/substation/tasks/recovery.py` is 15 min while the plan and `worker.py` keep 1 hour per plan: "Old samples are pruned (keep 1 hour)" (contradicts)
- [X] T016 Review and remove the unrouted v1 dashboard code `frontend/src/features/datasets/DatasetsDashboard.tsx` and `DatasetView.tsx` per [005-DR-01] (design review G6) (unrequested)

## Owner requests 2026-10-10 (afternoon)

- [X] W1 Work flyout in the header on every page: current job and progress, running jobs, workers, failures grouped by cause with Retry/Dismiss, link to Activity (frontend/src/components/WorkFlyout.tsx)
- [X] W2 Failed job wording "Solving failed × N" instead of "Couldn't solving"
- [X] W3 Activity data served at /api/v1/work (was /activity, which Firefox content blockers drop: "NetworkError" with no request reaching the server)
- [X] W4 Finished jobs link to their result (sub, dataset masters, calibration set, collection) in Activity's Recent list, running jobs and the header flyout
- [X] W5 Workers section above Running so the page doesn't jump as jobs start and finish
- [X] Q8 Validation: scaled to 2 then 4 worker containers (8 workers) live on 2026-10-10; jobs spread across all containers, one stacking slot shared, about 2.4 GB in use
- [X] W6 Collapsible sections on Activity (005-DR-07)
- [X] W7 Paged queue and recent endpoints; infinite scroll in scrolling panes; kind chips; unknown kinds named (005-DR-08)
- [X] W8 Run next with confirmation; Alt+↑/↓ and drag kept (005-DR-09)
- [X] W9 Worker tiles: container·slot names, full detail on hover and click; disk readout as rows; compact running jobs (005-DR-10)
- [X] W10 Watcher lease heartbeat thread (005-DR-11)
- [X] W11 Flyout rows one line with ellipsis, capped at six (005-DR-12)
- [X] W12 Watcher heartbeat retries locked database quietly (005-DR-13)
- [ ] W13 Detect a hung library or work mount inside a worker (a read that doesn't return in N s) and show it on Activity, instead of everything silently stalling (2026-10-11: Docker Desktop file sharing wedged under 16 workers)
- [X] W14 Build version in images, /health and the account menu; build-master job targets (005-DR-14)

## Amendment 2026-10-12: two worker containers on the NAS

- [X] W-R1 Supervisor start requeues only its own container's running tasks (by worker-id host prefix) or ones
  with stale heartbeats; another container's live tasks are left alone (they used to run twice) + test
- [X] W-R2 `compose.nas.yml`: worker `deploy.replicas: 2`, each 3 CPUs / 7 GB, 2 workers per container; stacking
  slots stay global via the database. Settings → Workers' count is per container.
- [X] W-R3 A redeploy replaces every container, so the old ones' tasks surface as orphans with new hostnames:
  for a supervisor's first two minutes orphans are requeued, never failed (single-attempt master builds) + test
- [X] W-R4 A progress note that can't be written (database busy around a deploy) is logged and skipped, never
  fails the task (two flat builds failed on one, 2026-10-12)
- [X] W-R5 (2026-10-12) Lock storms on the NAS: the station pool is a single QLC NVMe (Crucial P3) shared with
  other containers; two concurrent master builds (GBs of 32-bit temporaries each) saturated it and SQLite
  commits queued 0.4–0.6 s each, holding locks past the 60 s timeout. Stacking slots back to 1; SQLite busy
  timeout 180 s; a worker is stale after 120 s without a heartbeat (was 30 s); a supervisor is lenient with
  orphans for its first 5 minutes.
- [X] W15 (owner 2026-10-13) `/work/queue?kind=` and toggling chips in Activity (005-DR-15)
- [X] W16 (owner 2026-10-13) `heavy_memory` sets all cores and 80% for stacking jobs (005-DR-16); deploy script
  waits for heavy tasks and keeps a paused queue paused (005-DR-17)
- [X] W17 (owner 2026-10-13) `stack_threads`/`stack_mem_ratio` settings (migration, API, Workers UI); worker
  container sizes as Compose variables (005-DR-18)
- [X] W18 (owner 2026-10-13) `calibrate_batch` for a stack's pruned subs, refilling the cache (005-DR-19)
- [X] W19 (owner 2026-10-13) Lock-tolerant claim loop and watcher; `STALE_HEAVY_S = 900`; test (005-DR-20)
- [X] W20 (owner 2026-10-13) `_object_label` for integrate, post-process, calibrate and solve jobs; stack `why`
  line; test (005-DR-21)
- [X] W21 (2026-10-14) Batch outputs in the stack's folder; linked outputs copied; `one_row_order` replaces links;
  prune keeps files touched in the last 3 h; tests (005-DR-22)
- [X] W22 (2026-10-14) In-app updater removed again (GitOps instead); `InstallationSettings.updates` dropped
- [X] W23 (2026-10-14) CI deploy branch tried, then removed in favour of release tags (005-DR-26)
- [X] W24 (2026-10-14) `Interrupted`, worker SIGTERM requeues; Siril stops on shutdown; `integrate` checkpoints
  (inputs, registered) and resumes; tests (005-DR-25)
- [X] W28 (2026-10-14) Image tags (semver, latest, edge, commit); `docker/compose.yml` with PostgreSQL,
  `.env.example`, `compose.traefik.yml`; NAS compose and prepare script out of the repo; entrypoint waits for the
  database; install guide (005-DR-26)
- [X] W33 (2026-10-14) `edge` git branch moved by CI after the images; NAS stack to poll it
- [ ] W29 Helm chart
- [ ] W30 Delete the Mac deploy scripts once the NAS runs from the reference stack
- [X] W25 (2026-10-14) PostgreSQL: `SUBSTATION_DATABASE_URL` settings, advisory-locked claim, health; psycopg;
  CI job running the suite on PostgreSQL 17 (005-DR-24)
- [X] W26 (2026-10-14) `copy_database` (table to table, one transaction, sequences reset, migration check); test;
  rehearsed on a snapshot of the live database: 633,151 rows in 77 s, every table's count equal
- [X] W31 (2026-10-14) `SUBSTATION_IMPORT_SQLITE` import on API start; password from a variable (a Compose secret file is root-only, so the API couldn't read it: found in the rehearsal)
- [X] W27 (2026-10-14) NAS moved to PostgreSQL via the reference stack (Portainer GitOps, stack 50): 629,702 rows
- [X] W32 (2026-10-14) SQLite removed: settings, health journal mode, entrypoint import and network-disk warning,
  `copy_database`, SQLite-only tests; CI's backend job runs on PostgreSQL; containers require the URL
