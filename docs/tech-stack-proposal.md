# SubStation tech stack proposal (for agreement)

Status: agreed v4, 2026-10-09. v4: three services (frontend on Caddy, api, worker with Siril) instead of one container.
Previous: Changes from v2: SQLite instead of PostgreSQL; one container with an
internal worker supervisor (scale from the UI); queue and worker console (spec 005); host details are the
user's business. Evidence: `docs/spikes/`. Rules: `.specify/memory/constitution.md` (v2.0.0).

## Shape of the system

One image, one Compose service, one process supervisor inside it:

```
/data/library/*  (read-only mounts)          /data/substation  (read-write mount, local disk)
        │                                       ├─ substation.db (SQLite, WAL)
        ▼                                       ├─ work/  previews/  stacks/  config/
   watcher ──► jobs (in SQLite) ──► supervisor ──► worker 1..N ──► Siril pipe process each
                    ▲                      │           (psutil samples CPU% / RAM → SQLite)
                    │                      ▼
              web: API + live events ◄── browser: React + TypeScript UI
```

## Recommendation

| Concern | Recommendation | Why |
|---|---|---|
| Frontend | **React + TypeScript + Vite**: TanStack Query, Router and Table; Radix UI styled with `--sst-*` tokens; visx charts; react-hotkeys-hook | All UI in TypeScript; established libraries, only SubStation-specific parts written |
| Backend | **Python 3.12, Django 5.2 LTS + Django Ninja** (API only; no Python-rendered pages) | See "Why Django" below |
| Accounts and 2FA | django-allauth (headless mode for the React UI; TOTP, recovery codes, WebAuthn) | Logins now, 2FA a setting later |
| Database | **SQLite** in WAL mode, `transaction_mode=IMMEDIATE`, busy timeout; Django ORM and migrations | Zero admin, one file to back up, ample for this load (writes are small; heavy work happens in Siril) |
| Job queue | Enqueue via **Django's Tasks API** (`django.tasks`; `django-tasks` backport on 5.2); executed by SubStation's SQLite backend (atomic claim, priorities, retries, slots, progress) under our supervisor | No extra service; swappable standard interface; Huey was dropped in planning because its fixed worker pool cannot give live scaling and Siril-heavy slots (see specs/001 research R2) |
| Workers | In-container supervisor starts and stops 1..N worker processes on demand (spec 005), each owning one long-lived Siril pipe process; Siril-heavy slots limit parallel stacks | Scale from the UI, no Compose changes |
| Metrics | psutil per worker and Siril process every 1–2 s, short history in SQLite | Feeds the queue console |
| Live updates | Server-Sent Events from the web process, reading an events table | One-way updates are enough |
| File watching | watchdog (inotify) plus periodic scandir sweeps | Network-share changes are not notified |
| Identity | SHA-256 per new or changed file, queued; fingerprint (device, inode, size, mtime) to skip unchanged files | Constitution II |
| Engine | Siril 1.4.2 headless behind one adapter | Proven in both spikes |
| Pixel work | numpy, scipy, Pillow, astropy (QA detector, previews, flat ratios, headers) | Already written and validated in the spikes |
| Image | Debian (pinned snapshot) + Siril 1.4.2 + Python + built UI; multi-arch | Phase 1 proved it |
| Tests | pytest + pytest-django with spike golden fixtures; Siril adapter contract tests; Playwright | Constitution VI |
| Licence | GPL-3.0; dependencies MIT, BSD or Apache-2.0 | Compatible |

Constraint: `/data/substation` must be local storage to the container host (SQLite must not live on an
SMB or NFS share). Libraries can be anywhere, including network shares.

## Why Django

- The science must be Python whatever the web layer is: the QA leak detector, previews, stretch,
  flat ratios and header readers are numpy, scipy and astropy code proven in the spikes. A TypeScript
  backend would still need a Python worker, so two backend languages and a bridge between them.
- What the owner listed (real logins, 2FA later, an ORM with migrations, no hand-rolling) is exactly
  what Django ships: accounts, sessions, permissions, ORM, migrations and an admin, with django-allauth
  adding TOTP and WebAuthn as a setting. FastAPI would mean assembling SQLAlchemy, Alembic, an auth
  library and an admin by hand.
- The workers need the same models as the API (frames, jobs, verdicts). In Django they share one ORM
  and one schema in one codebase.
- Django Ninja gives typed, FastAPI-style endpoints and an OpenAPI schema, from which the React app
  generates a typed TypeScript client, so frontend and backend types stay in step.
- Django works well on SQLite, LTS releases have 3 years of support, and it is GPL-3.0-compatible (BSD).
- Django renders no UI here: the browser only ever sees the React app and JSON.

## Compose (whatever host it runs on)

```yaml
services:
  substation:
    image: ghcr.io/substation/substation:poc
    ports: [ "8080:8080" ]
    volumes:
      - /path/to/capture:/data/library/capture:ro     # one line per library, read-only
      - /path/to/substation:/data/substation          # local disk: database, work, previews, stacks
    restart: unless-stopped
```

## POC scope

1. Watcher, queue and catalogue for lights and imported masters (spec 001 stories 1–4).
2. Matching to existing masters (spec 002 story 1).
3. On-arrival calibrate, measure and grade with reasons (spec 003 story 1).
4. Sign-in, Datasets dashboard, dataset and night views with night chart and table (spec 003 stories
   2–3, no blink review).
5. Queue console with jobs, workers, CPU% and RAM, and worker count control (spec 005 stories 1–3).
6. Manual stack of a chosen scope with the default rule, kept with its recipe (spec 004 stories 1–2).

Exit criteria: on the live session, 95% of subs catalogued within 10 s and graded within 60 s; zero
writes to libraries; a 400-file drop processed without breaching those limits; two stacks running in
parallel visible in the console; grades agree with the spike grader on replayed spike data.

## Decision to confirm

Django + Django Ninja for the backend API (above), with React + TypeScript for all UI.

## Notes (2026-10-10)

- oxlint's `jsx-a11y/prefer-tag-over-role` is off: it asks for `<img>` instead of `role="img"`, but `role="img"` with
  `aria-label` is the accessible pattern for inline SVG charts and icons. axe checks them (frontend/tests/e2e/a11y.spec.ts).
- Frontend API types are generated from the live API's OpenAPI export (`npm run api:export && npm run api:gen`);
  the hand-written contracts in specs/ stay the spec, and the contract test requires every specified path to exist.
