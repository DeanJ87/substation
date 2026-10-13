# Plan: Calibration library (POC: story 1 matching; story 3 building masters from raw sets)

New app `apps/processing` holds per-light processing state; `apps/engine` is the only Siril caller.

**Matching** (`processing/matching.py`), from resolved metadata only (spec 001), masters only:
- Dark: master dark with exactly the light's exposure, same gain, offset, binning and camera, and
  temperature (master SET-TEMP, else CCD-TEMP) within ±2 °C of the light's CCD-TEMP (configurable).
  Among several, the closest temperature, then the newest.
- Flat: master flat with the same filter (case-insensitive, normalised), camera and binning, whose
  night (or DATE-OBS) is on or before the light's night; the latest such. Fallback "nearest later flat"
  is a setting, off by default.
- A master missing a value the rule needs is skipped; if that leaves no match, the light waits with the
  reason naming what's missing ("Awaiting calibration: no Hα flat on or before 28 Sep"; "the −20 °C 600 s
  dark has no gain: confirm it in Reconcile").
- `CalibrationMatch` (one per light): dark, flat, state (`matched`, `awaiting`), reason, rule text, the
  source of every value used. Re-matched when a light is (re)catalogued, a master is added or changed, or
  calibration settings change. A changed match on an already-calibrated light marks it for re-calibration
  only after the user accepts (POC: listed, not automatic).

**Building masters** (story 3, basic): for a raw set with no master yet, a `build_master` job (heavy slot):
dark flats and bias → `stack rej 3 3 -nonorm`; flats → calibrate with the matching master dark flat (or
bias) then `stack rej 3 3 -norm=mul`. The result is written to `/data/substation/masters/` and catalogued
as a master built here (provenance: set, frames, method, engine version). QA contact sheets (story 2) are
not in the POC; the truncated-readout check from the spike runs before building and excludes such frames.
