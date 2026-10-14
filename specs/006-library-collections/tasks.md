# Tasks: Library, collections and rigs

Done items were verified against the code on 10 October 2026. Open items name the files to touch and the
requirement they close.

## Phase 1: Model and rules (built)

- [X] L1 Rig model and detection from TELESCOP, INSTRUME, FOCALLEN (XPIXSZ for scale), Seestar naming [FR-001]
  - `apps/catalogue/models/library.py` `Rig`; `services/library.py` `ensure_rig`; `tests/unit/test_smart_scope.py`
- [X] L2 Rig rename, merge, merge suggestions and calibration mode [FR-001, US3]
  - `api_library.py` `/rigs`, `/rigs/{id}`, `/rigs/{id}/merge`, `/rigs/suggestions`; `features/settings/Rigs.tsx`
- [X] L3 Collections: create, rename, delete (datasets kept), add and remove datasets, one collection per dataset [FR-002]
  - `api_library.py` `/collections*`; `Dataset.collection` FK SET_NULL in `models/grouping.py`
- [X] L4 Suggestions by object name, then header pointing within 2°, with evidence; "Accept every suggestion" [FR-003, header half]
  - `services/library.py` `suggest`, `centre`; `POST /collections/accept-suggestions`
- [X] L5 Dataset labels "Rig · Filter · Panel N" [data model]
  - `services/library.py` `label`
- [X] L6 Name merging within a collection [extra, kept by design review]
  - `POST /collections/{id}/merge-names`; `CollectionView.tsx` `MergeNames`; `tests/unit/test_merge_names.py`

## Phase 2: Screens (built)

- [X] L7 Library home: readouts, collection cards with integration per filter and state badges, ungrouped list with suggestion, Choose…, Add to …, New collection, search, rig filter [FR-004, US1]
  - `GET /library`; `features/library/Library.tsx`
- [X] L8 Collection screen: rig × filter matrix, sessions timeline per rig, dataset table, remove dataset API [FR-005, US2]
  - `GET /collections/{id}`; `features/library/CollectionView.tsx`

## Phase 3: Library (L1) gaps

- [X] L9 "New collection" header button with in-page dialog; rig filter as a chip menu ("Rig All") [006-DR-01]
  - `features/library/Library.tsx`, `library.module.css`, new `features/library/EditCollection.tsx` (shared with L16)
- [X] L10 Processing readout names the main job ("workers busy · Hα master integrating") [006-DR-02]
  - `apps/catalogue/api_library.py` `library()` (`readouts.main_job`, reuse `_target` and the job type from `substation/tasks/activity.py`); `Library.tsx`
- [X] L11 Ungrouped meta "<sessions> · <subs> × <exposure> s · from <dates>" [006-DR-03]
  - `api_library.py` `LibDatasetOut.first_night`, `exposure_s`; `Library.tsx` `UngroupedRow`; `features/format.ts` range helper
- [X] L12 Constellation on the card objects line ("NGC 7000 · IC 5070 · Cygnus · 6 datasets") [FR-004, G21]
  - `models/library.py` `Collection.constellation` + migration; `services/library.py` `refresh_objects` (astropy `get_constellation`); `_card`; `Library.tsx`
- [X] L13 First-run state: "No subs yet", watched folder paths in mono, buttons to Settings → Folders and import docs [FR-004, G19]
  - `Library.tsx`; folder paths from `/health` libraries

## Phase 4: Collection (L2, L3) gaps

- [X] L14 Tabs Overview · Datasets N · Sessions N · Masters N with `tab` search param [006-DR-04]
  - `routes/router.tsx` (collection `validateSearch`); `CollectionView.tsx` split; extract `features/library/Timeline.tsx`
- [X] L15 Reference framing: `Collection.reference_dataset`, "reference" marker and framing label in the matrix, dataset meta "exposure · gain · set temperature" [006-DR-08]
  - `models/library.py` + migration; `api_library.py` `CollectionOut.reference_dataset_id`, `LibDatasetOut.exposure_s`, `set_temp_c`; `CollectionView.tsx`
- [X] L16 Candidates endpoint ranked by centre offset, rotation and overlap, with note and "in <other collection>" [006-DR-05, FR-003] — partial 2026-10-10: GET /collections/{id}/candidates ranked by header-pointing offset and object name; rotation and overlap wait on spec 009 — done 2026-10-10 with 009 P11 (solved overlap, rotation, offset; note)
  - `services/library.py` `rank_candidates`; `api_library.py` `GET /collections/{id}/candidates`; header centre now, solved values via P11
- [X] L17 "Add datasets" dialog: ranked list, notes, checkboxes, low-overlap group, "Add N datasets" [006-DR-05, FR-002] — done 2026-10-10 (in-page panel with checkboxes and "Add N datasets"); low-overlap grouping waits on 009
  - new `features/library/AddDatasets.tsx` (Radix Dialog); `features/v2/hooks.ts` `useCandidates`; `CollectionView.tsx`
- [X] L18 Edit collection dialog (name and objects) and in-page Remove confirmation [006-DR-05, 007-DR-16]
  - `api_library.py` `CollectionPatch.objects`; `EditCollection.tsx`; `CollectionView.tsx` (drop `window.confirm`, use B24 `components/Confirm.tsx`)
- [X] L19 Dataset table: verdict-badge state with master version or "Master current · <date>", split grade bar "<kept> of <total> kept", short last-night date [006-DR-06]
  - `api_library.py` `LibDatasetOut.master_version`, `master_finished_at`; `CollectionView.tsx`; `collection.module.css`; `format.ts` short date
- [X] L20 Select a date range on the timeline to filter the dataset table [006-DR-07]
  - `features/library/Timeline.tsx` (drag and keyboard range); `CollectionView.tsx` (`from`, `to` search params)
- [X] L21 Masters tab and combined masters panel: each dataset's current master; "Stack combined masters" shown disabled with the reason until spec 004 cross-rig stacking lands [006-DR-05, G24] — done 2026-10-10: Masters tab shows each dataset's masters and the Combined masters panel (enabled, spec 004 T022)
  - `api_library.py` `CollectionOut.masters`; `CollectionView.tsx` Masters tab
- [X] L22 Framing panel on the Overview and field overlay on collection cards, legend with field size, scale and overlap [006-DR-09] — done 2026-10-10 with 009 P12/P17/P18 on the Overview (images, outlines, legend, mosaic); card thumbnails keep the master preview
  - depends on P9 and P12 (spec 009); `Library.tsx`, `CollectionView.tsx`, `features/library/Framing.tsx`

## Phase 5: Tests, contract, validation

- [X] L23 Unit and API tests: suggestion evidence, one collection per dataset, delete keeps datasets, card filter totals equal dataset sums, candidates ranking [SC-001, SC-002, FR-002, FR-003] — done 2026-10-10: tests/contract/test_library_api.py and tests/unit/test_merge_names.py
  - new `backend/tests/unit/test_library.py`; `backend/tests/contract/test_catalogue_api.py`
- [X] L24 Regenerate the client contract and the reference copy — done 2026-10-10: client regenerated; full generated contract at specs/001-ingest-catalogue/contracts/openapi.generated.json beside the hand-written subset the contract test checks
  - `frontend/src/api/openapi.json`, `schema.d.ts`; `specs/001-ingest-catalogue/contracts/openapi.yaml`
- [X] L25 Validation on the phase 2 tree (T7 copy): two collections from accepted suggestions, per-filter integration equals the datasets [US1 independent test, SC-001, SC-002] — done 2026-10-10: 16 collections; every card's per-filter integration equals its datasets' (0 mismatches)

## Owner requests 2026-10-10 (afternoon)

- [X] L30 Library date filter: From/To dates (same date in both = on that night) across collections and ungrouped datasets, from each one's session dates

## Owner requests 2026-10-10 (evening)

- [X] L40 Project model (collection, name, kind, planned panels, order) and Dataset.project; API CRUD, assign, reorder; suggestions by panel and framing overlap [006-DR-20] — done 2026-10-10: Project model, Dataset.project/project_position, CRUD, assign in order, reorder, suggest (panels → mosaic; others by ≥50% framing overlap, else rig)
- [X] L41 Collection page lists projects; Overview, framing, integration and combined masters per project [006-DR-20] — done 2026-10-10: project bar scopes framing and dataset lists; Manage board (name, kind, planned panels, missing panels, integration)
- [X] L42 Framing table multi-select (click, Shift, Cmd/Ctrl, drag, All/None) and outlines on/off [006-DR-21] — done 2026-10-10
- [X] L43 Framing filter chips and HOO/SHO palette previews [006-DR-22] — done 2026-10-10: filter chips; HOO/SHO previews via SVG tint + screen blend
- [X] L44 Shared sortable table headings across the site [006-DR-23] — done 2026-10-10: components/sortable.tsx (natural text, numbers, missing last, aria-sort); collection datasets, framing, calibration masters, dataset Calibration and Quality tables, night calibration sets; settings tables still plain
- [X] L45 Drag reorder of projects and datasets [006-DR-24] — done 2026-10-10: drag project chips (Alt+←/→) and datasets within/between projects (Alt+↑/↓)
- [X] L46 Library stats for the current filters: lights, nights, hours taken and kept, kept/rejected rates, average SQM, hours per filter and per rig (GET /library/stats)
- [X] L47 Framing shows a dataset's current master when it is plate solved (deeper than one sub), else its best sub; masters are solved after integrating, starting from the subs' solved centre (a header start once locked onto the wrong field) and rejected if more than 0.5° from it
- [X] L48 Colour (As shot, HOO, SHO) is its own control, not a filter chip; framing larger (full width, table below); framing resets when the project changes
- [X] L49 Stack partners must share the panel and (when solved) half the field: Heart panel 1's v2 master had been stacked with panel 2 and was re-run alone

- [X] L50 Zoomable images across Library, dataset, sub, review and calibration screens (006-DR-25)
- [X] L51 PageLoading skeletons, Library stats updating state, debounced stats query (006-DR-26)
- [X] L52 Copy pass over frontend and API messages (006-DR-27)
- [X] L53 (owner 2026-10-13) Collection title split into common name + designation tag; subtitle drops repeated
  names (`frontend/src/features/library/names.ts`, test) (006-DR-28)
- [X] L54 (owner 2026-10-13) `ensure_rig` re-detects a rig with the wrong camera and reuses a rig within 2% focal
  length; NAS datasets re-checked; unnamed collections named, duplicate Sh2-240 merged (006-DR-29)
- [X] L55 (owner 2026-10-13) `Dataset.rejected_integration_s` (migration 0015, set by `recount_grades`); card
  `filter_time` split; segmented bars; NAS datasets recounted; test (006-DR-30)
- [X] L56 (owner 2026-10-13) Rejected readout as the complement of Kept (006-DR-31)
- [X] L57 (owner 2026-10-13) Home readouts replaced (`_home_readouts`, Library.tsx); test (006-DR-32)
- [X] L58 (2026-10-13) Readout numbers formatted; missing-calibration reasons name the rig and leave out an offset
  the camera never records ("no 180 s dark at gain 1600", not "… and offset None")
- [X] L59 (2026-10-14) `keep_collections` after `reresolve_targets` and `reresolve_library` (006-DR-33); test
- [X] L60 (2026-10-14) `tidy_datasets` after `reresolve_library` (006-DR-34); test
