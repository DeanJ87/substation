

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
