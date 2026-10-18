# Tasks: Archive collections (spec 013)

- [X] A1 Library role (active / archive / none) and the active library's archive target; migration; Settings → Library
- [X] A2 Move service: copy, verify hash, record the new copy, remove the original; same relative path; collision
  rules (FR-003, FR-004); resumable from the copies already recorded; tests including a mid-move restart
- [X] A3 Which files move: the collection's lights, and calibration frames used only by it (FR-002, FR-005); test
- [X] A4 Queued job with progress and cancel; scans skip files of a collection being moved (FR-006, FR-007)
- [X] A5 Archive and Bring back on the collection page with a preview of files, size and direction; where its files
  are (FR-009)
- [X] A6 Library filter by location; suggestions with the days setting and dismiss (FR-010)
- [X] A7 Accessibility check (007-DR-27) and screenshots of the collection page and Library

Notes (2026-10-17): roles on `Library` (`role`, `archive_to`; libraries migration 0012); `CollectionMove` and
`MoveItem`, `Collection.archive_dismissed_at`, change kind `archive` (catalogue migration 0024). Service
`apps/catalogue/services/archive.py`; job `apps/ingest/tasks/archive.py`; API `apps/catalogue/api_archive.py`
(`GET /collections/{id}/files`, `GET /collections/{id}/move-preview`, `POST /collections/{id}/move`,
`POST /moves/{id}/cancel`, `POST /collections/{id}/archive-suggestion/dismiss`); sweeps skip frames being moved.
Tests: `tests/unit/test_archive.py`; `CollectionFiles.test.tsx`, `LibraryAccess.test.tsx`. Screenshots of the
collection page (desktop and phone, confirm step, a move under way, a read-only refusal), Settings → Library and
the Library's filter checked.

- [X] A8 (2026-10-17) Compose: per-library modes and a third library slot (013-DR-03); deploy guide and
  `.env.example`; `SUBSTATION_LIBRARY_NAMES` for the read-only reason (013-DR-02)
- [X] A9 (2026-10-17) Settings → Library → Folders: mounted read-write or read-only, role and archive controls
  disabled with the reason when read-only, the suggestion days setting (013-DR-01, 013-DR-04, 013-DR-08)
- [X] A10 (2026-10-17) Archive and bring back recorded as undoable changes (013-DR-09); Activity names the job and
  its result
- [ ] A11 (2026-10-18, open) First run on the real library: Bring back the smallest collection from `organised`
  (archive) to `active`, verify every file by hash at the destination, the originals gone, frame/master counts and
  no files reported missing; then Archive it back and verify again. Record the result here
