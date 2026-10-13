

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
