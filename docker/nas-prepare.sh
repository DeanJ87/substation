#!/bin/zsh
# One-off setup for a NAS (images now come from GHCR; this only makes folders, catalogues and the login):
#   NAS=user@nas ROOT=/path/on/nas/substation CATALOGUES=/local/path/to/catalogues docker/nas-prepare.sh
#   1. copy this source tree to ~/substation-src on the NAS (build outputs left out)
#   2. make $ROOT/{station,catalogues} on fast storage (via a container, in case the parent is root-owned)
#   3. copy Siril's offline star catalogues (2.1 GB) for plate solving
#   4. write the admin login to substation.env there (not in the repo), unless it exists
#   5. build the three images on the NAS (x86_64)
# The image library is never touched: the stack mounts it read-only.
set -euo pipefail
NAS=${NAS:?set NAS=user@host}
ROOT=${ROOT:?set ROOT to the folder on the NAS for SubStation}
CATALOGUES=${CATALOGUES:?set CATALOGUES to a local copy of the Siril star catalogues}
cd "${0:A:h}/.."

echo "1/5 source"
rsync -az --delete --exclude node_modules --exclude .venv --exclude dist --exclude __pycache__ --exclude .git \
  --exclude backend/var --exclude .claude --exclude '*.pyc' ./ "${NAS}:substation-src/"

echo "2/5 folders"
ssh "$NAS" "docker run --rm -v $(dirname "$ROOT"):/c alpine sh -c \
  'mkdir -p /c/$(basename "$ROOT")/station /c/$(basename "$ROOT")/catalogues && chown -R 1000:1000 /c/$(basename "$ROOT")/station && chown 3000:3000 /c/$(basename "$ROOT")/catalogues'"

echo "3/5 star catalogues"
rsync -a --chmod=Da+rx,Fa+r "$CATALOGUES/" "${NAS}:$ROOT/catalogues/"   # readable by the containers

echo "4/5 admin login"
if ! ssh "$NAS" "test -f $ROOT/substation.env"; then
  PW=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
  ssh "$NAS" "docker run --rm -i -v $ROOT:/c alpine sh -c 'cat > /c/substation.env && chmod 600 /c/substation.env'" \
    <<<"SUBSTATION_ADMIN_USERNAME=admin
SUBSTATION_ADMIN_PASSWORD=$PW"
  echo "   admin password: $PW   (also in $ROOT/substation.env on the NAS)"
fi

echo "5/5 build images on the NAS"
ssh "$NAS" 'cd ~/substation-src && \
  docker build -q -f docker/api.Dockerfile -t substation-api:nas . && \
  docker build -q -f docker/worker.Dockerfile -t substation-worker:nas . && \
  docker build -q -f docker/frontend.Dockerfile -t substation-frontend:nas .'
echo "done: images built; the stack can be created in Portainer from docker/compose.nas.yml"
