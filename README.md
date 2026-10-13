# SubStation

Every sub graded. Every decision explained.

SubStation watches the folders your capture software writes to, calibrates and grades each sub as it
lands, and stacks datasets into masters, on your own hardware. Free software under the GNU General Public
License v3.0.

**Status:** pre-release. Feature specifications live in `specs/`, project principles in
`.specify/memory/constitution.md`, the evidence behind them in `docs/spikes/`.

## Layout

| Path | Contents |
|---|---|
| `backend/` | Django 5.2 project: API (Django Ninja), task queue and supervisor, catalogue and ingest |
| `frontend/` | React + TypeScript (Vite) user interface |
| `docker/` | Container image and Compose example |
| `specs/` | Spec Kit specifications, plans and task lists |
| `docs/` | Design system, spike reports, tech stack decision, roadmap |

## Running

```bash
docker compose -f docker/compose.example.yml up -d
```

Mount capture folders read-only under `/data/library/<name>` and a local folder at `/data/substation`.
See `specs/001-ingest-catalogue/contracts/container.md`.

## Development

```bash
cd backend && uv sync && uv run pytest
cd frontend && npm install && npm run dev
```
