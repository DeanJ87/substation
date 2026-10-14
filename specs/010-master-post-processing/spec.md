# Feature Specification: Master post-processing

**Feature Branch**: `010-master-post-processing`

**Created**: 2026-10-11

**Status**: Draft

**Input**: Owner request, 2026-10-11: after stacking, run each master through GraXpert, then BlurXTerminator,
then NoiseXTerminator, so its preview is a near-finished image; configurable, and able to be switched off. Also StarXTerminator for starless output. Tools: GraXpert (open source, GPL-3.0) and the
RC-Astro stand-alone tools (BlurXTerminator, NoiseXTerminator, StarXTerminator; proprietary, licensed per user,
beta command-line version for Linux, Windows and macOS).

## Overview

When SubStation finishes integrating a master light, it can run that master through a chain of post-processing
steps:

1. gradient removal;
2. deconvolution;
3. noise reduction;
4. optionally, star separation.

As a result, the master's preview shows a near-finished image rather than a flat, gradient-washed linear stack.
The untouched linear master is always kept. Each step writes its own artefact, so the user can take any stage into
their own processing.

The default chain is:

| Order | Step | Tool | Produces |
|-------|------|------|----------|
| 1 | Background extraction | GraXpert | background-extracted master (and optionally the background model) |
| 2 | Deconvolution | BlurXTerminator | deconvolved master |
| 3 | Noise reduction | NoiseXTerminator (or GraXpert denoise as the open alternative) | denoised master |
| 4 | Star separation (optional) | StarXTerminator | starless master and stars-only master |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A stacked master comes out looking finished (Priority: P1)

The owner stacks a dataset (for example, the NGC 7000 OIII subs). Once integration is done, the master
automatically runs through the enabled steps. The dataset's master preview then shows the result of the last
step: gradients removed, stars tightened and noise reduced. A strip of thumbnails shows every stage, from the raw
master to the final result. Clicking any stage opens it at full size with the 100% view.

**Why this priority**: This is the request: a stack you can look at and enjoy straight away.

**Independent Test**: Install and license GraXpert and the RC-Astro tools on a worker, then stack a dataset with
the default chain. The master page shows four stages (master, background-extracted, deconvolved, denoised), each
with a preview. The headline preview is the denoised stage. The original master file is byte-identical to the
one integration wrote.

**Acceptance Scenarios**:

1. **Given** the chain is on with its default steps, **When** a master light finishes integrating, **Then** a
   post-processing job is queued for it and shown in Activity as "Post-process master · NGC 7000 OIII · 3 steps".
   Its progress shows which step is running.
2. **Given** post-processing has finished, **When** the owner opens the dataset, **Then** the headline preview
   is the last successful stage, labelled with its stage name. A stage strip lists each stage with its tool and
   duration.
3. **Given** any stage, **When** the owner opens it, **Then** it shows full size with the same stretched preview
   and 100% view as masters today. It can be downloaded as a linear 32-bit file.
4. **Given** post-processing is running, **When** the owner looks at the dataset, **Then** the raw master's
   preview is shown straight away, with a "post-processing: step 2 of 3 (deconvolution)" note. Nothing waits for
   the chain.

---

### User Story 2 - Configure or switch off the chain (Priority: P1)

In Settings → Processing, a "Master post-processing" section lets the owner:

- switch the whole chain on or off;
- switch each step on or off;
- change the step order within allowed limits;
- set each step's parameters, starting from sensible defaults.

Each tool also shows whether it is ready (installed, licensed, models present). If it isn't, a plain reason is
given, such as "BlurXTerminator: not licensed on this worker".

**Why this priority**: The owner asked for it to be configurable and disablable. Without this, US1 can't be tuned
or switched off.

**Independent Test**: Switch off deconvolution and stack a dataset. The stage strip shows master,
background-extracted and denoised only. Switch the whole chain off and stack again. Only the raw master is
produced, and no post-processing job is queued.

**Acceptance Scenarios**:

1. **Given** the chain is switched off, **When** a master integrates, **Then** no post-processing job is queued.
   The master page offers "Post-process this master" as a manual action.
2. **Given** a step's parameters are changed, **When** the next master is post-processed, **Then** the new
   values are used and recorded on the artefact. Existing artefacts are not re-run by themselves.
3. **Given** a tool isn't installed or licensed, **When** the owner opens the settings section, **Then** that
   step shows as unavailable with the reason and a link to the setup notes. It can't be switched on until its
   tool is ready.
4. **Given** any parameter, **When** the owner hovers or focuses it, **Then** a one-line explanation shows the
   allowed range and default.

---

### User Story 3 - Re-run the chain on an existing master (Priority: P2)

The owner changes the deconvolution strength, or licenses a tool they didn't have before, and wants to re-run the
chain on a master that already exists. They don't want to re-integrate the subs.

**Why this priority**: Integrations take a long time, while tuning post-processing is quick and iterative.

**Independent Test**: On an existing master, choose "Post-process again" with a changed noise-reduction amount. A
new set of stages is produced from the untouched master. The previous set is kept as an earlier run until it is
deleted.

**Acceptance Scenarios**:

1. **Given** a master with post-processed stages, **When** the owner re-runs the chain, **Then** a new run starts
   from the original linear master, never from an earlier run's output. The new run becomes the headline.
2. **Given** two runs on one master, **When** the owner views the stage strip, **Then** they can switch between
   runs. Each run shows its parameters and date.
3. **Given** an earlier run, **When** the owner deletes it, **Then** only that run's artefacts are removed. The
   master and other runs are untouched.

---

### User Story 4 - Starless and stars-only versions (Priority: P2)

With star separation on, the final stage is split into a starless image and a stars-only image. Both are shown in
the stage strip and can be downloaded, ready for nebula-only processing and recombination.

**Why this priority**: Narrowband work (the owner's NGC 7000 OIII/Ha/SII) relies on starless images. It's
optional, so it comes after the core chain.

**Independent Test**: Switch star separation on and post-process a master. The strip ends with "starless" and
"stars only". Combining them by screen blend visually reproduces the input stage.

**Acceptance Scenarios**:

1. **Given** star separation is on, **When** the chain finishes, **Then** a starless and a stars-only artefact
   exist. The headline preview stays on the last full stage (with stars), and a toggle shows the starless view.
2. **Given** a collection's combined palette master (spec 006), **When** it is post-processed with star
   separation, **Then** starless and stars-only colour versions are produced.

---

### User Story 5 - Per-dataset override when stacking (Priority: P3)

When starting a stack, the owner can use the global chain or override it for this dataset: skip it, or switch
individual steps on or off. This suits, for example, a galaxy where deconvolution should be gentler.

**Why this priority**: The global defaults cover most cases. Overrides are a refinement.

**Independent Test**: Start a stack with "post-processing: off for this dataset" while the global chain is on.
No post-processing job is queued for that master, and other datasets still get the chain.

**Acceptance Scenarios**:

1. **Given** the stack dialog, **When** the owner expands "Post-processing", **Then** it shows the current global
   chain with per-step switches. Changes apply to this dataset only and are remembered for its next stack.
2. **Given** a dataset with an override, **When** the owner views its master, **Then** the stage strip notes
   "dataset override" and lists the steps that differ from the global chain.

---

### User Story 6 - Collection and palette masters (Priority: P3)

A collection's combined or palette master (spec 006), and a mosaic master, can be post-processed the same way.
This happens automatically when the chain is on, or manually from the collection.

**Independent Test**: Build an SHO palette master for a collection and post-process it. The colour stages appear
on the collection's combined view.

**Acceptance Scenarios**:

1. **Given** the chain is on, **When** a collection's combined master is built, **Then** it is queued for
   post-processing like any master light.

### Edge Cases

- **Tool missing or unlicensed on the worker**: the step is skipped with a recorded reason, such as "skipped:
  NoiseXTerminator not licensed". The chain continues from the previous stage, and the master never fails because
  of post-processing.
- **A step fails mid-run** (crash, out of memory, timeout): that stage is marked failed with the tool's message,
  and later steps run on the last good stage. The run shows "finished with 1 failed step". The owner can retry
  only the failed step onwards.
- **No GPU on the worker**: the tools fall back to the CPU. The run notes "CPU" per step. Settings warns that a
  CPU run can take many minutes per master, and offers a per-step time limit.
- **Mono, colour (one-shot colour) and combined colour masters**: each step must accept the master's channel
  layout. Where a tool only supports one layout, the step is skipped with a reason rather than corrupting the
  image.
- **Very large masters (mosaics)**: steps run in tiles or with a memory cap set by the worker limits. Above the
  disk budget, the run is refused with the space needed shown.
- **Master rebuilt** (stale, new subs added): post-processing runs again on the new master, if the chain is on.
  Earlier runs stay attached to the master version that made them.
- **Licence expires or is revoked**: affected steps become unavailable at the next readiness check. Existing
  artefacts are kept.
- **Models not downloaded and the worker offline**: the step is unavailable with "models not downloaded". It is
  never fetched silently during a run.
- **Two workers with different tool setups**: a run is assigned to a worker that has every enabled step's tool
  ready. If no single worker does, the steps a worker can't do are skipped and the reason says so.
- **Disk budget**: post-processed stages count towards the intermediates budget and are deletable. The original
  master is never deleted to make room.

## Requirements *(mandatory)*

### Functional Requirements

**Chain and outputs**

- **FR-001**: After a master light (dataset, combined or mosaic) is integrated, the system MUST queue a
  post-processing run for it when the global chain is on, unless a dataset override says otherwise.
- **FR-002**: The system MUST never modify the integrated master. Every run MUST start from the untouched master,
  and each step MUST write a separate artefact.
- **FR-003**: Steps MUST run in the configured order, each taking the previous successful stage as input. The
  supported steps are:
  - background extraction (GraXpert);
  - deconvolution (BlurXTerminator);
  - noise reduction (NoiseXTerminator, or GraXpert denoise);
  - star separation (StarXTerminator, producing starless and stars-only).
- **FR-004**: Order MUST be constrained: background extraction before deconvolution, deconvolution before noise
  reduction, and star separation last. The settings UI MUST prevent orders that break these rules, and say why.
- **FR-005**: Every artefact MUST stay linear, 32-bit floating point, at the master's resolution and channel
  layout. The system MUST also produce a stretched preview and the 100% view, using the same stretch as master
  previews.
- **FR-006**: Each artefact MUST record:
  - its step;
  - the tool and tool version;
  - the model version where the tool reports one;
  - every parameter used;
  - whether GPU or CPU was used;
  - its duration;
  - the input stage it came from.

**Configuration**

- **FR-007**: Settings → Processing MUST provide:
  - a global on/off for master post-processing;
  - per-step on/off and parameters;
  - an option to keep or discard intermediate stages (default: keep).
- **FR-008**: Defaults MUST be conservative, and each MUST be shown with its allowed range:

  | Step | Parameter | Default | Range |
  |------|-----------|---------|-------|
  | Background extraction | Correction | subtraction | subtraction or division |
  | Background extraction | Smoothing | 0.1 | 0 to 1 |
  | Background extraction | Save background model | off | on or off |
  | Deconvolution | Star sharpening | 0.25 | 0 to 0.7 |
  | Deconvolution | Star halo adjustment | 0 | −0.5 to 0.5 |
  | Deconvolution | Non-stellar sharpening | 0.5 | 0 to 1 |
  | Deconvolution | Non-stellar radius | automatic | — |
  | Deconvolution | Correct only | off | on or off |
  | Noise reduction | Amount | 0.5 | 0 to 1 |
  | Star separation | Also produce stars-only | on | on or off |

  Noise reduction may have further detail options where the tool supports them. Changing a default MUST NOT
  re-run existing artefacts.
- **FR-009**: The stack action MUST allow a per-dataset override (off, or per-step on/off). The override is
  remembered for that dataset and shown on its masters.

**Tool readiness**

- **FR-010**: The system MUST check each tool's readiness on each worker: installed, version, licence activated,
  models present, and GPU or CPU. Readiness MUST be shown in Settings and on the Activity worker list.
- **FR-011**: A step whose tool is not ready on the assigned worker MUST be skipped with a plain reason. The run
  MUST continue, and a master MUST never be marked failed because of post-processing.
- **FR-012**: Licence keys, account emails and model files MUST be provided by the admin on the worker host
  (mounted or entered once and stored outside the repository and images). They MUST never appear in logs, the
  API or the UI beyond "licensed to d…@…". The proprietary RC-Astro tools MUST NOT be bundled in SubStation's
  published images.
- **FR-013**: Tool executables, model locations, GPU use and per-step time limits MUST be configurable per
  worker. The tools MUST work offline once activated and their models are downloaded.

**Running, re-running and viewing**

- **FR-014**: Runs MUST be queued jobs with step-level progress, priority below live calibration and
  integration, and resumable after a restart from the last completed step.
- **FR-015**: The owner MUST be able to start a run manually on any existing master ("Post-process this master" /
  "Post-process again"), optionally with one-off parameters. They MUST also be able to retry a failed run from
  its failed step.
- **FR-016**: The master view MUST show:
  - the headline preview (the last successful full stage);
  - a stage strip (each stage's thumbnail, tool, duration and status);
  - a starless toggle when one exists;
  - a run picker when several runs exist.
- **FR-017**: Each stage MUST open full size with the 100% view and offer a linear 32-bit download.
- **FR-018**: The owner MUST be able to delete a run, or an individual intermediate stage. Deleting MUST record
  who did it and when.
- **FR-019**: Stages MUST count towards the intermediates disk budget. If a run would exceed it, the run MUST be
  refused, with the space needed shown.

**Copy**

- **FR-020**: UI copy MUST follow the voice guide: it names the tools and what each step does, and never says
  "AI-powered" or "smart".

### Key Entities

- **Post-processing chain (settings)**: the global on/off switch, the ordered steps, each step's on/off and
  parameters, and the keep-intermediates choice.
- **Dataset override**: the dataset's chain choice (inherit, off, or per-step switches), remembered across
  stacks.
- **Tool readiness**: per worker and per tool. Records installed, version, licence state (no secret), models
  present, GPU or CPU, last checked, and the reason when not ready.
- **Post-processing run**: belongs to one master version. Records who or what started it, its state, its
  parameters snapshot, and when it started and finished.
- **Stage artefact**: belongs to a run. Records:
  - its step and kind (background-extracted, background model, deconvolved, denoised, starless, stars-only);
  - its input stage;
  - its file and preview;
  - the tool, version, model version, parameters, and GPU or CPU;
  - its duration;
  - its state (done, skipped, failed) and reason.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the default chain and tools ready, the dataset preview shows the final post-processed stage
  without any manual steps. On a worker with a supported GPU, this happens within 10 minutes of integration
  finishing for a single-panel master.
- **SC-002**: In 100% of runs, the original integrated master is byte-identical before and after
  post-processing.
- **SC-003**: Switching the chain off in Settings stops all new post-processing runs, with no restart needed.
- **SC-004**: With a missing or unlicensed tool, 100% of masters still complete. Each skipped step shows a reason
  the owner can act on.
- **SC-005**: Re-running the chain with changed parameters on an existing master needs no re-integration. On the
  same hardware, it takes no longer than the original post-processing run.
- **SC-006**: From any stage's record, the owner can tell exactly which tool, version and parameters produced it.
- **SC-007**: In a side-by-side review, the owner judges the headline preview of the NGC 7000 OIII master
  clearly better than the raw master's preview: gradients removed, stars tighter, background smoother.

## Assumptions

- **Constitution**: Principle IV ("all image processing MUST go through Siril … behind a single engine
  adapter") does not cover third-party post-processing tools. This feature needs a constitution amendment
  (MINOR, v2.1.0). The amendment adds a second, separate adapter boundary for optional external post-processing
  tools, with the same rules as Siril: pinned or recorded versions, one place that calls them, and contract tests
  against the real tool's help output. The plan MUST include that amendment. Siril stays the engine for
  everything before the master and for previews and stretches.
- **Licensing**:
  - GraXpert is GPL-3.0 and may be installed in the worker image.
  - The RC-Astro tools are proprietary and are licensed to the user. SubStation calls them as separate programs
    the admin installs, never bundled or linked, which keeps SubStation's GPL-3.0 dependency rule intact.
  - The user supplies their own RC-Astro licences. Existing PixInsight-version licences work with the
    stand-alone version, per RC-Astro.
- **Platform**:
  - The RC-Astro command-line tools are in beta and run on Linux (Ubuntu 22.04 or later; NVIDIA GPU, with a CPU
    fallback), Windows and macOS 14 or later.
  - The current NAS worker has no NVIDIA GPU, so the CPU fallback is the expected path there for now. A GPU or a
    Mac worker would be faster.
  - Beta behaviour may change, so the adapter pins the tested tool versions and reports a mismatch as a
    readiness warning.
- **Tool interfaces** (verified 2026-10-11 against their documentation):
  - GraXpert's command line takes the image, `-cli`, `-cmd background-extraction|denoising`, `-output`,
    `-correction Subtraction|Division`, `-smoothing 0–1`, `-bg`, `-strength 0–1`, `-batch_size`,
    `-gpu true|false` and `-ai_version`. It has no documented command-line deconvolution, so deconvolution uses
    BlurXTerminator.
  - The RC-Astro command line takes a product (`bxt`, `nxt`, `sxt`), files, `--output` and per-product options
    (for BlurXTerminator: `--sharpen-stars`, `--adjust-star-halos`, `--sharpen-nonstellar`,
    `--nonstellar-radius` / `--auto-nonstellar-radius`, `--correct-only`, `--engine`, `--depth 32F`). Activation
    uses `--activate <email> <key>`, and `download-models` prepares offline use.
  - Exact NoiseXTerminator and StarXTerminator option names are to be confirmed against `--help` during
    planning.
- **Formats**: both tools read and write FITS, TIFF and XISF. The chain exchanges 32-bit float FITS so that it
  matches the rest of SubStation (constitution: FITS orientation must be normalised explicitly).
- **Open alternative**: GraXpert denoise is offered as the noise-reduction tool for users without
  NoiseXTerminator. The default noise-reduction tool is NoiseXTerminator when ready, otherwise GraXpert.
- **Out of scope**:
  - non-linear finishing (stretching to a final image, colour calibration, curves, recombining starless and stars
    for publishing);
  - post-processing of calibration masters or individual subs;
  - any tools other than GraXpert and the RC-Astro three.
- **Builds on**: spec 004 (dataset stacking and master preview), spec 005 (queue, workers, Activity), spec 006
  (collection combined and palette masters) and spec 008 (Settings → Processing).

## Amendment 2026-10-13: post-processing runs on a helper, not the NAS

RC-Astro's tools saturate the NAS's CPU, while a Mac's GPU runs them in seconds. Post-processing therefore runs
on other machines, and SubStation says so when none is connected.

- **010-DR-20**: Post-processing jobs are taken by **helpers**: a program on a faster machine that asks
  SubStation over HTTPS for the next master (token auth, `SUBSTATION_HELPER_TOKEN`), downloads it, runs the chain
  with its native tools, uploads each stage and reports done. SubStation draws previews, 100% views and
  measurements as before. The NAS runs no post-processing.
- **010-DR-21**: On macOS the helper runs natively, not in Docker: containers on macOS can't reach the Apple GPU,
  and RC-Astro uses CoreML natively. Its licence is the machine's own activation.
- **010-DR-22**: A master whose post-processing is queued with no helper connected says so, with when a helper was
  last seen. Helpers heartbeat through progress every 30 s; a silent helper's job goes back in the queue.

### Same helper, in a container (2026-10-13)

The helper is one program. On a Mac it runs natively (Docker on macOS can't reach the Apple GPU); on Linux it runs
in the finisher image as `entrypoint.sh helper`, which needs no database or library, only `SUBSTATION_URL` and
`SUBSTATION_HELPER_TOKEN`. `docker/compose.helper.yml` is the example (NVIDIA GPU passed through; RC-Astro unpacked
onto a volume and activated there, with a stable hostname and MAC address so the activation sticks). Any number of
helpers may run; each takes one job at a time. A job a helper drops (restart, crash) goes back to the queue up to
three times.

### A helper reports like a worker (2026-10-13)

A helper sends its CPU and memory, and those of the tool it's running, every 10 s with its progress (and with each
idle request for work). Activity shows it as a worker tile named after the machine, with the same CPU/RAM graph,
the tool's own share ("RC-Astro 400% · 3 GB") and the tool's command line. CPU is measured from the processes'
CPU time, so 100% is one core; work the tool hands to the GPU or Neural Engine doesn't show as CPU. Cancelling a
job in SubStation stops the running tool within about 10 s instead of after it finishes.

### Dropped connections (2026-10-13)

A helper retries a request whose connection drops (up to four tries, waiting longer each time); a refusal from
SubStation is final. A job a helper reports as failed goes back in the queue while it has attempts left, with the
reason kept, and only fails once they are used up.

### Colour stages keep a neutral sky (2026-10-14)

Stages are still drawn with the master's stretch (same strength and range, so versions compare fairly), but each
colour channel's black point moves with that stage's own sky level. GraXpert removes a light-pollution glow
(strongest in green); drawn against the master's old green black point, OSC stages came out purple. Existing
stages are redrawn; the stage files themselves were right and aren't processed again.
