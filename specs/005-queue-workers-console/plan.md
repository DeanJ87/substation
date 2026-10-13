# Plan: Queue and workers console (POC: stories 1–3)

Builds on spec 001's queue (Task, Worker, ResourceSample, supervisor, `siril_heavy` slots).

- **Jobs API** `GET /queue/jobs`: running jobs (type from the task name, target from its arguments, worker,
  progress, elapsed), waiting jobs grouped by priority class with counts, ETA and *why they are waiting*
  (paused, slots full, scheduled retry, priority), and the last 50 completed and failed jobs. Failed jobs
  carry the error's last line as the reason, plus the log excerpt.
- **Job actions** (admin): retry, cancel, move to front (`POST /queue/jobs/{id}/retry|cancel|bump`).
- **Pause and resume**: `InstallationSettings.queue_paused`; `claim` returns nothing while paused.
- **Workers API** `GET /queue/workers`: each worker with state, current job, uptime, and 15 minutes of
  samples; samples split into the worker process and its Siril child (`engine_cpu_pct`, `engine_rss_bytes`).
- **System API** `GET /queue/system`: CPU and RAM of the host (psutil), free disk and disk used by
  `/data/substation/work` against `InstallationSettings.work_budget_bytes`.
- **Scaling**: `PATCH /settings` already sets `worker_count` and `siril_heavy_slots` (supervisor applies
  them live); the console exposes them to admins.
- **UI**: Queue screen with running jobs, waiting groups, recent jobs, worker cards with CPU and RAM
  sparklines, system bars and admin controls. Live via `queue.changed` plus a 2 s poll while open.
- Old samples are pruned (keep 1 hour).
