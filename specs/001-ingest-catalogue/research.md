# Research: Ingest and catalogue

Phase 0 decisions for spec 001. Each entry: decision, rationale, alternatives.

## R1. SQLite configuration for several writers

- **Decision**: SQLite in WAL mode; Django `OPTIONS = {"transaction_mode": "IMMEDIATE", "timeout": 20,
  "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;"}`;
  no `ATOMIC_REQUESTS`; every write transaction kept short (per file, never around I/O or hashing).
- **Rationale**: `transaction_mode` and `init_command` are available from Django 5.1 (Django 5.2
  database docs); `IMMEDIATE` makes waiters respect `timeout` instead of failing with "database is locked".
  Writers here are small (one frame or copy row at a time); heavy work happens outside transactions.
- **Alternatives**: PostgreSQL (rejected by the owner: heavier, extra service). DEFERRED transactions
  (lock upgrade failures under contention).
- **Constraint**: the database must be on storage local to the container host (WAL needs shared memory
  and reliable locking; not SMB or NFS).

## R2. Job queue on SQLite

- **Decision**: enqueue through the Django Tasks API (`django.tasks` in Django 6.x; the `django-tasks`
  backport on 5.2), with priorities (-100..100) and queue names. Execution by SubStation's own backend:
  a `Task` table claimed atomically with `UPDATE … SET status='running', worker=? WHERE id=(SELECT id …
  WHERE status='ready' AND run_after<=now AND slot available ORDER BY priority DESC, enqueued_at
  LIMIT 1) RETURNING …` inside an IMMEDIATE transaction (SQLite ≥ 3.35). Retries with backoff, run-after
  scheduling, progress field, heartbeat-based recovery of jobs whose worker died.
- **Rationale**: no SQLite-backed library offers dynamic worker counts, resource slots, progress and
  metrics together (spec 005). Huey: one consumer per instance with fixed workers; Procrastinate:
  PostgreSQL only; Celery/RQ: Redis; django-tasks-db: no retries yet (attempts 0 or 1). Using the
  standard Tasks API keeps callers independent of the backend.
- **Alternatives**: Huey (fixed worker pool, no slot model), django-q2 (cluster restart to rescale).
- **Priorities**: live 80, bulk 40, archive 10, stacking and QA set per spec 005; ties by enqueue time.
  A file is "live" if its modification time is within 15 minutes when first seen.

## R3. Supervisor and processes

- **Decision**: container entrypoint runs `substation supervise` (Django management command) which
  starts and monitors: uvicorn (ASGI web and SSE), the watcher, and N worker processes (N from settings,
  changeable at runtime). Crashed children restart with backoff. Each worker samples its own CPU and RAM
  with psutil.
- **Rationale**: one container, scaling without restart.
- **Alternatives**: s6-overlay or supervisord (static process lists), Compose `scale` (needs the owner to
  edit the stack).

## R4. Detecting changes on network shares

- **Decision**: periodic sweep per library with `os.scandir` (default every 60 s for libraries with
  recent activity, every 15 min otherwise, plus on start-up and on demand) and watchdog inotify events
  where they arrive (local disks). Both feed the same "path check".
- **Rationale**: inotify does not report changes made by another machine on SMB or NFS mounts (the NINA
  PC writing to a NAS share). Sweeps are cheap: `scandir` returns stat data without extra calls.
- **Path check**: skip `._*`, `.DS_Store`, non-image extensions and ignore rules; look up `Copy` by
  (library, relative path); if fingerprint (st_dev, st_ino, st_size, st_mtime_ns) unchanged, update
  `last_seen` only; if the same (st_dev, st_ino, size, mtime_ns) is known at another path, record a
  move without re-hashing (same file object, unchanged); otherwise enqueue a hash job.
- **Stability**: a hash job first checks that size and mtime are unchanged across 2 s; if not, it
  re-schedules itself (run-after +2 s) up to 5 minutes, then reports "file kept changing".

## R5. Identity and hashing

- **Decision**: SHA-256 over the whole file, streamed in 8 MiB chunks, in hash jobs. One frame per
  digest; copies reference it. Fingerprints only skip re-hashing (constitution II).
- **Rationale**: exact identity; NINA subs are 52 MB, so a hash costs about 0.1–0.5 s of I/O on a NAS;
  queued so bursts never block live files. For bulk 400 × 52 MB ≈ 21 GB at ~100 MB/s ≈ 3.5 min.
- **Alternatives**: partial or sampled hashes (identity not exact), XISF embedded checksums (only some
  writers include them; used as an optional cross-check, not identity).

## R6. Moves, copies, deletions and replacements

- **Decision**:
  - New path whose content hashes to a known frame → new `Copy`; if a copy of that frame vanished in
    the same or previous sweep, log `CopyEvent(moved)`, else `CopyEvent(copied)`.
  - Path not seen in a complete sweep of a reachable library → copy `missing`; a frame with no present
    copies becomes `missing` only after a grace period of one further sweep (so out-of-order moves
    settle), then a reconciliation item is opened.
  - Same path, different content → old copy detached (`CopyEvent(replaced)`), new frame catalogued.
  - Library unreachable (mount empty or erroring) → sweep aborted; nothing marked missing.
- **Rationale**: spec 001 stories 2 and 4; constitution V (moves are automatic, losses reconciled).

## R7. Header reading

- **Decision**: FITS via `astropy.io.fits.getheader` (header only; `.fz` compressed handled by astropy);
  XISF via the `xisf` package's metadata parsing (header block only, no pixel reads), with multi-image
  support. Raw keywords stored per frame (`HeaderSnapshot`).
- **Rationale**: spike header reads took ~3 ms per file without pixel access. `xisf` is GPL-3.0, which
  matches the project licence. If `xisf` ever reads pixel data on open, fall back to the spike's
  header-only reader (`docs/spikes`, phase 1 `hdr.py`).

## R8. Metadata resolution

- **Decision**: per field, ordered sources: header → path pattern (most specific scope first) →
  user value. A user value always wins for that frame. A `PathPattern` may set `prefer_over_header` for a
  field and scope. Each field has a normaliser (filter names: strip, case-fold, aliases; temperatures and
  exposures: floats; times: UTC ISO). Conflicts between sources are stored.
- **Patterns**: the `parse` library (format-string inverse) with SubStation token names and typed
  converters; grammar in `contracts/path-patterns.md`.
- **Night**: `date(UTC start + longitude/15 h − 12 h)`; longitude from resolved SITELONG / LONG-OBS,
  else the library's or installation's site setting (flagged as "from settings").

## R9. Classification

- **Decision**: normalise IMAGETYP variants (`LIGHT`, `Light Frame`, `FLAT`, `Flat Field`, `DARK`,
  `Dark Frame`, `BIAS`, `Bias Frame`, `Master Dark`, `Master Flat`, `Master Bias`, XISF `imageType`),
  then: dark with `OBJECT=FlatWizard` or exposure equal to a flat set on the same night → dark flat;
  multi-image XISF with an `integration` image or `IMAGETYP` "Master …" → master; else path pattern
  `{type}`; else reconciliation. Reason stored as text.

## R10. Grouping

- **Decision**: datasets keyed by (target, panel, filter, camera, telescope, xbin, ybin, gain, offset) on
  resolved values; target and panel from OBJECT `^(.*?)\s+Panel\s+(\d+)$`; datasets span nights
  (`DatasetNight` keeps per-night counts). Calibration sets keyed by (type, filter for flats, exposure,
  gain, offset, binning, set temperature) and split into sessions where frames are more than 2 h apart;
  incremental maintenance on each new frame, merging sessions that a new frame bridges.
- **Regrouping**: a metadata change recomputes the frame's dataset or set in the same transaction and
  emits `dataset.updated` events.

## R11. Accounts in this feature

- **Decision**: django-allauth headless with the browser client and session tokens (cookies plus CSRF),
  `HEADLESS_ONLY = True`, signup closed via the account adapter (admins create users), login by username
  or email. A bootstrap admin is created from an environment variable on first start. MFA settings
  (`MFA_SUPPORTED_TYPES` with TOTP and recovery codes) are planned in spec 003; its headless support
  must be confirmed there.
- **Rationale**: constitution VIII applies to every UI, including the catalogue.

## R12. Live updates

- **Decision**: workers append rows to an `Event` table; the web process streams them as Server-Sent
  Events, polling the table every 500 ms per connection with `Last-Event-ID` resume, and old events are
  pruned after 24 h. Contract in `contracts/events.md`.
- **Rationale**: SQLite has no LISTEN/NOTIFY; 500 ms polling is cheap and meets the 10 s goal.

## R13. Fixtures

- **Decision**: tests use header-only extracts of real files (FITS and XISF headers kept verbatim, pixel
  data replaced by a tiny array) for every trap: NINA lights, BAD_ twins, WBPP multi-image masters, flats
  and FlatWizard darks, AppleDouble files, files with stripped FILTER and EXPTIME. A manifest records the
  source file and SHA-256 of each original. The full golden run reads the real spike trees
  (`SUBSTATION_GOLDEN_DIR`) and compares counts with the spike reports.
- **Rationale**: constitution VI (real data) without committing 42 GB to the repository.
