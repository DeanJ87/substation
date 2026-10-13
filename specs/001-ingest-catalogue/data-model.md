# Data model: Ingest and catalogue

SQLite via the Django ORM. Times are UTC. "User" means the Django user who made a change.
Fields marked *resolved* are denormalised copies of the winning `MetadataValue` for fast queries; the
`MetadataValue` rows are the source of truth.

## Library

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| name | text unique | directory name under `/data/library/` |
| mount_path | text | absolute path in the container |
| enabled | bool | |
| site_name, site_lat, site_lon | text, float, float, nullable | fallback when frames lack site headers |
| status | enum | `ok`, `unreachable`, `scanning` |
| last_full_sweep_at | datetime | |
| sweep_interval_active_s / idle_s | int | defaults 60 / 900 |

Discovered automatically from subdirectories of `/data/library`; admins enable or disable them.

## InstallationSettings

Singleton: site_name, site_lat, site_lon (nullable; fallback after the library's site), filter_aliases JSON
(for example `{"ha": "Hα", "halpha": "Hα"}`), updated_by, updated_at. Seeded from `SUBSTATION_SITE_*` environment
variables.

## Frame

One unique content.

| Field | Type | Notes |
|---|---|---|
| sha256 | char(64) PK | identity |
| size_bytes | bigint | |
| format | enum | `fits`, `fits_compressed`, `xisf` |
| image_count | int | XISF images in file |
| integration_index | int nullable | for masters: which image is the integration |
| frame_type | enum | `light`, `flat`, `dark`, `dark_flat`, `bias`, `master_dark`, `master_flat`, `master_bias`, `master_dark_flat`, `unknown` |
| classification_reason | text | |
| classification_source | enum | `header`, `rule`, `path_pattern`, `user` (user overrides are stored as a user `MetadataValue` for `frame_type` with user and time) |
| status | enum | `pending`, `catalogued`, `missing`, `ignored`, `error` |
| error | text nullable | parse errors |
| *resolved*: object, target, panel, filter_raw, filter_norm, exptime_s, ccd_temp_c, set_temp_c, gain, offset, xbin, ybin, camera, telescope, date_obs_utc, site_lat, site_lon | | from `MetadataValue` |
| night | FK Night nullable | |
| dataset | FK Dataset nullable | lights only |
| calibration_set | FK CalibrationSet nullable | calibration frames only |
| first_seen_at, catalogued_at | datetime | |

Indexes: (dataset, date_obs_utc), (night), (frame_type, filter_norm, exptime_s), (status).

State transitions: `(new)` → `pending` (hashed) → `catalogued` | `error`; `catalogued` ↔ `missing` (all copies gone after the
grace sweep / a copy reappears); any → `ignored` (content ignore rule) → previous state (rule removed).

## Copy

A path where a frame's content exists.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| frame | FK Frame | |
| library | FK Library | |
| rel_path | text | unique with library |
| st_dev, st_ino, st_size, st_mtime_ns | bigint | fingerprint |
| is_bad_prefixed | bool | name starts with `BAD_` |
| present | bool | |
| first_seen_at, last_seen_at, missing_since | datetime | |

## CopyEvent

Audit of file movements: `discovered`, `copied`, `moved` (from path → to path), `renamed`, `replaced`,
`missing`, `reappeared`; with frame, copy, library, details JSON, created_at.

## HeaderSnapshot

| Field | Type | Notes |
|---|---|---|
| frame | FK Frame (one per image index) | |
| image_index | int | |
| image_id | text | XISF image id, e.g. `integration` |
| geometry, sample_format | text | |
| keywords | JSON | FITS keywords (raw values, comments) |
| properties | JSON | XISF properties |

## MetadataValue

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| frame | FK Frame | |
| field | enum | `object`, `target`, `panel`, `filter`, `exptime`, `ccd_temp`, `set_temp`, `gain`, `offset`, `xbin`, `ybin`, `camera`, `telescope`, `date_obs`, `site_lat`, `site_lon`, `frame_type` |
| value | text (typed by field) | normalised value |
| raw | text | original text as found |
| source | enum | `header`, `folder_pattern`, `filename_pattern`, `inferred`, `settings`, `user` |
| source_detail | text | keyword name, pattern id, rule name |
| is_winner | bool | the resolved value |
| user | FK User nullable | for `user` source |
| created_at | datetime | |

Unique (frame, field, source, source_detail). Resolution: user > pattern with `prefer_over_header` >
header > pattern > inferred > settings. A user value is also stored as a `ContentCorrection` (below) so it
applies to future identical content.

## ContentCorrection

User-made value keyed by content: sha256, field, value, user, created_at. Applied whenever that content is
catalogued (survives the frame being forgotten and re-found).

## HeaderConflict

frame, field, values JSON (source → value), created_at. Shown on the frame; not a reconciliation item
unless the field cannot be resolved.

## UserVerdict

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| frame | FK Frame | |
| verdict | enum | `reject`, `accept`, `keep` (NINA thumbs-down is always `reject`; `source` tells NINA from in-app) |
| source | enum | `nina_bad_prefix`, `override` |
| copy | FK Copy nullable | the BAD_ copy that created it |
| user | FK User nullable | null for NINA |
| created_at | datetime | |

Machine grades are a separate entity in spec 003.

## PathPattern

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| library | FK Library nullable | null = all libraries |
| scope_glob | text | folder glob within the library, e.g. `ASIAIR/**` |
| kind | enum | `folder`, `filename` |
| pattern | text | grammar in `contracts/path-patterns.md` |
| prefer_over_header | JSON list of fields | |
| priority | int | ordering among patterns |
| enabled | bool | |
| created_by, created_at | | |

## IgnoreRule

kind (`folder`, `glob`, `content`), library nullable, value (path, glob or sha256), note, created_by,
created_at, active. Content rules apply wherever the content appears.

## Night

site_key (rounded lat/lon), date (observing night), site_lat, site_lon. Unique (site_key, date).

## Dataset

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| group_key | text unique | `target|panel|filter|camera|telescope|xbin x ybin|gain|offset`, built in code. Not a multi-column constraint: the key has NULLs and SQLite treats NULLs as distinct (Django silently skips `nulls_distinct=False` there) |
| target, panel, filter_norm, camera, telescope, xbin, ybin, gain, offset | | grouping fields |
| display_name | text | "NGC 7000 · Panel 3 · Hα" |
| state | enum | `ok`, `needs_reconciliation` (this spec); `awaiting_calibration`, `integrating`, `stale` (later specs) |
| state_reason | text | |
| sub_count, integration_s, first_utc, last_utc | | maintained |

## DatasetNight

dataset, night, sub_count, integration_s, first_utc, last_utc, user_rejected_count.

## CalibrationSet

Created with the foundational models (Frame references it).


type, camera, filter_norm (flats), exptime_s, gain, offset, xbin, ybin, set_temp_c, session_start_utc,
session_end_utc, night, frame_count, filter_blocks JSON (darks: frames per NINA filter label).

## ReconciliationItem

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| kind | enum | `missing_field`, `frame_missing`, `master_metadata`, `ambiguous_master`, `classification_unknown`, `bad_without_twin` (informational) |
| frame | FK nullable | |
| dataset | FK nullable | |
| field | text, empty when not field-specific | non-null so the open-item uniqueness index works |
| reason | text | plain English |
| suggestion | JSON | e.g. value from path, with source |
| status | enum | `open`, `resolved`, `dismissed` |
| resolution | JSON | value applied or action |
| resolved_by, resolved_at | | |

Opening an item for a light sets its dataset to `needs_reconciliation` until no open items remain.

## Task (queue)

| Field | Type | Notes |
|---|---|---|
| id | uuid PK | |
| name | text | e.g. `ingest.hash`, `ingest.catalogue`, `ingest.sweep` |
| args | JSON | |
| queue | text | `ingest`, `engine`, … |
| priority | int | -100..100 |
| slot | enum | `light`, `siril_heavy` |
| status | enum | `ready`, `running`, `succeeded`, `failed`, `cancelled` |
| attempts, max_attempts | int | |
| run_after | datetime | delays and backoff |
| progress | float, nullable | 0–1 |
| progress_note | text | |
| worker | FK Worker nullable | |
| enqueued_at, started_at, finished_at, heartbeat_at | datetime | |
| error | text nullable | |
| dedupe_key | text unique nullable | e.g. `hash:<library>:<path>:<mtime_ns>` so repeated sweeps do not enqueue twice |

Transitions: `ready` → `running` → `succeeded` | `failed` → (attempts < max) `ready` with backoff;
`running` with stale heartbeat (worker gone) → `ready`; `ready`/`running` → `cancelled` (admin).

## Worker and ResourceSample

Worker: id, pid, kind (`web`, `watcher`, `worker`), state, started_at, heartbeat_at, current task.
ResourceSample: worker, cpu_pct, rss_bytes, at (every 2 s, kept 15 min). Full use in spec 005.

## Event

id (autoincrement), type, payload JSON, created_at. Streamed over SSE; pruned after 24 h.
