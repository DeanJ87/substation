# Feature Specification: The night on the map, and the sky as it was shot

**Feature Branch**: `poc-substation`
**Created**: 2026-10-15
**Status**: Proposed 2026-10-15; not built
**Input**: Owner request, 2026-10-15: the night page's "Open the map" should open the map at that place; the map
should filter to a date, so it shows that night at that place; and "Through the night" should show the sky itself,
each target's path across it as it was imaged, in the style of a sky dome with the subs plotted along each
target's track (as some astrophotographers share for a single target). A night can have several targets and
two to four rigs running at once, so each track must say which target and which rig it is.

## Why

The night page today shows each dataset as a bar against clock time. That says when, not where: not how high the
target was, which way the rig was pointing, when it crossed the meridian, how close it got to trees, houses or
the moon, or why subs late in the night went soft. A view of the sky with every sub where it was taken answers those
at a glance, and makes a night worth sharing.

## User scenarios

1. **Open the map here.** On a night page, Open the map opens the map centred and zoomed on that night's place,
   filtered to that night; the place is selected and its panel open.
2. **The map on a date.** On the map the owner picks a date (or a range: a month, the last 30 days). Only places
   with subs in that period show, each panel listing just those nights. From a place on a single date, the
   owner goes to that night's page. The date is in the address, so the view can be linked to and goes back and forward.
3. **The sky through the night.** The night page's "Through the night" panel shows the sky from that place as a
   dome (horizon ring with N, E, S, W; altitude rings at 30° and 60°; the meridian). Each sub is a dot where its
   target stood at the middle of its exposure. Dots of one target join into a track, so a meridian flip, a cloud
   gap or a change of target shows as a break.
4. **Several targets and rigs.** Each target has its own colour and is named where its track ends and in a key.
   With more than one rig in the night, each rig has its own dot shape, also in the key. The key's rows can be
   switched on and off, and hovering a track or key row highlights it and dims the rest. In a tracks-only list, every row
   says target, filter, rig, time span and integration.
5. **Grades on the sky.** Rejected subs are hollow and down-weighted ones are faded, so the owner can see that the
   rejects sat low in the east, or near the moon. Hovering a dot shows the sub (time, exposure, altitude, FWHM,
   grade); clicking it opens the sub viewer.
6. **Play the night.** A time slider under the dome runs from the first sub to the last. Dragging it, or pressing
   Play, draws the subs up to that moment and moves a marker per target (and the moon, when up). With reduced motion
   on, Play steps rather than animates.
7. **Altitude over time.** Under the dome, a chart of altitude against time for each target (same colours), with
   the moon's altitude, astronomical twilight shaded, and 30° marked: the familiar planning chart, filled in with
   what was actually shot.
8. **Across nights.** On a dataset or collection, the same dome can show every night of that target from one place
   (tracks stacked by night, latest brightest), with "night 3 of 11" style counts and an altitude-over-dates strip.
   This is the per-target summary card the owner described; it follows the night view and can ship after it.

## Requirements

- **FR-001** The night page's map link carries the place (latitude, longitude, zoom) and the night; the map opens
  there with that place selected.
- **FR-002** The map takes a date or a date range in its address; places, counts and panels follow it; a clear
  control shows and clears it.
- **FR-003** For each sub of a night: its pointing (the plate solution's centre, else the header's RA/Dec, else
  the target's catalogue position, saying which), its mid-exposure time and the night's site give altitude and
  azimuth. Subs with no pointing and no known target are listed as not placed, not guessed.
- **FR-004** Positions are computed by SubStation (no internet needed) and kept, so a night with hundreds of
  subs draws at once.
- **FR-005** The dome uses the house design: theme tokens, both themes, readable labels; targets get distinct
  colours from a palette that stays distinguishable for common colour-blindness, and shape (per rig) never
  relies on colour alone.
- **FR-006** Tracks break where consecutive subs of a target are more than 15 minutes apart, or across a
  meridian flip.
- **FR-007** The moon's track and phase are drawn when it is above the horizon during the night.
- **FR-008** Every point and track has a text equivalent (the tracks list, and a table of subs with time,
  altitude and azimuth) for screen readers and keyboard users; the slider and key are keyboard operable.
- **FR-009** Works at phone width: the dome scales to the screen, the key and altitude chart stack below it.

## Out of scope

Planning future nights; terrain or a horizon profile (a later addition: the owner's own horizon mask drawn on the
dome); live position during a session; video export (a still image export may follow).

## Success criteria

- **SC-001** From a night page, one click shows that place on the map with only that night's data.
- **SC-002** On a night with 2+ targets on 2+ rigs, each track can be told apart by target and rig without colour.
- **SC-003** A sub's dot sits within 0.5° of its true altitude and azimuth (tested against a known ephemeris).

## Amendment 2026-10-15: as built

- **015-DR-01 Where pointing comes from.** SubStation has no offline catalogue of target positions, so a sub with
  neither a plate solution nor RA/Dec in its header takes its dataset's usual pointing (the median of its other
  subs' solutions or headers) and says so; only a dataset with no pointing at all leaves its subs unplaced (FR-003).
- **015-DR-02 One place per night.** Positions use the night's place (the mean of its lights' recorded sites); subs
  shot a few kilometres apart in one night are drawn from that one point, well within the picture's accuracy.
- **015-DR-03 The view.** The dome is drawn from directly below (zenithal, north up, east on the left, as looking
  up), which keeps every track legible; an oblique dome like the reference may follow with the across-nights view
  (N7). No refraction is applied: under half a degree above 2° altitude.
- **015-DR-04 The map's address** is `/map?lat=&lon=&zoom=&date=` (or `from=`/`to=`); the place is the one nearest
  the given point within about 5 km.

### Amendment 2026-10-15: the dome from the side, one target at a time

- **015-DR-05** The dome is drawn in three dimensions, as the owner's reference shows: a wireframe hemisphere
  (altitude rings at 30° and 60°, meridians every 45°, the far side dashed) over the horizon as an ellipse, seen
  from behind and above the observer (32° up), facing south by default. Dragging sideways, or the turn buttons,
  walks round it; "face south" puts it back. Replaces the top-down chart of 015-DR-04.
- **015-DR-06** One target is in focus at a time: its track, marks and its position at the slider's time are
  drawn fully; the others stay faint for context. It starts on the target with most subs; choosing a target in the
  key brings it into focus. Rig rows still hide or show a rig.

### Amendment 2026-10-15: the real sky behind the dome

- **015-DR-07** Behind the dome's lines, each point shows the sky that stood there at the slider's time (or the
  middle of the night), from an all-sky survey image: Mellinger (the default, best for the Milky Way at this scale)
  or DSS2 colour, or none. The choice is remembered in the browser. The survey is fetched by SubStation once per
  survey from the CDS image service (hips2fits, 4096 × 2048, plate carrée) and kept in the station's cache; the
  browser reprojects it (altitude and azimuth → right ascension and declination for the site and sidereal time).
  The floor inside the horizon is left bare. The image's credit is shown under the dome. If the survey can't be
  fetched (no internet), the dome draws as before with a note.

### Amendment 2026-10-15: orbit and zoom

- **015-DR-08** Dragging the dome orbits it: sideways turns it round, up and down tilts the viewpoint (8°–85°).
  The wheel, or a pinch, zooms towards the pointer (up to 6×); the − and + buttons zoom towards the focused
  target's track; ← and → turn it 45° for keyboards; "Reset view" puts it back. The drawing keeps one frame
  whatever the tilt and is clipped to it; marks and lines keep their size on screen when zoomed; the sky survey
  repaints at half resolution while the dome is moving.

### Amendment 2026-10-15: across nights (N7) and the camera's frame

- **015-DR-09 Across nights.** A dataset's Sky tab and a collection's Overview ("On the sky") show the same dome
  with every night of that target from one place: `GET /datasets/{id}/sky` and `GET /collections/{id}/sky`, each
  with an optional `?site=`. The place defaults to the one with most subs (by the nights' site key); the others are
  offered in a "From" list. Positions come from the SkyPosition cache, each light seen from its night's place worked
  out exactly as the night view does (the mean of that night's catalogued lights), so the two views share kept rows
  rather than overwriting each other. Tracks break per night and dataset at gaps and meridian flips (FR-006).
- **015-DR-10 Stacked by night.** All nights share the target's colour; the latest is drawn on top at full strength
  and older nights fade evenly down to a quarter. The key lists the nights newest first as "Night 3 of 11 · date",
  with subs and integration; hovering or focusing a row brings that night forward, choosing it keeps it forward (and
  the sky behind is then shown for the middle of that night, else the latest). A shape per rig, named in the key
  when there are several. The view starts facing the target's usual azimuth so a northern target isn't on the far
  wall; Reset view returns there.
- **015-DR-11 Altitude over the dates.** Under the dome, a strip with a bar per night from the lowest to the
  highest altitude its subs were taken at, a dot at the median, along the dates (month labels), 30° marked; the
  nights fade by age as on the dome.
- **015-DR-12 The camera's frame.** Each night track carries its dataset's field of view from its plate solves
  (median centre, median width and height, rotation folded onto 0–180° since a meridian flip covers the same sky);
  the across-nights view carries the most-shot rig's. The dome draws it as a rectangle for the target in focus (one
  per rig) at the time the sky behind is shown (the slider's time, else the middle of the night): the corners go
  from the tangent plane to right ascension and declination (gnomonic), then to altitude and azimuth for the site
  and sidereal time, each edge divided so it bends with the dome; the image's top edge is drawn heavier. Nothing is
  drawn while any part of it is below the horizon. The side panel says the frame's size and rotation in words.

### Amendment 2026-10-15: across nights within the shared scope

- **015-DR-13** The across-nights endpoints take the shared scope (spec 018, 018-DR-11); `site` still picks the place
  the sky is seen from. The dataset's Sky tab fits the tab row on a phone (007-DR-34).

### Amendment 2026-10-16: play the nights, and a sky that turns

- **015-DR-14** The across-nights dome has Play and a slider over the nights joined end to end (the days between
  skipped): the sky behind turns with the time, each night's subs appear as they were shot, earlier nights stay
  faint, nights still to come aren't drawn, the camera's frame shows where it pointed at that moment, and the
  night list follows. The key explains why tracks of different nights coincide: the dome is the sky above the
  observer, where a target follows the same arc every night and only the time it gets there changes.
- **015-DR-15** While either dome plays, the view slowly walks round it (six degrees a second), as in a filmed
  sky; a drag takes over, and reduced motion keeps it still.

### Amendment 2026-10-16: the whole target, by filter

- **015-DR-16** A collection has a Sky tab (moved from its Overview): every frame of the target on one dome, each
  mark and track in its filter's colour (L white, R red, G green, B blue, Hα deep red, OIII teal, SII amber;
  others from the series palette), with a Filters key giving each filter's frames and hours that hides or shows
  it, and Play through every night (015-DR-14). The same colours apply on a dataset's Sky tab. Each sub on the
  sky now carries its filter and exposure.

### Amendment 2026-10-16: readable from where you'd stand

- **015-DR-17** Each dome starts facing its target (its usual azimuth) and, the higher the target was, from a higher
  viewpoint: 32° up for targets around 40° or lower, two degrees more for each degree above, to 62°, so a track
  near the zenith sits inside the dome rather than along its rim. The drawing's frame is tall enough for that
  view. The sky survey is painted on the side of the dome facing the viewer, the side the target's track lies on,
  so the sky behind a track is the sky at it and both turn together; it covers the whole shell (the earlier bare
  floor is gone). Each track ends in a small arrowhead showing which way it went.
- **015-DR-18** (2026-10-22) The dome is seen from outside, and reads that way. The sky survey is painted on the far
  wall (the inside you look at), with only a faint copy on the near shell, so the near side no longer hides
  everything. Grid, tracks and marks are drawn back to front: the far wall plainly, the near shell faint, dashed and
  thinner, so in front and behind are told apart. Dragging turns the dome like a globe under the finger (the near
  surface follows the pointer), matching the turn buttons; dragging down raises the view. The hint says which way
  you are looking ("Seen from outside, looking south · 32° above").
