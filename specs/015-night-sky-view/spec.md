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
