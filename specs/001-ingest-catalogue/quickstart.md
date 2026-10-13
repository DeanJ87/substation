# Quickstart and validation: Ingest and catalogue

How to prove spec 001 works end to end. Contracts: [container](contracts/container.md),
[API](contracts/openapi.yaml), [events](contracts/events.md), [patterns](contracts/path-patterns.md).
Entities: [data-model.md](data-model.md).

## Prerequisites

- Docker with Compose.
- Test data: the spike trees (`sub-test`, 42 GB) on any disk; a scratch folder to act as a live capture
  folder; an empty local folder for `/data/substation`.
- Developer machine: Python 3.12 with uv, Node 20+.

## Run

```bash
docker compose -f docker/compose.example.yml up -d      # edit the three volume lines first
# open http://<host>:8080, sign in with SUBSTATION_ADMIN_USERNAME / _PASSWORD
```

Mount the spike tree read-only as `/data/library/spike` and the scratch folder as
`/data/library/capture`.

## Developer test commands

```bash
cd backend && uv run pytest                     # unit, integration, contract (header fixtures)
SUBSTATION_GOLDEN_DIR=/path/to/sub-test uv run pytest -m golden   # full golden run
cd frontend && npm test && npx playwright test
```

## Validation scenarios

| # | Scenario | Steps | Expected | Spec ref |
|---|---|---|---|---|
| V1 | Read-only guarantee | Hash every file in the spike tree; run a full ingest; hash again | Identical hashes, names and mtimes | SC-004, FR-002 |
| V2 | Golden counts | Ingest the spike tree | 636 unique frames; 17 BAD_ copies folded into user REJECTs; 8 light datasets; 6 flat sets; 3 dark-flat sets; reconciliation list matching spike phase 2 (masters missing gain, offset, temperature; BAD_ without twin) | SC-002, US2, US6 |
| V3 | Live arrivals | Replay one night into `capture` at capture pace (`backend/scripts/replay.py --rate 600s --speedup 60`) | Each sub appears ≤10 s after its copy completes; `frame.catalogued` events in the browser | SC-001, US1 |
| V4 | Partial files | Replay with a slow writer (`--chunked`) | No entry until the file is complete | US1-2 |
| V5 | Nights after midnight | Inspect 2026-10-07 data | All 44 lights on night 2026-10-07 | US1-3 |
| V6 | Moves and renames | Move a dataset folder within `capture`, rename half its files, copy one night elsewhere | Frame count unchanged; copies updated; `CopyEvent` moved/copied logged; no reconciliation | SC-003, US2 |
| V7 | Missing content | Delete every copy of one frame | After one more sweep: frame missing, dataset "Needs reconciliation"; restoring the file clears it | US2-4 |
| V8 | Replaced content | Overwrite a file with different content at the same path | New frame; old frame loses that copy | US2-5 |
| V9 | No re-hashing | Rescan an unchanged library of 10,000 frames | No hash jobs; sweep ≤2 min | SC-006 |
| V10 | Missing headers | Copies of 20 lights with FILTER and EXPTIME stripped (`scripts/strip_headers.py`) | Without patterns: 20 reconciliation items; with the NINA filename pattern: values "from filename pattern"; one bulk correction resolves the rest | US3 |
| V11 | Bulk drop | Stop container; copy 400 files; start; replay live subs meanwhile | Queue shows the backlog and ETA; live subs still ≤10 s; bulk done ≤15 min; restart midway resumes | SC-005, US4 |
| V12 | Ignore rules | Ignore one frame and one folder; move and copy them | Not processed; listed under Ignored; undo queues them | US5 |
| V13 | Multi-year dataset | Ingest phase 1 and 2 NGC 7000 data | Datasets list nights per panel; each night browsable | US7 |
| V14 | Accounts | Open the UI without signing in; sign in as admin; create a standard user | API returns 401 without a session; standard user cannot change libraries | constitution VIII |
