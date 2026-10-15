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
