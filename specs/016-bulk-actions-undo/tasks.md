# Tasks: Bulk actions and undo (spec 016)

- [X] U1 (2026-10-15) `Change` model and migration; `services/changes.py` record and undo (FR-001..003)
- [X] U2 (2026-10-15) Verdicts and binning record changes and return `change_id`; `POST /frames/agree` (FR-004, FR-005)
- [X] U3 (2026-10-15) `GET /changes`, `POST /changes/{id}/undo`; tests: agree takes a night off the review list
  and undo restores it, a later verdict survives undo, binning undone by restoring, only the maker or an admin
- [X] U4 (2026-10-15) Toast actions; Undo after bulk verdicts, agreeing and binning; Ctrl/Cmd+Z; Activity → Your
  changes (FR-006); tests
- [X] U5 (2026-10-15) Subs tab: per-session Select all and Agree with N flagged; Agree with all flagged; Select all
  shown; screenshots
- [X] U6 (2026-10-15) Bulk selection and undo on calibration sets, Library datasets and Activity jobs (amendment
  2026-10-15, FR-007..011):
  - [X] U6a Change kinds `move`, `dismiss`, `qa` (catalogue migration 0023); undo for each, later changes kept
  - [X] U6b `POST /bulk/calibration-sets/build`; `POST /calibration-qa/override` records a `qa` change
  - [X] U6c `POST /bulk/datasets/regrade`, `/stack` (default rule), `/move` (records a `move` change)
  - [X] U6d `POST /work/bulk/jobs/retry` (admins), `/dismiss` (records a `dismiss` change)
  - [X] U6e Shared selection bar (count, buttons with text, Clear, Escape) and labelled choose boxes; on
    Calibration → Raw sets, a raw set's frames, the Library's Not in a collection list, a collection's Datasets
    tab and Activity → Recent failures; Undo through the toast, Ctrl/Cmd+Z and Your changes
  - [X] U6f Backend tests for every endpoint and undo (read-only refused, limits); frontend tests for each bar;
    screenshots (desktop and phone)
