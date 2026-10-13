

- **002-DR-14 Wait for a closer flat.** While a flat set from a light's own night (or nearer than the best built
  flat) is still queued or building, the light waits ("waiting for the 11 Oct OIII flats to be built") instead of
  taking an older flat. Subs already calibrated with another flat are re-calibrated automatically once a flat from
  their own night exists; other newer-calibration cases still wait for the owner (002 C11). (Owner 2026-10-11.)

## Amendment 2026-10-12: choosing a flat is a table of your filter's flats

The card grid of every flat ("Flats OIII", "Flats SII", "Flats G" for an Hα session, many with no picture) made
picking a flat slow: the session's own filter should come first, in a table, with a preview on hover.

- **002-DR-16**: Change opens a full-width panel under the session. Flats of the session's filter are listed first
  in a table (flat, filter, night, days from the session, frames, telescope, built / to build / library master),
  nearest night first; hovering a flat's name shows its preview. Flats of other filters are hidden behind "Show
  other filters (n)", for a session whose own filter is wrong, and are marked when shown. A flat set SubStation
  built is listed once (as its set), not again as a library master.

## Amendment 2026-10-12: masters are applied in the light's row order

Owner: M81 Hα (Feb 2026) showed the OAG's bright patch on one side and its shadow on the other, and a dust mote
twice: the flat was applied upside down. Cause: Siril keeps a NINA FITS light as written (`ROWORDER=TOP-DOWN`) but
writes converted XISF masters bottom-up, and nothing reconciled the two. A sweep of the NAS found 900 of 2,171
calibrated subs affected (755 XISF lights with top-down FITS darks; 125 top-down FITS lights with XISF flats; 20
with both).

- **002-DR-17**: Before calibrating, each master MUST be put in the light's row order (a flipped copy, cached);
  the same holds for the dark flat or bias applied to raw flats when building a master. Affected subs are
  recalibrated and re-graded (manual verdicts kept); masters stacked from them go stale.

## Amendment 2026-10-13: flats' filter, flat picker links and previews

- **002-DR-18**: A flat set's page lets a user say which filter the flats were taken through. A camera with no
  filter wheel records none, so flats shot through a Duo NB read as OSC; the correction is stored per flat (like a
  session's filter), regroups them with that filter's flats, and lights are matched again. Only flats take a
  filter.
- **002-DR-19**: In the flat picker, a flat set's name links to its page, and every row's hover preview shows an
  image: the built master, else one of its flats; when none can be drawn the card says so instead of staying blank.

## Amendment 2026-10-13: one exposure, one format; one row order per master

- **002-DR-20**: When the capture software saved the same exposure as both FITS and XISF (same camera, type and
  DATE-OBS), the XISF copy is set aside by a content ignore rule noted "Same exposure as <file> (FITS)". Stacking
  both would mirror a flat: Siril reads XISF bottom-up and NINA's FITS top-down, so every dust mote and the OAG
  shadow appear twice (found on the NGC 7822 flats: three sets of 50 FITS + the same 50 as XISF).
- **002-DR-21**: Before a master is stacked, every converted frame is put in the first frame's row order, so no
  master mixes orientations even when a set legitimately holds both formats. The build report says how many were
  turned.
- **002-DR-22** (2026-10-13): A master SubStation builds takes its camera and telescope from its own header (Siril
  keeps its frames'), resolved through the equipment aliases like a light, not from its set's label at build time.
  A later rig merge or correction then reaches the master too. (17 Sony masters built while the Sony frames were
  filed under the ATR2600M rig had kept "ATR2600M", showing ATR2600M data before the camera was bought.)
