# SubStation worker: watcher + task workers + Siril 1.4.2 (headless). The only image with Siril and the only
# service that mounts the libraries.   docker build -f docker/worker.Dockerfile -t substation-worker:dev .

# Debian testing (forky) pinned twice: the base image by digest and apt by a snapshot.debian.org date,
# so siril 1.4.2-1 resolves identically on every build (docs/spikes phase 1, risk 12).
FROM debian:forky-slim@sha256:3c80e257eff6274d593eb33a94bda5174ccd619836e6a728a73e11c97f2213e3
ARG DEBIAN_SNAPSHOT=20261008T000000Z
ARG SIRIL_VERSION=1.4.2-1
ENV DEBIAN_FRONTEND=noninteractive
RUN rm -f /etc/apt/sources.list.d/debian.sources \
 && echo "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} forky main" > /etc/apt/sources.list \
 && apt-get -o Acquire::Check-Valid-Until=false update \
 && apt-get install -y --no-install-recommends \
      "siril=${SIRIL_VERSION}*" "siril-common=${SIRIL_VERSION}*" ca-certificates tini procps \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv python install 3.12 && uv sync --frozen --no-dev --python 3.12
COPY backend/ ./

ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=substation.settings SUBSTATION_DATA_DIR=/data
RUN useradd -m -u 1000 substation && mkdir -p /data/library /data/substation && chown substation /data/substation
ARG SUBSTATION_VERSION=""
ENV SUBSTATION_VERSION=$SUBSTATION_VERSION
COPY docker/entrypoint.sh /entrypoint.sh
USER substation
# Let Siril prepare its Python environment now (from the system python3), not in the background during work.
RUN (printf "requires 1.4.0\n"; sleep 30) | env PATH=/usr/bin:/bin siril-cli -s - >/tmp/siril-venv.log 2>&1; \
    grep -iE "venv|python" /tmp/siril-venv.log || true
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["worker"]
