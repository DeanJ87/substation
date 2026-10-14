#!/bin/sh
# Everything CI checks, locally, stopping at the first failure (005-DR-27). The backend tests need PostgreSQL on
# localhost:5432 (docker run -d -p 5432:5432 -e POSTGRES_USER=substation -e POSTGRES_PASSWORD=substation
# postgres:17-alpine) or SUBSTATION_DATABASE_URL pointing at one.
set -eu
cd "$(dirname "$0")/.."
export SUBSTATION_DATABASE_URL="${SUBSTATION_DATABASE_URL:-postgres://substation:substation@localhost:5432/substation}"

echo "== backend"
(
  cd backend
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy .
  uv run python manage.py makemigrations --check --dry-run >/dev/null
  uv run pytest -q
  uv run python manage.py export_openapi ../frontend/src/api/openapi.json
)
git diff --exit-code -- frontend/src/api/openapi.json

echo "== frontend"
(
  cd frontend
  npm run -s api:gen
  npx tsc -b
  npx oxlint src
  npx prettier --check .
  npx vitest run
)

echo "== stack"
SUBSTATION_DB_PASSWORD=x docker compose -f docker/compose.yml --env-file docker/.env.example config -q

echo "All checks passed."
