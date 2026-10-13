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
