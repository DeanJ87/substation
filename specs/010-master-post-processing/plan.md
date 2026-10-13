# Plan: Master post-processing (spec 010)

**Date**: 2026-10-12 · **Spec**: [spec.md](spec.md)

## Approach (MVP, owner 2026-10-12)

- `backend/apps/processing/postprocess.py` is the single adapter for the external finishing tools (GraXpert,
  RC-Astro `rc-astro bxt|nxt|sxt`): readiness (installed on this worker), command lines from the documented
  flags, `run_chain` (each step on the last good stage; skipped with a reason when the tool is missing; failed
  steps don't stop the chain), and the queued task `postprocess_master` (stack queue).
- Runs are stored on the master (`Master.report["post_runs"]`): per stage the tool, parameters, time, state,
  reason and preview. No schema change; the master file is never touched (each run writes `<master>_postN/`).
- Settings: `processing.post` (global on/off, ordered steps with parameters, GPU, tool paths, time limit),
  editable in Settings → Processing → Master post-processing.
- `integrate` queues the chain when it's on (or a dataset override says so).
- API: `GET/POST /stacks/{id}/post`, `GET /stacks/{id}/post/{run}/{stage}/preview`.
- UI: a stages strip under each master (thumbnail, tool, seconds or reason), "Post-process this master / again".

## Constitution Check

- **IV. One Engine, One Boundary**: amended (v2.1.0) to allow a second, separate adapter boundary for optional
  external finishing tools; `postprocess.py` is that boundary, with command-line tests.
- **I. Originals Read-Only / derived data**: stages live beside the master under `/data/substation`; the master is
  untouched (tested).
- **III. Every Decision Explained**: every skipped or failed step carries its reason.
- **Governance (GPL-3.0 deps)**: RC-Astro's tools are proprietary programs the admin installs and licenses; they are
  called as separate processes, never bundled in images. GraXpert is GPL-3.0.

## Deferred

- Installing GraXpert / RC-Astro in the worker image or as a sidecar (admin step for now; paths in settings).
- Per-dataset override UI in the stack dialog (the backend reads `report.post_override`).
- Collection combined/palette masters, run picker, per-stage delete, readiness shown from the worker in Settings.
