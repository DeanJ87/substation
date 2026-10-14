# SubStation finisher (spec 010): runs only the "finish" queue — master post-processing with GraXpert and, when the
# owner supplies a licence, RC-Astro's BlurXTerminator / NoiseXTerminator / StarXTerminator. Separate from the
# worker so these jobs can move to GPU hardware that mounts the same /data/substation.
#   docker build -f docker/finisher.Dockerfile -t substation-finisher:dev .
#
# GraXpert (GPL-3.0) is baked in, pinned by version and checksum. RC-Astro's tools are proprietary: never in this
# image. The entrypoint unpacks them onto the persistent /opt/finish volume at first start, from
# RC_ASTRO_INSTALLER_URL, and activates them with RC_ASTRO_EMAIL / RC_ASTRO_KEY (compose variables, never in git).
FROM python:3.14-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends procps \
      tini curl ca-certificates unzip libgl1 libglib2.0-0 libgomp1 libx11-6 libxext6 libxrender1 libfontconfig1 \
 && rm -rf /var/lib/apt/lists/*

ARG GRAXPERT_VERSION=4.0.0
ARG GRAXPERT_SHA256=bbefcfe43f29482d3f0a78fc87fed6818fdb9c1627aeb22a3b4cfaae9aacb8aa
RUN curl -fsSL -o /tmp/gx.zip \
      "https://github.com/Dark-Matters-Astro/GraXpert/releases/download/${GRAXPERT_VERSION}/GraXpert-linux.zip" \
 && echo "${GRAXPERT_SHA256}  /tmp/gx.zip" | sha256sum -c - \
 && unzip -q /tmp/gx.zip -d /opt && rm /tmp/gx.zip \
 && chmod +x /opt/GraXpert-linux/GraXpert && ln -s /opt/GraXpert-linux/GraXpert /usr/local/bin/GraXpert-linux

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --python /usr/local/bin/python3.12
COPY backend/ ./
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=substation.settings SUBSTATION_DATA_DIR=/data \
    SUBSTATION_ONLY_QUEUES=finish HOME=/opt/finish/home
RUN useradd -m -u 1000 substation && mkdir -p /data/substation /opt/finish/home \
 && chown -R substation /data/substation /opt/finish
ARG SUBSTATION_VERSION=""
ENV SUBSTATION_VERSION=$SUBSTATION_VERSION
COPY docker/entrypoint.sh /entrypoint.sh
USER substation
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["helper"]
