# Tasks: One scope for every list (spec 018)

- [X] SC1 (2026-10-15) `Scope` schema (FR-001) and `scope.apply_frames / datasets / nights / masters / sets / collections`
  (FR-002); tests: every input on every type
- [X] SC2 (2026-10-15) Map, review, calibration blocking and what to shoot take the scope; the Library (`/library`)
  and its totals (`/library/stats`) take it too, worked out on the server (FR-006); a collection's card counts only
  what the scope covers; Newer calibration (`/calibration/recalibration`) takes it as well
- [X] SC3 (2026-10-15) Frames, datasets, library stats, calibration sets, masters and a night's subs move to the shared
  names; old names still accepted (FR-005): `night` on frames and calibration sets, a rig by name on library stats,
  `target` as part of the name on datasets, `since`/`until` on the map. Shared paging (FR-003) where the list was
  already paged (frames, datasets); calibration sets and masters stay whole lists (see 018-DR-06)
- [X] SC4 (2026-10-15) `readScope`/`scopeQuery`, `useScope()` and the shared filter bar (with a search box and chips for
  what a link brought) on the Library, Calibration and What to shoot; the map reads the same scope from its
  address; links carry it: Library → collection → map → night → What to shoot, and back; browser-side filtering
  removed from the Library and Calibration (FR-004); tests: `readScope`, `replaceScope`, `forNight`, `inNights`,
  the map's address, and every endpoint above
- [ ] SC5 Cameras as records; `camera` by id. Open (2026-10-15): cameras are free text on frames, datasets, rigs and
  calibration sets, so a camera record needs a model, a migration that backfills it from all four, and the rig
  editor to choose one; not done with the scope work. `camera` stays a name, matched whatever the case (018-DR-01)
- [ ] SC6 Drop the old parameter names once nothing sends them
- [X] SC7 (2026-10-15) The across-nights sky takes the scope (its `site` picks the view); the collection's On the sky
  passes the scope's nights; selection bars on scoped lists keep only rows still shown (018-DR-11, 018-DR-12); tests
- [X] SC8 (2026-10-15) Review fixes: scoped card hours from the subs, rig names shared by several rigs, empty state and
  picker from the whole library (018-DR-13..15); tests
- [X] SC9 (2026-10-22) Rigs list their filters; the filter bar narrows filters to the chosen rig (018-DR-16); tests
- [X] SC10 (2026-10-22) Dependent fields across every select, picker and date range: shared helpers
  (`features/cascade.ts`), scope bar, master window, New master range and sessions, Compare, Finished role and
  filter, project split, kind and goals, Library Files, token expiry, notification test, path pattern preferences,
  session filter suggestions by camera (018-DR-17); vitest and a backend contract test
- [ ] SC11 Cascades that need server data: a project count per collection for Link another, per-rig counts for the
  scope bar's rig list, counts per rule for New master (018-DR-17, cascade audit)
