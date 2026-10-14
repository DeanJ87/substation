# Feature Specification: Queue and workers console

**Feature Branch**: `005-queue-workers-console`

**Created**: 2026-10-09

**Status**: Draft

**Input**: Scope: the queue is shown in the UI so it's clear what the workers are doing: each job, each worker
process, CPU% and RAM%, whether there are ten processes or Siril is stacking two sets at once. Source: owner feedback 2026-10-09; constitution VII.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See what SubStation is doing right now (Priority: P1)

The user opens the Queue screen and sees every running job (what it is, which dataset or files, which
worker, progress, elapsed time), what is waiting (by priority: live, bulk, archive, stacking), and recent
completions and failures.

**Why this priority**: with bulk ingests and long stacks, the user must be able to see that work is
moving and why something has not happened yet.

**Independent Test**: Drop the 653-file phase 2 tree in while a stack runs; the Queue screen shows the
stack's progress, the hashing and cataloguing backlog with an estimate, and live subs jumping ahead.

**Acceptance Scenarios**:

1. **Given** jobs running and waiting, **When** the Queue screen opens, **Then** each running job shows
   its type (hash, catalogue, convert, calibrate, measure, grade, register, stack, preview, QA), its
   target, worker, progress and elapsed time, and waiting jobs are grouped by priority with counts and an
   estimated completion time.
2. **Given** a job fails, **When** viewed, **Then** it shows the reason in the voice guide's form, its
   attempts, the engine log excerpt, and Retry and Cancel.
3. **Given** the dashboard, **When** jobs are queued, **Then** a compact queue indicator ("Queue 2,
   awaiting calibration" as in the design) links to the Queue screen.

---

### User Story 2 - See how hard each worker is working (Priority: P1)

For each worker and each Siril process the user sees CPU%, RAM (used and % of its limit), current
command and uptime, and for the whole system, total CPU, RAM, disk used by intermediates against the
budget, and free disk.

**Why this priority**: the owner runs this on shared hardware and needs to tune it.

**Independent Test**: During a stack, the stack's Siril process shows its rising RAM and high CPU while an
idle worker shows near zero; figures update at least every 2 seconds and match the host's own tools within
5 percentage points.

**Acceptance Scenarios**:

1. **Given** workers running, **When** the screen is open, **Then** per-process CPU% and RAM update live,
   with a short history (last 15 minutes) per worker.
2. **Given** intermediates near the disk budget, **When** shown, **Then** the budget bar warns and explains
   which jobs are waiting for space.

---

### User Story 3 - Scale and steer the workers (Priority: P2)

An admin sets how many workers run (for example from 1 to 10), how many may run Siril-heavy jobs
(stacking, master building) at the same time, and per-worker limits. Two stacks can run in parallel on
different workers. The admin can pause and resume the queue, cancel a job, or raise one to the front.

**Why this priority**: tuning matters once the basics work.

**Independent Test**: Set 4 workers with 2 stacking slots; start stacks of two datasets; both run at once on
different workers while ingest continues on the others.

**Acceptance Scenarios**:

1. **Given** the worker count is raised, **When** saved, **Then** new workers start without a restart of
   the service and appear on the screen.
2. **Given** the worker count is lowered, **When** saved, **Then** surplus workers finish their current job
   and stop; no job is lost.
3. **Given** two stack jobs and two stacking slots, **When** queued, **Then** both run concurrently on
   separate Siril processes.
4. **Given** a paused queue, **When** resumed, **Then** waiting jobs continue in priority order.

### Edge Cases

- A worker or Siril process crashes: its job is retried (up to a limit) and the crash is shown with the
  log excerpt.
- Memory limit reached: the job fails with a plain explanation rather than taking the host down.
- Restart of the whole stack: running jobs are re-queued, not marked done.
- Many workers contending for the catalogue: the console still updates without stalling ingest.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show running, waiting (by priority), completed and failed jobs, with type,
  target, worker, progress, elapsed time, attempts and estimated completion.
- **FR-002**: System MUST show per-worker and per-Siril-process CPU%, RAM used and % of limit, current
  command and uptime, updated at least every 2 seconds, with 15 minutes of history.
- **FR-003**: System MUST show system totals: CPU, RAM, intermediate disk use against the budget, and free
  disk on the work area.
- **FR-004**: Admins MUST be able to set the worker count (1 to at least 10), the number of concurrent
  Siril-heavy slots, and per-worker resource limits, applied without a full restart.
- **FR-005**: Admins MUST be able to pause and resume the queue, cancel or retry a job, and move a job to
  the front.
- **FR-006**: Independent Siril-heavy jobs (for example two stacks) MUST be able to run in parallel on
  separate Siril processes.
- **FR-007**: Failed jobs MUST show a plain-English reason and the relevant engine log excerpt.
- **FR-008**: Queue and worker views MUST follow the design system and update live without a page reload.

### Key Entities

- **Job**: type, target, priority, state, worker, progress, attempts, timings, result or error.
- **Worker**: process, state, current job, resource limits, resource samples.
- **Engine process**: a Siril pipe-mode process owned by a worker, with its own resource samples.
- **Resource sample**: CPU%, RAM, at a time, for a worker, engine process or the system.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Live figures on the Queue screen refresh within 2 seconds and agree with host tools within 5
  percentage points.
- **SC-002**: Changing the worker count takes effect within 10 seconds with no lost or duplicated jobs.
- **SC-003**: Two stacks run concurrently with ingest still meeting spec 001's 10-second limit, given
  enough CPU.
- **SC-004**: A user can tell why any waiting job has not started (priority, slots full, waiting for
  calibration, waiting for disk) from the Queue screen.

## Assumptions

- Resource figures are for SubStation's own processes inside its containers.
- Only admins change worker settings; all users can view the queue.
- Later visualisations (SNR over time, animated progression of a dataset) are on the roadmap, not here.

## Amendment 2026-10-10: v2 design (docs/design/v2, A1)

The Queue screen is **Activity**: "6 workers · 3 jobs running · 9 queued", Pause new work, Worker settings;
readouts CPU (threads, workers), Memory (used of total), Disk (write rate on /data/substation) and Intake
(watching N folders, last file time); **Running** jobs as cards with their pipeline steps and progress, the
workers on them (W1…), time left and the last log lines; **Workers** as tiles (state, job, file, progress);
**Queue** in order, reorderable; **Recent** completions with failures pinned on top until retried or
dismissed, in plain English ("Couldn't write the SII master … Subs and grades are safe." Retry).

## Amendment 2026-10-10: design review

From the full design review (`docs/design/design-review.md`, sections B–D): every SubStation design file and the brand guidelines were checked against the build. These requirements add to the ones above; where the design files disagree, the decisions in spec 007 apply.

1. **005-DR-01**: Activity MUST be the only queue screen. The header's Activity badge and the Library's Processing
   readout MUST link to it, and the legacy `/queue` page MUST redirect to it.
2. **005-DR-02**: Each running job card MUST show:
   - every worker on the job as chips (W1…);
   - the estimated time left ("≈ 9 min");
   - Cancel;
   - a link to the dataset;
   - the last three log lines in mono with timestamps.
3. **005-DR-03**: Each worker row MUST show its state as a verb ("Solving", "Normalising", "Idle"), its job, the file
   in progress, CPU% and the 15-minute history.
4. **005-DR-04**: The queue MUST be reorderable by drag and by keyboard, and MUST show an estimate for each waiting
   item.
5. **005-DR-05**: Recent completions MUST read as outcome sentences ("Graded 24 subs · Askar 71F · Hα · 7 Oct · 19
   accepted, 2 weighted, 3 rejected") with their duration.
6. **005-DR-06**: The Activity readouts MUST be:
   - CPU (threads and workers);
   - Memory (used of total, with the integration buffer);
   - Disk (write rate on /data/substation);
   - Intake (Watching, folder count, last file time).
   Each readout MUST have a meter.
## Amendment 2026-10-11 (owner): a calmer Activity page

- **005-DR-07 Sections fold.** Workers, Running, Queue and Recent collapse; the choice is remembered.
- **005-DR-08 Long lists scroll in place.** Queue and Recent scroll inside their card and load 50 more as they
  scroll (`GET /work/queue`, `GET /work/recent` with offset and limit); the queue's make-up is chips by kind with
  the time to clear in the header.
- **005-DR-09 Run next says what happened.** "Run next" (was ↑) confirms the move, since a short job then runs
  and leaves the queue at once.
- **005-DR-10 Workers named and explained.** A tile is named by container and slot (C2·1); hovering shows the
  whole job, its start and the Siril command; a click unfolds it. The disk readout is labelled rows (free, work,
  cache, stacking), not a sentence.
- **005-DR-11 Intake is honest.** The watcher renews its lease on its own thread, so a long sweep no longer lets it
  lapse (it read "Not watching" while sweeping, and another worker could start a second sweep).
- **005-DR-12 The flyout stays inside itself.** Running jobs in the header flyout are one line each (long file
  names end in …, full text on hover), at most six with "and N more on Activity".
- **005-DR-13 A busy database doesn't drop the watcher.** "database is locked" while renewing the lease is retried
  quietly; the lease is only given up once it has really expired.
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
- **005-DR-20** (2026-10-13): A worker or the watcher that finds the database locked waits and tries again; it never
  exits over it (an exit restarted every worker and orphaned a running stack). A stacking-slot task is only taken
  back after 15 minutes without a heartbeat (light tasks: 2), so a disk stall can't make a running stack look dead
  and start a second one beside it.
- **005-DR-21** (2026-10-13): Activity names what a job works on first: the collection's common name (else the
  dataset's target), then rig and filter ("Soul Nebula · Askar 71F + ATR2600M · SII · v1"). A running stack also
  says who or what started it and with which subs ("queued by admin 13 Oct 08:25 · accepted and down-weighted subs",
  or "started automatically …").
- **005-DR-22** (2026-10-14): A stack's recalibrated subs live in its own working folder, never the shared cache
  (the cache's pruning took them mid-stack and seven stacks failed); the cache never prunes a file used in the last
  3 hours. A FITS Siril only links when converting is copied, never moved as a link, and a linked frame is replaced,
  never written through, so nothing can change a file in an image library.

## Amendment 2026-10-14: updates without scripts

Deploys used scripts on the owner's Mac that logged in to the NAS over SSH to pause the queue, wait for stacks and
restart containers. One hung for eight hours on an SSH call. SubStation now updates itself.

- **005-DR-23**: Every 10 minutes the API container asks GitHub for the newest successful image build of the branch
  it runs (`SUBSTATION_UPDATE_REPO`). When that build is newer than the running one and automatic updates are on
  (Settings → Workers → Updates; on by default), it pauses the queue, waits until no stack or master build is
  running, then calls the stack's Portainer webhook (`SUBSTATION_UPDATE_WEBHOOK`) naming the build
  (`SUBSTATION_TAG=<short commit>`). When the new version starts, the queue resumes, unless it had been paused by
  hand. If the new version isn't running 20 minutes later the update is marked failed with the reason, the queue
  resumes, and that build isn't tried again by itself. "Update now" and "Don't update now" do the same by hand.
  Without both variables updates are off and say so. Nothing logs in to the NAS.
