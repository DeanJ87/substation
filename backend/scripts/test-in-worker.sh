#!/bin/sh
# Run the Siril tests inside the worker image (the only image with siril-cli).
#   backend/scripts/test-in-worker.sh [pytest args]     default: -m siril
set -e
cd "$(dirname "$0")/../.."
IMAGE=${SUBSTATION_WORKER_IMAGE:-ghcr.io/substation/substation-worker:0.1}
ARGS=${*:--m siril}
docker run --rm --user root -v "$PWD/backend":/src/backend:ro -v "$PWD/specs":/src/specs:ro \
  -e UV_PROJECT_ENVIRONMENT=/tmp/venv -e UV_LINK_MODE=copy -e UV_CACHE_DIR=/tmp/uvcache \
  -v substation-uv-cache:/tmp/uvcache --entrypoint sh "$IMAGE" -c \
  "mkdir -p /tmp/r && cp -r /src/backend /src/specs /tmp/r/ && cd /tmp/r/backend && rm -rf .venv && \
   uv sync --frozen --python 3.12 -q && uv run pytest -p no:cacheprovider $ARGS -q"
