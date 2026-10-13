

- **005-DR-14 Version shown.** Images carry their version (pyproject version · branch · commit · build time), shown
  in the account menu and returned by /health. Build-master jobs name what they build ("Flat OIII · 28 Sep 2026 ·
  ATR2600M · 50 frames").

## Amendment 2026-10-13: filter the queue by kind

- **005-DR-15**: The queue's kind chips ("Calibrate and grade 625") are buttons: pressing one lists only that kind
  of job (in run order, paged as before); pressing it again lists every kind.

## Amendment 2026-10-13: a stack gets the whole container

- **005-DR-16**: While a stacking-slot job runs (integrate, combine, build a master), Siril uses every CPU its
  container has and 80% of free memory (`SUBSTATION_SIRIL_HEAVY_MEM`), then returns to the per-worker threads and
  share. One stacking slot means this can't overcommit. (A 135-sub M 81 Hα stack ran for over an hour on 2 threads
  and 60%.)
- **005-DR-17**: A deploy waits for a running stack or master build to finish (up to an hour) before restarting any
  worker, and leaves a paused queue paused.
- **005-DR-18** (2026-10-13): Resources fit the installation, not one machine: Settings → Workers sets Siril's
  threads and memory share while stacking (blank: every core, 80%); the Compose stack takes the worker containers'
  count, workers each, CPUs and memory cap as variables (`SUBSTATION_WORKER_REPLICAS`, `SUBSTATION_WORKERS_EACH`,
  `SUBSTATION_WORKER_CPUS`, `SUBSTATION_WORKER_MEMORY`), defaulting to 2 × 2 workers, 3 CPUs, 7 GB.
- **005-DR-19** (2026-10-13): A stack whose subs' calibrated copies were pruned from the cache calibrates them in
  batches: subs sharing their masters are one sequence and one Siril command (every thread), not one call each; the
  results go back into the cache. A group Siril can't do in one go falls back to one at a time.
