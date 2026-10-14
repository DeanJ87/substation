# SubStation API: Django (uvicorn). No Siril, no access to the libraries.
#   docker build -f docker/api.Dockerfile -t substation-api:dev .
FROM python:3.14-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends tini curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --python /usr/local/bin/python3.12
COPY backend/ ./

ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=substation.settings SUBSTATION_DATA_DIR=/data
# Django admin's own static files, served by WhiteNoise under /static/
RUN SUBSTATION_DATA_DIR=/tmp/build-data python manage.py collectstatic --noinput >/dev/null
RUN useradd -m -u 1000 substation && mkdir -p /data/substation && chown substation /data/substation
ARG SUBSTATION_VERSION=""
ENV SUBSTATION_VERSION=$SUBSTATION_VERSION
COPY docker/entrypoint.sh /entrypoint.sh
USER substation
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
  CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["api"]
