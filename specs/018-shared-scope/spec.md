# Feature Specification: One scope for every list

**Feature Branch**: `poc-substation`
**Created**: 2026-10-15
**Status**: Proposed 2026-10-15; not built
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
| `from`, `to` | a range of nights, either end open |
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
