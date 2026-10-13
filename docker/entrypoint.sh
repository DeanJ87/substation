#!/bin/sh
# SubStation entrypoint for the api and worker images (specs/001-ingest-catalogue/contracts/container.md).
#   entrypoint.sh api      migrate, create the bootstrap admin, serve the API on :8000
#   entrypoint.sh worker   wait for the database schema, then run watcher + workers (supervise --no-web)
#   entrypoint.sh helper   post-processing helper on any machine: no database or library, talks to SubStation over HTTPS
set -eu

ROLE="${1:-api}"
ROOT="${SUBSTATION_DATA_DIR:-/data}/substation"

if [ "$ROLE" != helper ] && [ ! -d "$ROOT" ]; then
  echo "SubStation can't start: $ROOT is missing. Mount a local folder there (see compose.example.yml)." >&2
  exit 1
fi
if ! touch "$ROOT/.write-test-$ROLE" 2>/dev/null; then
  echo "SubStation can't start: $ROOT is read-only. Mount it with write access. Your subs are untouched." >&2
  exit 1
fi
rm -f "$ROOT/.write-test-$ROLE"

FSTYPE="$(stat -f -c %T "$ROOT" 2>/dev/null || echo unknown)"
case "$FSTYPE" in
  nfs*|cifs|smb*|fuse.sshfs)
    echo "Warning: $ROOT is on a network filesystem ($FSTYPE). SubStation's database needs local disk;" >&2
    echo "expect 'database is locked' errors. Put /data/substation on storage local to the Docker host." >&2
    ;;
esac
mkdir -p "$ROOT/work" "$ROOT/previews" "$ROOT/stacks" "$ROOT/config"

case "$ROLE" in
  api)
    python manage.py migrate --noinput
    python manage.py bootstrap_admin
    exec python -m uvicorn substation.asgi:application --host 0.0.0.0 --port 8000 --proxy-headers \
         --forwarded-allow-ips='*'
    ;;
  worker)
    tries=0
    until python manage.py migrate --check >/dev/null 2>&1; do
      tries=$((tries + 1))
      if [ "$tries" -ge 120 ]; then
        echo "SubStation worker: the database schema is still not ready after 4 minutes. Is the api service running?" >&2
        exit 1
      fi
      sleep 2
    done
    exec python manage.py supervise --no-web
    ;;
  helper|finisher)
    # spec 010: post-processing only (SUBSTATION_ONLY_QUEUES=finish). RC-Astro is unpacked and activated here, onto
    # the /opt/finish volume, never baked into the image; a failure leaves GraXpert running and BXT steps skipped.
    TOOLS=/opt/finish
    if [ -n "${RC_ASTRO_INSTALLER_URL:-}" ] && ! ls "$TOOLS"/rc-astro/*/rc-astro >/dev/null 2>&1 \
        && ! [ -x "$TOOLS/rc-astro/rc-astro" ]; then
      echo "Fetching RC-Astro's CLI into $TOOLS/rc-astro" >&2
      mkdir -p "$TOOLS/rc-astro" && curl -fsSL -o "$TOOLS/rc-installer.sh" "$RC_ASTRO_INSTALLER_URL" \
        && sh "$TOOLS/rc-installer.sh" "$TOOLS/rc-astro" </dev/null >/dev/null 2>&1 || echo "RC-Astro unpack failed" >&2
      rm -f "$TOOLS/rc-installer.sh"
    fi
    RC="$(find "$TOOLS/rc-astro" -maxdepth 3 -type f -name rc-astro -perm -u+x 2>/dev/null | head -1)"
    if [ -n "$RC" ]; then
      export SUBSTATION_RC_ASTRO="$RC"
      if [ -n "${RC_ASTRO_EMAIL:-}" ] && [ -n "${RC_ASTRO_KEY:-}" ] && [ ! -f "$TOOLS/.rc-activated" ]; then
        ok=1
        for p in bxt nxt sxt; do
          "$RC" "$p" --activate "$RC_ASTRO_EMAIL" "$RC_ASTRO_KEY" >/dev/null 2>&1 || { ok=0; echo "RC-Astro $p: activation failed" >&2; }
        done
        "$RC" download-models >/dev/null 2>&1 || echo "RC-Astro: model download failed (offline?)" >&2
        [ "$ok" = 1 ] && touch "$TOOLS/.rc-activated"
      fi
    fi
    if [ "$ROLE" = helper ]; then
      # spec 010: a post-processing helper on any machine — asks SubStation for work over HTTPS, no database here
      exec python /app/backend/tools/substation_helper.py --url "${SUBSTATION_URL:?set SUBSTATION_URL}" \
           --host "${SUBSTATION_HELPER_NAME:-$(hostname)}"
    fi
    tries=0
    until python manage.py migrate --check >/dev/null 2>&1; do
      tries=$((tries + 1)); [ "$tries" -ge 120 ] && { echo "SubStation finisher: database not ready." >&2; exit 1; }
      sleep 2
    done
    exec python manage.py supervise --no-web --no-watcher
    ;;
  *)
    exec "$@"
    ;;
esac
