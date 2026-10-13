# Plan: Library, collections and rigs

Most of the model and the two screens already exist (`apps/catalogue`, `features/library`). This plan
covers the remaining design-review requirements (006-DR-01 to 006-DR-09) and the tests and validation
the feature still lacks. Framing (006-DR-09) and solved suggestions wait on spec 009; "Stack combined
masters" waits on the spec 004 increment for cross-rig stacking.

## Technical context

- Backend: Django 5.2 + Django Ninja, SQLite WAL. Library endpoints live in
  `backend/apps/catalogue/api_library.py` on the catalogue router; rules in
  `backend/apps/catalogue/services/library.py`; models `Rig` and `Collection` in
  `backend/apps/catalogue/models/library.py`, `Dataset.rig` and `Dataset.collection` (FK, SET_NULL) in
  `models/grouping.py`.
- Frontend: React + TanStack Router/Query, CSS modules. `features/library/Library.tsx` (L1),
  `features/library/CollectionView.tsx` (L2), shared hooks and layout in `features/v2/hooks.ts` and
  `features/v2/v2.module.css`, formatters in `features/format.ts`. Routes in `routes/router.tsx`.
- Contract: `frontend/src/api/openapi.json` and `schema.d.ts` are generated from the backend; the
  reference copy is `specs/001-ingest-catalogue/contracts/openapi.yaml`.

## Already built (verified in code)

- Rig detection from TELESCOP, INSTRUME, FOCALLEN (and XPIXSZ for image scale), Seestar handling,
  rename, merge, merge suggestions, per-rig calibration mode (`ensure_rig`, `/rigs*`,
  `features/settings/Rigs.tsx`).
- Collections: create, rename, delete (datasets kept: FK SET_NULL), add and remove datasets, one
  collection per dataset (FK), "Accept every suggestion", name merging (`/collections/{id}/merge-names`).
- Suggestions by object name, then header pointing within 2°, with the evidence sentence (`suggest`).
- `GET /library`: readouts, cards (integration per filter, rigs, span, sessions, states, preview master),
  ungrouped datasets with suggestions; search and rig filter on the client.
- `GET /collections/{id}`: card, datasets, rig × filter matrix, rig details, sessions; the L2 screen with
  matrix, timeline and dataset table.

## Design of the remaining work

- **Library header** (006-DR-01): "New collection" opens a small in-page dialog (name, optional datasets)
  that posts `POST /collections` with an empty list allowed; the rig `<select>` becomes a chip that opens a
  menu ("Rig All", then each rig), styled per A.5 chips.
- **Processing readout** (006-DR-02): `library()` returns `readouts.main_job` built from the running task
  with the highest priority: task name mapped to a verb ("master integrating", "subs grading") and its
  dataset's filter from the task arguments ("Hα master integrating"). The mapping is shared with Activity
  (`substation/tasks/activity.py` `_target` already derives a job's type and target; reuse it).
- **Ungrouped meta** (006-DR-03): `LibDatasetOut` gains `first_night` and `exposure_s`; the client renders
  "2 sessions · 420 subs × 10 s · from 3 and 4 October 2026" with a new range formatter in `format.ts`.
- **Constellation** (G21): computed from the collection's median header centre with
  `astropy.coordinates.get_constellation` in `_card`, cached on `Collection.constellation` (new field,
  refreshed in `refresh_objects`).
- **Collection tabs** (006-DR-04): `/collections/$id?tab=overview|datasets|sessions|masters`. Overview keeps
  the matrix, framing (009) and combined masters panel; Datasets holds the table; Sessions holds the
  timeline plus a session list; Masters lists each dataset's current master (from `Master`), with the
  combined-master panel disabled with a reason until spec 004 adds cross-rig stacking.
- **Reference framing** (006-DR-08): `Collection.reference_dataset` (nullable FK, default the dataset with
  most accepted integration). The matrix marks its rig "reference" and the dataset's framing label; meta
  reads "Reference framing · 300 s · gain 100 · −10 °C".
- **Add datasets** (006-DR-05): `GET /collections/{id}/candidates` ranks every dataset not in this
  collection by centre offset from the reference framing (header centre now, solved centre and overlap
  after 009), rotation difference when known, and overlap; each with a note ("Centre 6′ away, 88% overlap"
  or "Pointing 1.2° away (from headers)") and `in_collection` naming any other collection. The dialog
  (`AddDatasets.tsx`, Radix Dialog) has checkboxes, a separate "Low overlap: a separate panel" group and
  "Add N datasets" (existing `POST /collections/{id}/datasets`). Nothing moves on disk.
- **Edit collection**: a dialog for name and objects text (`CollectionPatch.objects`), replacing the inline
  rename. Remove collection uses the in-page confirmation from spec 007 (B24).
- **Dataset table** (006-DR-06): `LibDatasetOut` gains `master_version` and `master_finished_at`; State
  shows `VerdictBadge` "Integrating v7", "Master stale", "Awaiting calibration", "Needs reconciliation" or
  "Master current · 2 Oct"; Grades a three-part split bar with "452 of 541 kept"; Last night a short date.
- **Timeline range** (006-DR-07): pointer drag (and Shift+arrow keys) on the axis selects a date range held
  in the route search (`from`, `to`); the dataset table filters to datasets with a session in range.
- **First-run state** (G19): when no subs exist, the content is replaced by "No subs yet", the watched
  folder paths in mono (from `/health` libraries), "within a few seconds of landing", and links to
  Settings → Folders (spec 008) and the import docs.

## Constitution check

- I (originals read-only) and catalogue-only collections: no endpoint touches files. Pass.
- III (every decision explained): every suggestion and candidate carries its evidence sentence. Pass.
- VIII: collection edits are standard-user actions; rig merge stays admin (`admin_required`). Pass.

## Project structure

```text
backend/apps/catalogue/models/library.py      Collection.constellation, Collection.reference_dataset
backend/apps/catalogue/migrations/            one migration
backend/apps/catalogue/services/library.py    rank_candidates, constellation, reference
backend/apps/catalogue/api_library.py         readouts.main_job, LibDatasetOut fields, /candidates, patch objects
backend/tests/unit/test_library.py            new
frontend/src/features/library/                Library.tsx, CollectionView.tsx (split into tabs),
                                              AddDatasets.tsx, EditCollection.tsx, Timeline.tsx (extracted)
frontend/src/features/format.ts               date range and short date helpers
frontend/src/routes/router.tsx                collection search params
```

## Complexity tracking

None. Combined masters and framing are explicit dependencies, not workarounds.
