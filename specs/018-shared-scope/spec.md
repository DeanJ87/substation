# Feature Specification: One scope for every list

**Feature Branch**: `poc-substation`
**Created**: 2026-10-15
**Status**: In progress 2026-10-15: the scope, every list endpoint and the Library, Calibration and map built; cameras as records open
**Input**: Owner suggestion, 2026-10-15: the endpoints could share the same inputs (place, date, date range,
camera, rig, project and so on), so the interfaces and the architecture stay consistent.

## Why (what the code does today)

Each list endpoint grew its own filters, named its own way:

| Endpoint | Filters today |
|---|---|
| `GET /frames` | `dataset`, `night` (one date), `type`, `status`, `q` |
| `GET /datasets` | `state`, `target` (text), `filter` |
| `GET /library/stats` | `date_from`, `date_to`, `rig` (a name, not an id), `q` |
| `GET /nights/{date}`, `/nights/{date}/subs` | `site` |
| `GET /calibration-sets` | `type`, `night` |
| `GET /collections/{id}/framing`, `/collections/{id}/combined` | `project` |
| `GET /map`, `/library`, `/review`, `/calibration/blocking`, `/calibration/shopping`, `/changes` | nothing |

So the same idea (a date range, a rig) is spelled three ways, several pages fetch everything and filter in the
browser, and a filter chosen on one page can't follow a link to another (the map → collection links had to add
their own `nights` parameter).

## The idea

One **scope**: a fixed set of optional inputs that every list endpoint accepts, meaning the same thing everywhere,
and one place in the backend that turns it into a query for each kind of record.

| Input | Meaning |
|---|---|
| `site` | a place (its site key); or `lat`, `lon`, `within_km` for "near here" |
| `date` | one night (the observing night, not the calendar day) |
| `date_from`, `date_to` | a range of nights, either end open (`from` can't be a parameter name in the backend's language) |
| `camera` | camera id (cameras become records, as rigs are) |
| `rig` | rig id |
| `telescope` | telescope name, until telescopes are records too |
| `filter` | normalised filter name (`Ha`, `OIII`, `L`, …) |
| `collection`, `project`, `dataset` | ids |
| `target` | target name |
| `verdict` | `accept`, `down`, `reject`, `flagged`, `manual` (lists of subs) |
| `q` | free text, as the search bar understands it (names, months, "last night") |
| `cursor`, `limit` | paging, the same on every list |

## Requirements

- **FR-001** One `Scope` schema, used by every list endpoint as its query parameters; an endpoint may add inputs
  of its own but never renames a shared one.
- **FR-002** One function per record type applies a scope (`frames`, `datasets`, `nights`, `masters`,
  `calibration sets`, `collections`), each mapping the inputs to that type's fields (a dataset's rig, a frame's
  dataset's rig, a night's site…). Inputs that don't apply to a type are ignored, not errors.
- **FR-003** Every list endpoint pages the same way (`cursor`, `limit`, `next_cursor`).
- **FR-004** The frontend has one `useScope()` that reads and writes the scope in the address, and one filter bar
  that shows it; a link from one page to another carries the scope, so "M 81, February, the Askar" stays chosen
  from the Library to the map to a night to Calibration → What to shoot.
- **FR-005** The old parameter names keep working (`night`, `date_from`, `date_to`, rig by name) until the
  frontend no longer sends them, then are removed. The OpenAPI contract test covers the shared schema.
- **FR-006** Totals (Library stats, map counts, what to shoot) are computed for the scope on the server; no page
  fetches everything to filter it.

## Order of work

1. Scope schema and the apply functions, with tests per record type (each input on each type).
2. Endpoints that take nothing today: map (with the date filter of spec 015), review, calibration blocking and
   what to shoot, library.
3. Endpoints with their own names: frames, datasets, library stats, calibration sets, nights.
4. Frontend `useScope()`, the shared filter bar, links that carry the scope; remove browser-side filtering.
5. Cameras as records (rigs already are), so `camera` is an id like `rig`.

### Amendment 2026-10-15: as built so far

- **018-DR-01** The range is `date_from` / `date_to` (Library stats already used those names); the map's `since` /
  `until` (spec 015) are accepted as the older names. `camera` and `telescope` are names until they are records.
- **018-DR-02** `q` reads a date the way search does ("october", "last night") and otherwise matches the target,
  dataset or collection name.
- **018-DR-03** Built: the scope and `apply()` for frames, datasets, nights and calibration matches; What to shoot
  (and its NINA and CSV downloads), Waiting for calibration, Review and the map take it. What to shoot has the
  shared filter bar, in its address.


### Amendment 2026-10-15: the Library, the older endpoints and links that carry the scope

- **018-DR-04** The Library (`/library`) takes the scope: a collection is listed when any of its datasets is in
  scope, and its card counts only those datasets and their sessions on the scope's nights and place; the ungrouped
  list and the counts are the datasets in scope. The readouts (what needs you, missing calibration, this month)
  stay whole. `/library/stats` takes the scope too; its `rig` may still be a rig's name (FR-005), and an unknown
  name matches nothing rather than everything. Binned and deleted lights count through the dataset they were in.
- **018-DR-05** Free text (`q`) also matches a rig's name and a filter, as Library stats' search did; on calibration
  sets and masters it matches the type, filter, camera and telescope. On `/frames` it still finds a frame by its
  OBJECT header or its file's path.
- **018-DR-06** Older names kept (FR-005): `night` on `/frames` and `/calibration-sets` (for `date`), a rig by name on
  `/library/stats`, `since`/`until` on `/map`, `from`/`to` in the map's address. On `/datasets`, `target` keeps its
  older meaning, part of the name, because every exact match is also a partial one. Paging (FR-003) stays where it
  was: frames and datasets page by `cursor`/`limit`/`next_cursor`; calibration sets and masters are whole lists
  (hundreds, grouped by night on one page), so paging them would only add round trips.
- **018-DR-07** Calibration has no rig of its own: a `rig` narrows calibration sets and masters to the rig's camera.
  A master built here takes the night its frames were shot, so a master's nights are compared with the night shown.
- **018-DR-08** A night's subs (`/nights/{date}/subs`) take the rest of the scope; the date and place are already in
  the address. Newer calibration (`/calibration/recalibration`) takes the scope through each sub's light.
- **018-DR-09** The frontend has `useScope()` (the scope in the current page's address, changed in place) and one
  filter bar: free text (settling before it asks), rig, filter and nights, plus a removable chip for anything a link
  brought that the bar has no control for (a night, a place, a collection…). The Library and Calibration use it and
  no longer filter in the browser. Links carry the scope: Library → collection (which narrows its sessions to the
  scope's nights) → its map (with the collection) → a night → What to shoot (that night and place instead of the
  range) and back. The map says when a link narrowed it beyond its nights, with a way to show everything.
- **018-DR-10** Cameras as records (SC5) stay open: cameras are free text on frames, datasets, rigs and calibration
  sets, so a record needs a model, a backfill from all four, and the rig editor to pick one.

### Amendment 2026-10-15: the scope meets the night sky and the selection bars

- **018-DR-11** The night sky across nights (`/datasets/{id}/sky`, `/collections/{id}/sky`, spec 015 N7) takes the
  shared scope: its nights, rigs, filters and the rest narrow the lights drawn. Its `site` keeps the meaning it had
  there, the place the sky is seen from, so every other place stays in the "From" picker. A collection's "On the
  sky" section passes the scope's nights, as its sessions are narrowed.
- **018-DR-12** A selection bar (spec 016 U6) on a list the scope narrows (the Library's Not in a collection, the
  Calibration page's raw sets) acts only on chosen rows still shown: narrowing the list drops hidden rows from the
  choice, so an action never reaches what the page doesn't show.

### Amendment 2026-10-15: after review

- **018-DR-13** With nights or a place in the scope, a collection card's hours are counted from those nights' subs,
  so they agree with its sessions and with Library stats (they had summed each dataset's whole history).
- **018-DR-14** A rig by name on Library stats (the older parameter) means every rig of that name.
- **018-DR-15** The Library tells "nothing matches these filters" from an empty library by the unfiltered count; the
  collection picker on a dataset and the filter list always offer everything, whatever is filtered now.
- **018-DR-16** (2026-10-22) Choices follow their parent. With a rig chosen, the filter list offers only filters that
  rig shot through (each rig lists its filters); choosing a rig that lacks the current filter clears it. No choice
  leads to an empty page.
