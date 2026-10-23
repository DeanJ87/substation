# Data model: Finished projects and the render read API (spec 020)

Models in `backend/apps/finished/models.py`; migrations `0001`..`0004`. Render data itself is not stored: it is built
on request (`render.py`) and described by [contracts/render-api.openapi.yaml](contracts/render-api.openapi.yaml).

```text
libraries.Library (role = completed)
  └─< FinishedProject >──<  catalogue.Project  ──> catalogue.Collection
        │   (linked_projects, M2M)    └─< catalogue.Dataset ─< catalogue.Frame (lights; grades, verdicts,
        ├─< FinishedFile                                         measurements, plate solves)
        └── Progression (1:1) ──> tasks.Task (current build job)
ApiToken (independent; created_by → User)
```

## FinishedProject

A folder `<kind>/<subject>/<name>/` in a Completed library holding at least one of `exports/`, `web/`, `social/`,
`project/`.

| Field | Notes |
|---|---|
| `library` | FK `libraries.Library`; cascade |
| `rel_path` | `kind/subject/name`; unique with `library` (identity) |
| `kind` | `astro`, `nightscapes`, `videos` (from the top folder, case-insensitive) |
| `subject`, `name` | folder names |
| `linked_projects` | M2M `catalogue.Project` (`related_name="finished"`) |
| `distance_ly`, `distance_source` | DR-13: `"manual"` or a SIMBAD source string; manual blocks look-ups |
| `missing` | folder not found on the last reachable scan |
| `files_changed_at` | newest file time seen, never in the future |
| `data_fingerprint`, `data_changed_at` | DR-11: hash of the render data's inputs and when it last changed; `data_changed_at` is the API's `updated_at` |
| `created_at`, `updated_at` | bookkeeping |

**Derived status** (not stored; `render.offered()` and the app): *not offered — its folder is missing*; *not linked*
(astro only); *needs a final image*; otherwise *offered*. Folders that do not fit the layout are reported by the scan
with a reason and are not stored.

**Relations to the catalogue**: render data reads the datasets of the linked projects (`Dataset.project`), their
catalogued light frames, effective verdicts, `MachineGrade`, `SubMeasurement` and solved `PlateSolve`s, and the
collection's names and constellation. It changes none of them. Deleting a linked catalogue project unlinks the
finished project with a warning; merging is refused when a project to be absorbed is linked (DR-17).

## FinishedFile

| Field | Notes |
|---|---|
| `project` | FK `FinishedProject`; cascade |
| `rel_path` | inside the project folder, e.g. `exports/heart-final.png`; unique with `project` |
| `section` | `exports`, `web`, `social` (outputs, may be served) or `project` (listed, never served) |
| `size_bytes`, `mtime` | from `stat`; their change clears `sha256` and moves `files_changed_at` |
| `sha256` | reserved; not filled at present (research Q1) |
| `missing` | gone from the folder on the last scan |
| `role` | `""`, `final`, `starless`, `stars`, `per_filter`, `progressive`, `step` |
| `role_filter` | `per_filter`: the normalised filter name (e.g. `Hα`) |
| `role_order` | `progressive` and `step`: 1, 2, 3 … |
| `role_label` | `step`: what was done (e.g. `GraXpert + NoiseXTerminator`) |
| `role_set_by_owner` | once any file in the project is set by the owner, guesses stop for that project |

**Validation**: a role can be given only to a PNG/JPEG/TIFF outside `project/`; `per_filter` needs a filter;
`progressive` and `step` need an order. Guessed `final` only in `exports/`; at most one final is kept by guessing.

**Served key** (`render.file_key`): `final`, `starless`, `stars`, `per_filter/<filter>`, `progressive/<n>`, `step/<n>`;
plus `thumb` (of the final) and `progression/<n>` (from `Progression`). The first file per key wins.

## ApiToken

| Field | Notes |
|---|---|
| `name` | up to 100 characters, required |
| `scope` | `render` (the only scope) |
| `digest` | SHA-256 of the secret; unique; the secret itself is returned once at creation and never stored |
| `hint` | last four characters of the secret |
| `created_by`, `created_at` | who and when |
| `expires_at` | optional; must be in the future when set; naive times read as UTC |
| `last_used_at` | updated at most once a minute |
| `revoked_at` | set once by revoke; never cleared |

`active` = not revoked and not expired; checked on every render call.

## Progression

One per finished project (`OneToOne`, cascade). Images are not stored in the database: each checkpoint's JPEG is
`STATION_ROOT/cache/progression/fp<project id>/<hash>.jpg`.

| Field | Notes |
|---|---|
| `state` | see transitions below |
| `reason` | why unavailable, failed, cancelled, waiting, or skipped automatically |
| `step`, `progress` | live progress of a build (0..1) |
| `task` | FK to the current queue job |
| `mapping` | `HOO`, `SHO`, `RGB`, `OSC` or `MONO` |
| `reference_frame` | SHA-256 of the pinned registration reference, kept between runs while still kept |
| `input_hash` | hash of algorithm version, mapping, channels, reference and inputs |
| `checkpoints` | `[{order, nights, label, integration_s, subs, filters, hash, file}]`, cumulative |
| `started_at`, `finished_at`, `updated_at` | bookkeeping; `finished_at` and checkpoint hashes feed the data fingerprint |

### State transitions

```text
          start(): availability() gives a reason
 none ─────────────────────────────────────────────▶ unavailable ──(start, now available)──▶ queued
  │  start(): inputs unchanged and all images cached ────────────────────────────────────▶ done
  │  start(auto): >30% of subs need calibrating again → stays none (or done), with a reason
  └─ start() ─▶ queued ─(worker)─▶ running ─┬─▶ done          (images written, cache pruned)
                  ▲                          ├─▶ failed        (error; reason = last line)
                  │                          ├─▶ cancelled     (cancelled in Activity)
                  └──── restart / interrupted┘   unavailable   (became unavailable when run)
 done | failed | cancelled ──(Generate or Rebuild; force)──▶ queued
```

`reconcile_progressions()` moves a `queued`/`running` progression whose job ended without it to the job's outcome
(cancelled, failed, or `none` when the job ended early with nothing built). A progression already `queued` or
`running` is left as it is unless forced.
