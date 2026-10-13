# Validation: spec 001 ingest and catalogue

T109. Every quickstart scenario, run on 9–10 October 2026 against the owner's real data: the phase 2 spike
tree (`sub-test`, 42 GB, mounted read-only as library `archive`) and a scratch capture folder (`capture`)
fed by `backend/scripts/replay.py`. Stack: the three-service Compose build (`docker/compose.local-test.yml`)
with **three worker containers** (two worker processes each), on macOS Docker Desktop with the data on a
USB SSD (ExFAT).

**Still to do:** the same run on the owner's NAS during a live NINA session. Two results below depend on
the host and should be re-read there (marked †).

| # | Scenario | Result | Evidence |
|---|---|---|---|
| V1 | Read-only guarantee | **Pass** | `pytest -m golden`: a full ingest of the 42 GB tree with a guard that fails any write-mode open, rename, delete, chmod or utime under the library: no attempts, and every file's name, size and mtime unchanged. Content-hash comparison runs on the fixture tree in `test_read_only.py`. |
| V2 | Golden counts | **Pass** | `pytest -m golden` (1 min 57 s): 636 unique frames, 36 WBPP masters, 18 NINA rejects (17 BAD_ twins + 1 without a twin, on the reconciliation list), 8 light datasets with the spike's reject counts (P3 Hα 24/5, Heart P2 Hα 15/4, P1 OIII 15/5, P2 Hα 6/2, L 1/1), 6 flat sets (L 51, R 51, G 50, SII/Hα/OIII 50), dark flats 2 s ×150, 1 s ×50, 0.01 s ×50. Reconciliation differs from the spike's 45 by design: here each master gets one item per missing value (36 × gain, offset, temperature = 108), grouped by folder on screen with suggestions. |
| V3 | Live arrivals | **Pass †** | Replay of the 10-07 night into `capture`: each sub appeared in NGC 7000 · Panel 1 · OIII. In-process with the watcher (`test_performance.py`): catalogued 2.7 s after the file appeared (2 s of that is the stability wait). On Docker Desktop the container gets no file events from macOS, so subs there are found by the active sweep (≤ 60 s); on a Linux NAS events arrive immediately. |
| V4 | Partial files | **Pass** | Slow-writer replay (`--chunked`): no partial entries. The first run found 4 ghost frames from half-written files because Docker Desktop reports stale sizes; fixed by checking the size the XISF or FITS header declares before hashing (`completeness.py`). |
| V5 | Nights after midnight | **Pass** | All 38 unique 10-07 lights (44 files with the BAD_ copies) are on the night of 7 October, including those after midnight. |
| V6 | Moves and renames | **Pass** | Folder moved, one sub renamed to BAD_ (NINA thumbs-down), one deleted: 20 copies recorded as moved, the renamed sub gained a NINA reject, the deleted one is not missing (the archive still has it). ExFAT under Docker Desktop renumbers inodes on rename, so these moves were found by hashing; same-inode moves (ext4, btrfs) skip hashing (`test_content_tracking.py`). |
| V7 | Missing content | **Pass** | 10 subs whose only copies were deleted: missing after the second sweep, dataset "Needs reconciliation"; accepting the loss in Reconcile cleared it. Restoring clears it too (`test_content_tracking.py`). |
| V8 | Replaced content | **Pass** | A capture file overwritten in place with different content: a new frame for the new content; the old frame lost that copy and kept its others. |
| V9 | No re-hashing | **Pass** | Unchanged rescan of 10,000 frames: nothing queued, 0.2 s (`test_performance.py`). Sweeps of the 689-file archive log "0 queued, 689 unchanged". |
| V10 | Missing headers | **Pass** | 10 real subs with FILTER and EXPTIME stripped (`scripts/strip_headers.py`): 20 items; the NINA file name pattern filled both, shown "from file name pattern #1"; removing it and one bulk correction also resolves them (`test_metadata_resolution.py`). |
| V11 | Bulk drop | **Pass †** | Workers stopped, 400 files (20 GB) dropped, workers started while 12 live subs arrived: the backlog finished in 66 s; live subs waited 1.5 s median (5.6 s worst) in the queue. Restart mid-queue resumes without re-hashing (`test_bulk_ingest.py`). |
| V12 | Ignore rules | **Pass** | Ignoring a folder in the UI covered its 12 known files; undo restored them. Content rules follow a moved sub; an ignored folder's new files aren't even hashed (`test_ignore.py`). |
| V13 | Multi-year dataset | **Partly** | The tree has no dataset spanning two nights (each panel and filter was shot on one night), so this is covered by tests only: per-night breakdowns and the Night page (`test_nights_api.py`). Needs data from two sessions of one panel. |
| V14 | Accounts | **Pass** | No session: 401. A standard user can read but gets "Only an admin can change this." for libraries and path patterns. Sign-up is closed (403). |

## End-to-end and accessibility

- `npx playwright test tests/e2e/ingest.spec.ts` (1.2 min): sign in; a new sub lands and its dataset count
  rises live; a sub without FILTER appears in Reconcile, is given OIII, and joins its dataset.
- `npx playwright test tests/e2e/a11y.spec.ts`: axe (WCAG 2.1 AA) on every screen in dark, light and night
  vision: no violations, after fixing the verdict icon's text alternative and the menu badge's contrast.

## Found and fixed during validation

Real data found these; each has a regression test.

1. Half-written files hashed under Docker Desktop (stale sizes): header-declared size check.
2. macOS `._` AppleDouble files crashed the watcher: skipped before stat; errors no longer stop it.
3. An empty capture folder was treated as an unmounted share and not looked at for 15 minutes: retried every 15 s.
4. A sweep that queued files left the library "idle" (next sweep in 15 minutes): it now counts as activity.
5. Frames showed as catalogued before their headers were read: new `pending` status.
6. A large backlog delayed every catalogue step behind all hashing: each sub is catalogued right after its hash.
7. Dates stored with an offset didn't parse back: `parse_date_obs` accepts offsets.
8. URL clashes (`/frames/metadata` read as a frame; `/path-patterns/preview` as a pattern id): a `sha256` path converter and route order.
9. NINA file names carry local clock time with summer time, so a time-capturing pattern disagreed with every DATE-OBS by about an hour: the NINA example leaves time to the header.

## Known gaps

- A copy of a sub whose header another tool rewrote is different content, so it counts as a second sub (seen
  when stripping headers). Flagging "same camera, same start time" as a likely duplicate is noted for later.
- Test artefacts in the local catalogue: the e2e run and V8 added three extra subs to NGC 7000 · Panel 1 · OIII
  (in `capture/e2e/` and `capture/live-1007/`).
