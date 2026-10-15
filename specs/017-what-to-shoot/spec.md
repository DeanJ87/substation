# Feature Specification: What to shoot

**Feature Branch**: `poc-substation`
**Created**: 2026-10-15
**Status**: Built 2026-10-15
**Input**: Owner approval, 2026-10-15 (site review item 1): a calibration shopping list page, with the darks
exportable to NINA. Flats are listed but never scheduled: they depend on the rig as it was on the night.

## User scenarios

1. **What would unlock the most.** Calibration → What to shoot lists the darks (by camera, exposure, gain, offset,
   binning, size and set temperature) and biases that would release subs waiting for calibration, biggest first,
   with the subs and integration each would release and the datasets they belong to.
2. **Shoot the darks.** The owner sets frames per row (default 30) and downloads a NINA sequence of those darks
   and biases, coldest first, each row noting its temperature; or a CSV of everything.
3. **Flats.** Flats are listed by rig, filter and the nights they're for, with a note that they must match the
   rig as it was then.
4. **Not a shooting problem.** Lights waiting on something else (a master still being built, a value to confirm in
   Reconcile) are listed with their reason.

## Requirements

- **FR-001** Built from the lights waiting for calibration and the reason recorded for each; a light needing both
  a dark and a flat counts toward both.
- **FR-002** A dark row's temperature is the lights' set point (else their sensor temperature, rounded); an
  uncooled camera's is "uncooled".
- **FR-003** The NINA file is the simple sequencer's target file (CaptureSequenceList): image type DARK or BIAS,
  exposure, gain, offset, binning and count per row. Cooling isn't part of that format, so rows are ordered
  coldest first and each carries its temperature in a comment.
- **FR-004** Frames per row: 1–500.

## Assumptions

The NINA import format is the simple sequencer's XML target file; if NINA's current version doesn't import it, an
Advanced Sequencer export follows (to be confirmed with the owner's NINA).

### Amendment 2026-10-15

- **017-DR-01** Only lights still in the library count (catalogued, in a dataset): binned or ignored subs kept their
  old "waiting" record and showed as rows with no datasets (385 binned second-Hα subs). The list takes the shared
  scope (spec 018), so the NINA file can be for one rig, filter or date range.

