# Plan: Sub grading and review (POC: story 1; stories 2–3 without blink review)

**On arrival** (`processing.calibrate_measure`, one per matched light, light slot, a long-lived Siril
process per worker): stage the sub, convert XISF to FITS, `calibrate_single -dark -flat -cc=dark`,
then on the calibrated sub `findstar -out=` (star list), `bgnoise`, `stat`. Measurements: star count, median
FWHM (px and arcsec from XPIXSZ and FOCALLEN), roundness (median FWHMy/FWHMx), background (median),
noise (bgnoise), FOCPOS and FOCTEMP. The calibrated FITS is kept in the work area for stacking.

**Grading** (`processing/grading.py`, pure Python, recomputed for the dataset-night on each new
measurement): night medians of wFWHM, stars and background; wFWHM as Siril defines it
(`FWHM + 2·FWHM·(Nref − N)/Nref`, Nref the night's highest star count). Reject: wFWHM > 1.5× median,
stars < 0.6× median, background > 2× median, roundness < 0.85, or no stars. Down-weight: wFWHM above
1.2× median, weight `(median/wFWHM)²`. Fewer than 5 subs in the night: provisional. Reasons in the voice
guide's form with the measurement, the comparison and the likely cause. Thresholds are settings with a
version number. Registration failure is recorded at stack time (spec 004).

**Effective verdict**: latest human verdict (NINA BAD_ or override) if any, else the machine grade.
Overrides by keyboard (A, W, R) on the dataset table, recorded with user and time.

**UI**: the dataset view gains the night chart (FWHM, stars, background over the night, rejected and
down-weighted marked, FOCPOS alongside), metrics columns (verdict, FWHM, stars, background, weight,
reason) and override keys. The dashboard shows accepted, down-weighted and rejected counts, tonight's
accepted, and the "Awaiting calibration" state with its note.
