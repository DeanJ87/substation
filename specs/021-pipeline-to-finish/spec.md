# Feature Specification: Pipeline to a finish-ready image

**Feature Branch**: `021-pipeline-to-finish`

**Created**: 2026-10-24

**Status**: Draft

**Input**: User description: "SubStation is the one-stop pipeline that takes a target from raw subs to a linear, calibrated, cleaned image ready to pull into PixInsight (or any finisher) for the creative work; define the whole pipeline as named stages with a clear hand-off point, and fill the gaps (colour calibration, a clean-up chain on combined images, export)."

This spec is the umbrella over the processing specs. It orders what already exists (004 dataset stacking, 010 master post-processing, the combined-master work in 004, 020 finished projects) into one pipeline with a defined end, and adds what is missing: colour calibration, a clean-up chain on combined colour images, a choice of steps per run, and a hand-off export. Stretching and creative processing stay with the owner's finishing software.

## The pipeline

| Stage | Works on | What happens | Status |
|---|---|---|---|
| 1. Subs | each sub | calibrate, measure, grade | exists |
| 2. Master | one dataset (one filter, one field) | stack at normal resolution, drizzle ×2 or bin 2×2 | exists; resolution choice being added |
| 3. Master clean-up | each master, linear | crop the stacking edges; background extraction; optionally deconvolution per channel | exists (all steps run together); per-run choice added here |
| 4. Assembly | masters of one filter | stack together (same field, more data) and/or stitch a mosaic (chosen filters), one linear image per filter on a shared canvas | exists; filter choice being added |
| 5. Colour | the filters of a project | combine into RGB, LRGB, HOO, SHO, or keep OSC as it is, aligned pixel for pixel | partly exists (palette previews); a real combined image is added here |
| 6. Colour calibration | the combined colour image | spectrophotometric colour calibration against a star catalogue; optional narrowband white balance | new |
| 7. Finishing clean-up | the combined colour image | deconvolution (unless done per channel), noise reduction, optional star removal into starless and stars-only images | new for combined images |
| 8. Hand-off | the chosen stage | linear 32-bit files plus a record of every step, ready to open in the finishing software | new |

Mono data runs stage 3 per filter (background extraction by default) and stages 6–7 once on the combined image. Colour (OSC) data is already colour, so it runs the whole chain on its master.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Narrowband project to a finish-ready image (Priority: P1)

The owner has Hα and OIII masters for a single-field target. They clean each master (background extraction), combine them into an HOO image, run deconvolution and noise reduction once on that colour image, and export the result to open in their finishing software, linear and unstretched, with a note of every step.

**Why this priority**: this is the most common path for the owner's data and the core promise: from subs to a file ready for the creative work, without hand work in between.

**Independent Test**: on a project with Hα and OIII masters, produce an HOO image, clean it, export it, and open the export in a finishing program: it is linear, 32-bit, the channels line up, and the record lists the steps.

**Acceptance Scenarios**:

1. **Given** Hα and OIII masters in one project, **When** the owner combines them as HOO, **Then** one linear colour image is made with each channel aligned pixel for pixel, and each master's clean-up (if run) is the input used.
2. **Given** a combined HOO image, **When** the owner runs the finishing clean-up with deconvolution and noise reduction on, **Then** each step's result is shown with a preview and stats, and the original combined image is unchanged.
3. **Given** a cleaned combined image, **When** the owner exports it, **Then** they get a linear 32-bit file in the chosen format, named after the target, project and stage, plus a record of every step and setting from the subs onwards.

---

### User Story 2 - Choose the steps per run (Priority: P1)

For any master or combined image, the owner turns steps on or off for that run (for example background extraction only on a mono master, or background extraction and deconvolution), without changing the steps' settings.

**Why this priority**: doing the right step at the right stage (background extraction per master, colour steps after combining) is impossible if every run applies every enabled step.

**Independent Test**: run a mono master with only background extraction on; check only that stage exists in the result, and that the next run defaults to the site setting again.

**Acceptance Scenarios**:

1. **Given** the available steps, **When** the owner starts a run, **Then** they see each step as on/off, defaulting to the site setting for that kind of image (mono masters: background extraction only; colour images: the full chain).
2. **Given** a choice of steps, **When** the run finishes, **Then** only the chosen steps ran, with the site settings for each, and the run records which steps were chosen.

---

### User Story 3 - Colour calibration of colour images (Priority: P2)

The owner calibrates the colour of an RGB, LRGB or OSC image against a star catalogue, using the camera and filters they shot with, so star colours are true without hand balancing. For HOO/SHO they can apply a narrowband white balance or skip it.

**Why this priority**: accurate colour is the step that most often sends people to their finishing software early; doing it here makes the hand-off image ready for creative work.

**Independent Test**: on an OSC master and on an LRGB combined image, run colour calibration and check the result's star colours against the catalogue's (the report shows how many stars were matched and the correction applied).

**Acceptance Scenarios**:

1. **Given** a plate-solved colour image and the rig's camera and filter profile, **When** colour calibration runs, **Then** the image's colour is corrected and the report says how many catalogue stars were used and the correction factors.
2. **Given** a rig with no camera or filter profile chosen, **When** the owner tries to calibrate, **Then** they are asked to choose the profile once for that rig, and nothing runs until they do.
3. **Given** an HOO or SHO image, **When** the owner runs colour calibration, **Then** it uses the narrowband mode with the filters' wavelengths, or they can switch it off for that image.
4. **Given** a mono single-filter master, **Then** colour calibration is not offered (it needs a colour image).

---

### User Story 4 - Mosaic through the same pipeline (Priority: P2)

For a mosaic, each panel master gets background extraction, the panels of each chosen filter are stitched onto one shared canvas, the filters are combined into colour, and the colour, clean-up and export stages run once on the whole mosaic.

**Why this priority**: per-panel gradients must be removed before stitching for seamless joins, and whole-image steps (colour, deconvolution, noise) must run once so the mosaic is consistent.

**Independent Test**: on a 2-panel Hα/OIII mosaic, run the pipeline end to end and check the seams, the shared canvas, and that colour and clean-up ran once on the whole image.

**Acceptance Scenarios**:

1. **Given** cleaned panel masters, **When** the owner stitches chosen filters, **Then** each filter's mosaic is built from the cleaned panels on one canvas shared by every filter.
2. **Given** stitched filters, **When** combined and cleaned, **Then** colour calibration, deconvolution and noise reduction run once on the whole mosaic, not per panel.

---

### User Story 5 - Re-run any stage from its input (Priority: P3)

The owner changes a step at any stage (for example a different noise-reduction choice) and re-runs only that stage and the ones after it, from the stage's saved input, without re-stacking or re-cleaning earlier stages.

**Why this priority**: iteration on the late stages is common, and redoing early stages costs hours.

**Independent Test**: re-run the finishing clean-up on a combined image and confirm the masters and the combined image itself were not rebuilt.

**Acceptance Scenarios**:

1. **Given** a finished pipeline, **When** the owner re-runs stage 7, **Then** stages 1–6 are reused as they are and a new stage-7 result is added beside the old one, both kept until the owner removes one.
2. **Given** an earlier stage that has changed (a new master version), **Then** later stages that used the old version are marked out of date, with what changed, and offer to re-run.

### Edge Cases

- A project mixes rigs with different pixel scales: assembly and colour combine onto the reference canvas (resampled), and the record says which inputs were resampled.
- One filter is missing for the chosen mapping (SHO with no SII): the combine is refused with which filter is missing, or the owner picks a mapping the data supports.
- Colour calibration finds too few catalogue stars (small field, heavy nebula, no plate solution): it fails with that reason and the image stays uncalibrated; later stages can still run.
- The star catalogue is not available offline and the site has no internet: colour calibration says so and offers the online catalogue setting or a local download.
- A drizzled master and a normal master of the same filter: they are not stacked together without the owner choosing to resample; the reason is shown.
- Star removal on a colour image: produces starless and stars-only images; both are exported if chosen.
- An OSC image from a smart telescope with its own processing artefacts (e.g. mosaic edges): the crop step still applies before calibration.
- Very large mosaics: each stage checks memory and disk first and refuses plainly rather than crashing (as for masters).

## Requirements *(mandatory)*

### Functional Requirements

- **021-FR-001** The pipeline has eight named stages (table above). Every image SubStation makes says which stage it is and which inputs and versions it came from.
- **021-FR-002** For any master, assembled image or combined image, the owner can start a clean-up run choosing each available step on or off; the run uses the site settings for each step and records the choice. Automatic runs use the site defaults.
- **021-FR-003** Site defaults per kind of image: mono masters run background extraction only; colour masters (OSC) and combined colour images run the full chain (background extraction where not already done, colour calibration, deconvolution, noise reduction; star removal off by default). Deconvolution can instead be set to run per mono master ("per channel"), in which case it is off for the combined image.
- **021-FR-004** Assembly uses each input's latest clean-up result when one exists (else the master as stacked), and says which it used.
- **021-FR-005** The owner can combine a project's filters into a colour image with a chosen mapping (RGB, LRGB, HOO, SHO, OSC as is), with sensible defaults from the filters present. The result is a linear colour image whose channels line up pixel for pixel, on the shared canvas for mosaics.
- **021-FR-006** Colour calibration runs on a plate-solved colour image against a star catalogue, using the camera sensor and filter profile chosen once per rig; narrowband mode with the filters' wavelengths for HOO/SHO, which the owner can switch off per image. It reports the stars matched and the correction applied. It is not offered for single-filter mono images.
- **021-FR-007** The finishing clean-up on combined images runs deconvolution, noise reduction and optional star removal (starless and stars-only outputs), in that order after colour calibration, each with previews and stats like master clean-up.
- **021-FR-008** Any stage's result can be exported as a linear 32-bit file in the owner's chosen format, named from target, project, stage and version, together with a readable record of every step and setting from the subs to that stage. Exports go to SubStation's own export area (never into the owner's source folders); the owner can open them in place or download.
- **021-FR-009** Re-running a stage reuses earlier stages as they are and keeps the previous result beside the new one until removed. When an input changes, later stages that used it are marked out of date with the reason.
- **021-FR-010** Every stage checks memory and disk before starting and refuses with a plain reason when it would not fit.
- **021-FR-011** The pipeline view shows, for a project, each stage's latest result per filter or image, its state (done, out of date, failed with reason, not started) and the next sensible action.

### Key Entities

- **Stage result**: an image at one stage, with its inputs (and their versions), the steps and settings applied, previews, stats and state.
- **Clean-up run**: one run of chosen steps on one image, recording the choice and each step's result.
- **Colour image**: a combination of filters under a mapping, on a shared canvas.
- **Rig colour profile**: the camera sensor and filters used for colour calibration, chosen once per rig.
- **Export**: a linear file of one stage result plus its processing record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **021-SC-001** From finished masters, the owner gets an exported, cleaned, colour-combined linear image of a single-field narrowband target in no more than five actions in the app.
- **021-SC-002** An exported file opens in a common finishing program as linear 32-bit data with correct channel order, and its record lists every step from the subs onwards.
- **021-SC-003** Re-running the last stage does not rebuild any earlier stage (no master, assembly or combine work is repeated).
- **021-SC-004** On a 2-panel mosaic, the stitched seam shows no step in background level larger than the image's noise after per-panel background extraction.
- **021-SC-005** Colour calibration on an OSC master of a star field matches at least 100 catalogue stars or explains why not.

## Assumptions

- The owner's finishing software reads linear 32-bit FITS and XISF; both are offered.
- The existing tools stay the engines: the stacking engine for stacking, stitching and colour calibration; the existing external finishing tools for background extraction, deconvolution, noise reduction and star removal.
- Colour calibration needs plate-solved images (masters are already solved) and a star catalogue, online or downloaded once; the download is the owner's choice.
- Stretching, curves, colour grading and other creative work are out of scope; the hand-off is linear.
- Existing master post-processing (010) becomes stage 3 for masters; combined-master post-processing becomes stage 7; nothing already produced is lost.
