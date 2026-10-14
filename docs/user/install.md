# Install and update

SubStation is four containers that work together:

| Service | What it does |
|---|---|
| `frontend` | Serves the web interface on one port |
| `api` | The catalogue and its API; upgrades the database on start |
| `worker` | Watches your folders, reads files and does the heavy work (Siril lives here) |
| `postgres` | The catalogue's database |

The project publishes images and a reference stack; how and when you roll out a new version is up to you. Every
way below uses the same images.

## Versions

Images are on GitHub's registry, `ghcr.io/deanj87/substation-{frontend,api,worker}`, tagged:

| Tag | What it is |
|---|---|
| `1.4.2` | one release, never changes |
| `1.4` | the newest patch of 1.4: fixes only |
| `latest` | the newest release |
| `edge` | every build of the development branch: newest features, least tested |
| `2194c51` | one commit, never changes |

Pick one with `SUBSTATION_VERSION`. Run all four containers on the same version.

## The folders

```
SUBSTATION_DATA/station      read-write: work files, previews, masters
SUBSTATION_DATA/postgres     read-write: the database
SUBSTATION_DATA/catalogues   Siril's star catalogues, for plate solving
your libraries               read-only: one folder per library (capture folder, archive, …)
```

Each library is mounted at `/data/library/<name>` and shows in SubStation under that name. Mount libraries
read-only; SubStation never writes there unless you switch on the bin's deleting (Settings → Bin) and mount
that library read-write.

Put `SUBSTATION_DATA` on fast local storage (an SSD). Libraries can be anywhere, including network shares.

## Docker Compose

1. Copy `docker/compose.yml` and `docker/.env.example` (as `.env`) into a folder.
2. Fill in `.env`: where `SUBSTATION_DATA` is, your library folder, the admin password, a database password
   (`openssl rand -hex 24`) and the version.
3. `docker compose up -d`, then open `http://<your machine>:8080` and sign in.

Behind a reverse proxy, add an override: `docker/compose.traefik.yml` is one for Traefik
(`docker compose -f compose.yml -f compose.traefik.yml up -d`, with `SUBSTATION_DOMAIN` and `SUBSTATION_URL`).

On first start SubStation reads every library. A large archive takes a while; the header shows how far it has
got, and new subs still appear straight away.

## Updating

- **By hand**: `docker compose pull && docker compose up -d`. The database is upgraded on start.
- **Automatically**: an image watcher (Watchtower, or diun to be told instead) on `edge`, `1.4` or `latest`.
- **Portainer**: add the stack from this repository (Stacks → Add stack → Repository: `docker/compose.yml`, plus
  `docker/compose.traefik.yml` as an additional file if you use Traefik), put your `.env` values in the stack's
  environment variables, and switch on GitOps updates with "Re-pull image" and "Force redeployment", so a new
  image on your tag is picked up even when the files haven't changed.

An update stops the workers. Whatever they were doing goes back in the queue, and a stack picks up from what it
had finished (its calibrated and registered subs) rather than starting again, so updating while a long stack runs
costs minutes, not the whole stack.

## Kubernetes (k3s and others)

Run PostgreSQL (a managed one, or an operator such as CloudNativePG) and the three SubStation images as
Deployments:

- `api` and `frontend`: any number of replicas; `GET /api/v1/health` for readiness and liveness on the API.
- `worker`: as many replicas as you like; work is shared through the database. Each needs the station volume and
  the libraries, so those must be volumes every worker node can mount (ReadWriteMany for the station, read-only
  for libraries).
- Settings come from environment variables as in `.env.example`; the database password from a Secret, via
  `SUBSTATION_DATABASE_PASSWORD_FILE`.
- Give workers `terminationGracePeriodSeconds: 90`; a stopped worker hands its work back and it resumes.

A Helm chart is planned. Until then these are the pieces it will contain.

## SQLite instead of PostgreSQL

Without `SUBSTATION_DATABASE_URL`, SubStation keeps its catalogue in SQLite at `/data/substation/substation.db`.
That suits one machine with the station folder on a local disk; it doesn't work on network storage or across
several machines.

To move an existing SQLite installation to PostgreSQL, point the reference stack's `SUBSTATION_DATA` at the
folder that holds `station/substation.db` and set `SUBSTATION_IMPORT_SQLITE=1` for the first start. The API brings
the SQLite file up to date, copies every row into the new, empty PostgreSQL in one transaction, and renames the file
to `substation.db.imported-<time>`; the workers start once it's done. If anything fails, nothing is half-copied and
the file stays where it was. Remove the variable afterwards. (By hand, the same is `manage.py copy_database
<file>`; it refuses a database that already has data unless you add `--replace`.)

## Post-processing helpers

GraXpert and RC-Astro run best on a machine with a GPU. A helper on that machine takes post-processing jobs from
SubStation over HTTPS (spec 010): set `SUBSTATION_HELPER_TOKEN` on the stack and the same token on the helper, and
`SUBSTATION_SKIP_QUEUES=finish,finish_ctl` so the workers leave those jobs to it.
