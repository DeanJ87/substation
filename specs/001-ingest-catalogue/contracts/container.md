# Contract: containers, filesystem and processes

Three services from one repository (revised 2026-10-09 at the owner's request; was one container):

| Service | Image | Mounts | Runs |
|---|---|---|---|
| `frontend` | Caddy + built React app | none | static UI; proxies `/api`, `/_allauth`, `/admin`, `/static` to `api:8000` (SSE unbuffered) |
| `api` | Python slim, no Siril | `/data/substation` | migrations, bootstrap admin, uvicorn on :8000 |
| `worker` | Debian + Siril 1.4.2 + Python | `/data/substation`, `/data/library/*` read-only | `supervise --no-web`: watcher + N workers (N changeable in the UI) |

Scaling: `docker compose up --scale worker=N` runs N worker containers (worker ids are prefixed with the container hostname; one watcher runs at a time by lease). Processes per container are set in the UI (spec 005). SubStation never creates containers itself (no Docker socket).

All three must run on the same host: the SQLite catalogue on `/data/substation` is shared, and needs local disk.

## Filesystem

| Path | Mode | Contents |
|---|---|---|
| `/data/library/<name>/` | read-only, zero or more | capture folders and archives; each subdirectory is a Library |
| `/data/substation/` | read-write, local disk | everything SubStation writes |
| `/data/substation/substation.db` (+ `-wal`, `-shm`) | | SQLite catalogue and queue |
| `/data/substation/work/` | | intermediates (later specs), bounded by the disk budget |
| `/data/substation/previews/` | | generated previews (later specs) |
| `/data/substation/stacks/` | | stacks and built masters (later specs) |
| `/data/substation/config/` | | `settings.toml`, secret key, path patterns export |

SubStation refuses to start if `/data/substation` is missing or not writable, and warns (does not
refuse) if it detects a network filesystem there. It never opens files under `/data/library` for
writing.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `SUBSTATION_ADMIN_USERNAME`, `SUBSTATION_ADMIN_PASSWORD` | none | bootstrap admin created on first start if no users exist |
| `SUBSTATION_PORT` | `8080` | HTTP port |
| `SUBSTATION_WORKERS` | `2` | initial worker count (changeable in the UI later) |
| `SUBSTATION_SECRET_KEY` | generated into `config/` | Django secret |
| `SUBSTATION_ALLOWED_HOSTS` | `*` | |
| `SUBSTATION_LOG_LEVEL` | `info` | |
| `SUBSTATION_SITE_NAME`, `SUBSTATION_SITE_LAT`, `SUBSTATION_SITE_LON` | none | seed for the installation site fallback (editable in Settings) |
| `TZ` | `UTC` | display only; never used for night calculation |

## Processes (`substation supervise` in the worker service)

| Process | Count | Role |
|---|---|---|
| watcher | 1 | inotify events and scheduled sweeps → path checks → tasks |
| worker | N (1..64) | claims tasks by priority and slot; samples CPU and RAM |

Health: `GET /api/v1/health` returns database, libraries and worker status. The supervisor restarts
crashed children with backoff and logs to stdout.

## Compose example

See `docker/compose.example.yml`.
