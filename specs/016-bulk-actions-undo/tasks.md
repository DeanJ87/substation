# Tasks: Bulk actions and undo (spec 016)

- [X] U1 (2026-10-15) `Change` model and migration; `services/changes.py` record and undo (FR-001..003)
- [X] U2 (2026-10-15) Verdicts and binning record changes and return `change_id`; `POST /frames/agree` (FR-004, FR-005)
- [X] U3 (2026-10-15) `GET /changes`, `POST /changes/{id}/undo`; tests: agree takes a night off the review list
  and undo restores it, a later verdict survives undo, binning undone by restoring, only the maker or an admin
- [X] U4 (2026-10-15) Toast actions; Undo after bulk verdicts, agreeing and binning; Ctrl/Cmd+Z; Activity → Your
  changes (FR-006); tests
- [X] U5 (2026-10-15) Subs tab: per-session Select all and Agree with N flagged; Agree with all flagged; Select all
  shown; screenshots
- [ ] U6 Bulk selection and undo on calibration sets, Library datasets and Activity jobs (Later)
