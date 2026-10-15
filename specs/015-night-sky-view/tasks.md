# Tasks: The night on the map, and the sky as it was shot (spec 015)

- [X] N1 (2026-10-15) Map address takes lat/lon/zoom and a date or a from/to range (`features/map/search.ts`); the
  place nearest the address is selected with its panel open; a Night control with Last 30 days, This month, This
  year and Every night; `GET /map?since=&until=` filters places and nights; the night page's Open the map passes its
  place and night (FR-001, FR-002); tests
- [X] N2 (2026-10-15) `SkyPosition` (processing 0016): each light's pointing (plate solve, else header RA/Dec, else
  the dataset's usual pointing), mid-exposure time, place, altitude, azimuth and hour angle; worked out in one batch
  and again only when an input changes; checked against a hand calculation within 0.5° (FR-003, FR-004, SC-003)
- [X] N3 (2026-10-15) `GET /nights/{date}/sky?site=`: subs, tracks per dataset with target and rig, segments broken
  at gaps over 15 minutes and meridian flips, each target's altitude curve, the Moon's track and phase, sunset,
  astronomical dusk and dawn, sunrise; unplaced subs with the reason (FR-006, FR-007); tests
- [X] N4 (2026-10-15) Sky dome (`features/sky/SkyView.tsx`, zenithal equidistant, north up, east left): horizon,
  30°/60° rings, meridian, compass, tracks and marks; a colour per target (`--sst-series-1..6`, Okabe–Ito hues in
  every theme, reds in night vision), a shape per rig; rejected hollow, down-weighted faded; key toggles hide a
  target or rig, hovering or focusing a row dims the rest; hover shows the sub, a click opens the viewer (FR-005)
- [X] N5 (2026-10-15) Time slider and Play (twelve seconds for the night; half-hour steps with reduced motion), a
  ring per target and the Moon at the slider's time; altitude chart with twilight shaded, the Moon, 30° line and
  the slider's time, sized to its width so its text stays legible
- [X] N6 (2026-10-15) Tracks list and a table of every sub (each row opens the viewer); the dome and chart have text
  labels; slider and key are keyboard operable; phone layout stacks dome, slider, key and chart; screenshots in dark
  and light with two targets on one rig and a second rig
- [ ] N7 (later) The same dome across all nights of a target on dataset and collection pages
- [X] N8 (2026-10-15) The dome from the side (`project3d`, near and far halves, outline, drag and turn buttons) and
  one target in focus at a time (015-DR-05, 015-DR-06); tests; screenshots facing south and south-west
