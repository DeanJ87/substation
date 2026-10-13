

- [X] T120 FrameType "processed" from PixInsight signatures and HISTORY; NAS also ignores */calibrated, */registered, */debayered, */approved (001-DR-11)
- [X] T121 (owner 2026-10-13) 8-bit captures of any type set aside by a content ignore rule at catalogue time
  (`apps/ingest/processed.py`); existing ones set aside once on the NAS; test in `tests/unit/test_processed_copies.py`
- [X] T122 (owner 2026-10-13) Site values out of the repo: compose variables, prepare-script variables, helper URL
  required, spike reports and e2e defaults without local paths
