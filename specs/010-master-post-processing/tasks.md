# Tasks: Master post-processing (spec 010)

- [X] T001 `processing.post` defaults (off; background → deconvolve → denoise; starless off) and editable section
- [X] T002 `postprocess.py`: readiness, command lines (GraXpert `-cli -cmd …`, `rc-astro bxt|nxt|sxt --depth 32F`)
- [X] T003 `run_chain`: each step on the last good stage; missing tool skipped with reason; master untouched
- [X] T004 `postprocess_master` task; runs recorded on `Master.report.post_runs` with previews
- [X] T005 `integrate` queues the chain when on
- [X] T006 API `GET/POST /stacks/{id}/post`, stage preview
- [X] T007 UI: stages strip and "Post-process this master / again" on each master; Settings section
- [X] T008 Tests: command lines, skip-when-missing, chaining with a stand-in tool, master untouched
- [X] T009 Constitution v2.1.0: second adapter boundary for external finishing tools
- [X] T010 Finisher container (`docker/finisher.Dockerfile`, compose `finisher`): only the `finish` queue
  (`SUBSTATION_ONLY_QUEUES`; main workers `SUBSTATION_SKIP_QUEUES=finish`), GraXpert 4.0.0 pinned by checksum,
  RC-Astro unpacked and activated at first start onto the `/opt/finish` volume from `RC_ASTRO_INSTALLER_URL`,
  `RC_ASTRO_EMAIL`, `RC_ASTRO_KEY` (Portainer env, never in git) — owner 2026-10-12
- [X] T013 Preflight: master not visible, unreadable, output folder not writable, tool not executable, tool wrote
  nothing — each a plain reason, never a crash; queue routing test
- [ ] T011 Per-dataset override in the stack dialog (US5)
- [ ] T012 Combined/palette masters (US6); run picker and per-stage delete (US3); starless toggle (US4)
- [X] T014 (owner 2026-10-12) The master card shows
  the latest processed stage, with an Original toggle; each stage is labelled "vN · step" and shows its linear
  FITS path (Copy path)
- [X] T015 An unlicensed RC-Astro counts as not ready (its CLI runs but refuses work); GraXpert denoises instead
- [X] T016 The finisher sizes itself (SUBSTATION_WORKERS, not the site worker count) and skips library discovery
- [X] T017 (owner 2026-10-12) The run's log says each step's outcome in order (running GraXpert → done in N s /
  skipped (reason) / failed (reason)), not three "starting" lines that read as parallel; post-processing jobs
  show in Activity like the others (name, "Master vN · dataset" target, link, done sentence, verb)
- [X] T018 (2026-10-12) RC-Astro is activated with a one-off code (`rc-astro license <code>`, 30-minute expiry) and
  ties the licence to the machine: a plain restart lost it. The finisher's hostname and MAC address are pinned in
  compose so it stays "this computer" across restarts and deploys; the finisher also looks for the CLI at
  /opt/finish/rc-astro
- [X] T019 (owner 2026-10-12) Activate RC-Astro from the web: Settings → Processing shows what the finisher can run
  (it reports on start and on "Check again") and takes an activation code, which the finisher applies itself.
  The finisher activates once; its identity is pinned. Owner 2026-10-12: parallel runs on the one machine are
  fine (like several CLI instances), so parallelism is more workers in the finisher (`FINISHER_WORKERS`), all
  sharing its activation
- [X] T020 (owner 2026-10-12) Quick finisher jobs (check tools, activate RC-Astro) run on their own `finish_ctl`
  queue and a small control worker, so an activation code never waits behind a long post-processing run
- [X] T021 (owner 2026-10-12, M81 Hα) Registration edges are trimmed before the tools run ("Edges trimmed" stage):
  the ragged empty border from mixed nights made GraXpert's background model leave dark bands and blotches
- [X] T022 (owner 2026-10-12) The 100% view tabs through a master's versions — Original, + GraXpert,
  + BlurXTerminator, + NoiseXTerminator — at full resolution, keeping zoom and position ([ and ] to switch)
- [X] T023 Every stage is drawn with its master's stretch (preview and 100%): NoiseXTerminator's cleaner sky made
  each stage's own auto-stretch far harsher, turning sub-1% residuals into dark blotches; older runs are redrawn
- [X] T024 (owner 2026-10-12) Stages open the 100% view on their version ("View at 100%"), no separate preview
  links or thumbnails; switching versions keeps your place (centred once; the image keeps its size while loading);
  a measurements panel beside the image (sky background and noise in ADU, brightest signal, signal to noise, change
  against the original)
- [X] T025 (owner 2026-10-13) A version shows "Loading … at full resolution" while it loads; the others are
  fetched in the background once the first is up, so later switches are instant
- [X] T026 (owner 2026-10-13) Helper API (`/api/v1/helper/`: claim, master download, progress, stage upload,
  done, fail, ping), token auth; tests (end to end, no token, someone else's job)
- [X] T027 `backend/tools/substation_helper.py`: standard-library helper for the Mac (GraXpert app, RC-Astro CLI at
  /Applications/RC-Astro/CLI), `--check` and `--once`
- [X] T028 NAS finisher removed from compose; its RC-Astro activation released; queued post-processing cancelled;
  masters say when they're waiting for a helper
- [X] T029 (owner 2026-10-13) The finisher image runs the helper by default (`entrypoint.sh helper`, no data dir
  needed); `docker/compose.helper.yml` for Linux/NVIDIA machines; the helper uses the tool paths the entrypoint found
- [X] T030 A post-processing job may be retried up to 3 times (a helper restarting mid-job); a configured tool path
  is used as given, never swapped for another install
- [X] T031 (owner 2026-10-13) Helper CPU/RAM samples (helper and tool process trees, via `ps`) sent with progress
  every 10 s and with idle claims; stored as the helper worker's resource samples; Activity labels helper tiles by
  machine and the engine by tool; cancel stops the tool at once; image gains `procps`; test
- [X] T032 (owner 2026-10-13) Helper `_again` retry for post/download/upload; `/fail` requeues while attempts
  remain; test
- [X] T033 (owner 2026-10-14) `shifted_stretch` + `plane_backgrounds` in stage_views; test; all post-processed
  masters' views redrawn
- [X] T034 (2026-10-14) Stage uploads in 16 MB pieces (`offset`, `last`) so a proxy's one-minute limit can't cut
  them off; helper VERSION 4; test

## Amendment 2026-10-24: combined masters

- [X] T035 `postprocess.py`: the chain runs on any object with `output_path` and `report` (a master or a combined
  master): `postprocess()`, `record_run()`, `redraw_views()`, `post_object()`, `post_name()`; new task
  `postprocess_combined` on the `finish` queue; `redraw_post_views` takes a kind (010-DR-23, 010-DR-26)
- [X] T036 `CombinedMaster.report` JSON field (migration `processing.0018_combined_report`)
- [X] T037 Combining queues post-processing for each new current combined master when the chain is on
  (`combine._after_combine`) (010-DR-23)
- [X] T038 API: `/combined/{id}/post` (GET; POST admin only, refused for a deleted or unfinished one),
  `/combined/{id}/post/views`, stage preview, 100% view and download (010-DR-26)
- [X] T039 Helper API dispatches on the task: claim, download, stage upload, done and fail work for combined jobs;
  the job carries `kind` (010-DR-26)
- [X] T040 Size limits: `image_size`, `available_memory`, `size_problem`; refused runs recorded as a failed
  "Before starting" stage, on the worker and at helper claim; `post.max_megapixels` setting and its range check
  (010-DR-27)
- [X] T041 Activity names, outcomes, links and the stale-failure check for `postprocess_combined`
- [X] T042 UI: combined master card shows the latest run's stages, View at 100%, stage files, and Run
  post-processing / Run again for admins; the card's picture is the latest processed stage; the 100% view tabs
  through versions for combined masters; Settings shows the largest-image limit (010-DR-24, 010-DR-25)
- [X] T043 Tests: chain on a combined master, API and admin check, automatic queueing on and off, each size limit,
  a too-big run recorded without crashing, a helper end to end on a combined master, a helper refused a canvas too
  big for the server
- [ ] T044 Palette images (HOO, SHO) through the chain (rest of US6)

## Amendment 2026-10-24 (2)

- [X] T045 Combined masters listed per filter as current plus a newer queued/running/failed try; deleted and
  superseded ones never hide the current one (010-DR-28)
- [X] T046 Combined card: thumbnail per finished stage opening the 100% view on that version, a tile for a stage
  without a preview, files folded under "Files of each step", the helper named; post lists tolerate missing or
  null fields; `post`, `post-combined` and `combined` queries refresh on `master.updated` (010-DR-28)
- [X] T047 Steps per run: `step_choices`, `chosen_overrides`, optional `{steps}` body on both POST routes, `chosen`
  recorded on NAS and helper runs, helper runs record the settings they ran with; dialog on both cards (010-DR-29)
- [X] T048 Tests: the production report shape (helper run, stage without preview, null fields), a newer failed or
  deleted try beside the current one, chosen steps end to end, unavailable steps; frontend card, dialog and request
  body tests
