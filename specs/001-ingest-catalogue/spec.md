

- **001-DR-11 Already-processed copies are not subs.** A light that PixInsight (or anything leaving FITS HISTORY
  ImageCalibration/StarAlignment/Debayer lines) has already calibrated, registered or debayered is classified
  "processed", not "light", so WBPP's calibrated/_c and registered/_r copies don't double a night's subs or skew its
  stretch. (Owner 2026-10-11.)

## Amendment 2026-10-13: 8-bit captures are set aside

Early Sony A7 III files were saved as 8-bit RGB and are of no use for calibration or stacking. Any catalogued file whose image is 8-bit (BITPIX=8 or UInt8), whatever
its type (light, flat, dark), gets its own content ignore rule noted "8-bit capture: camera-processed data, not raw".
It leaves its dataset and calibration, shows in Settings → Ignored, and can be undone there. Nothing is deleted;
the files stay where they are for the owner to remove. New 8-bit files are set aside when catalogued. (The library
held 326, all Sony A7 III: 118 lights, 157 flats, 51 darks.)

## Amendment 2026-10-13: no site details in the repository

The repository holds nothing specific to one installation: no host names, domain names, user names or storage
paths. `docker/compose.nas.yml` takes them as required stack variables (`SUBSTATION_DOMAIN`, `SUBSTATION_STATION`,
`SUBSTATION_CATALOGUES`, `SUBSTATION_LIBRARY`, `SUBSTATION_ARCHIVE`), so a missing one stops the deploy rather than
starting on an empty folder; `docker/nas-prepare.sh` takes `NAS`, `ROOT` and `CATALOGUES`; the post-processing
helper needs `--url` or `SUBSTATION_URL`.
