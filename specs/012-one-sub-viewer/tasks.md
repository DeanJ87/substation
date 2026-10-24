# Tasks: One way to look at subs (spec 012)

- [X] M1 (2026-10-14) `GET /map` (places by site, nights, collections, picture); test
- [X] M2 (2026-10-14) Map page and menu item: clustered picture markers with counts, place panel, place names
- [X] M3 (2026-10-14) Sub page "Where": small map and place name; `site_lat`/`site_lon` on the sub's data
- [X] V1 (2026-10-14) Owner decisions recorded: Review is a filter; viewers are modals; labels keep the rig
- [X] V2 (2026-10-14) `Modal`; `SubView` (from the sub page) steps through a given list; `/subs/<sha>` redirects to
  its dataset with `?sub=`; dataset route `sub` and `show=flagged`; Flagged chip and "Review N flagged"; Review
  out of the menu, `/review` redirects; key help; nights in order in the dataset subtitle
- [ ] V3 Blink with best (Space) in the viewer
- [X] V4 (2026-10-14) Night page on the v2 layout: place name and small map, Moon (phase, and whether it was up
  during the lights, from astropy's built-in ephemeris), a timeline bar per dataset, a strip of sub thumbnails per
  dataset; a thumbnail opens the viewer stepping through every sub that night in time order (`?sub=`); `?site=`
  picks the place when several shot that night; calibration sets link to their set; `GET /nights/{date}/subs`
- [X] M4 (2026-10-14) Map place panel links: each collection shot there opens its sessions showing only the nights
  shot at that place (`?nights=&at=`, with "Show every session"); each night opens that place's night page
- [ ] V5 One dataset label (collection · rig · filter) on every page, search and Activity
- [ ] V6 Hide "Not recorded" rows; a section with nothing recorded says so once
- [X] V7 (2026-10-15) J previous / K next; key help
- [X] V8 (2026-10-15) Continuous zoom in the full-size view (wheel, pinch, drag, double click, − % + Fit 100%)
- [X] V9 (2026-10-15) Clickable pills restyled as buttons site-wide; chips and tags kept
- [X] V10 (2026-10-15) Buttons match pills (filled face, height, focus); Calibration's actions beside its title;
  Change and Filter side by side; a failed job's time over its two actions; post-processing "View at 100%" sized to
  its text
- [X] V11 (2026-10-15) The sub viewer's picture keeps its own shape, so star and annotation overlays sit on it exactly
  at any window shape (they drifted into the dead space of a fixed 3:2 box)
- [X] V12 (2026-10-15) Sub tiles show the capture time and exposure, FWHM, stars and guiding RMS; the file name on
  hover (they showed "…_026" or a cut-off name)
- [X] V13 (2026-10-22) Night page: the viewer follows the strips' order (012-DR-06)
- [X] V14 (2026-10-22) Bin in the viewer steps to the next or previous sub, or closes (012-DR-07); test
- [X] V15 (2026-10-24) Display levels in the sub viewer (012-DR-08): Black point and Brightness sliders and Reset
  under the toolbar and in the 100% view's bar; an SVG levels filter on the viewer image, 100% view and inspector;
  held across J and K, remembered per dataset and filter in the browser; [ ] \ keys and key help; tests for the
  curve, stepping, Reset, keys and storage
