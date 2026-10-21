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
| `edge` | every build of the development branch: newest features, least tested (the `edge` git branch follows it) |
| `2194c51` | one commit, never changes |

Pick one with `SUBSTATION_VERSION`. Run all four containers on the same version.

## The folders

```
SUBSTATION_DATA/station      read-write: work files, previews, masters
SUBSTATION_DATA/postgres     read-write: the database
SUBSTATION_DATA/catalogues   Siril's star catalogues, for plate solving
your libraries               read-only unless you choose: one folder per library (capture folder, archive, …)
```

Each library is mounted at `/data/library/<name>` and shows in SubStation under that name. The reference compose
file has three slots:

| Variable | What |
| --- | --- |
| `SUBSTATION_LIBRARY`, `_NAME`, `_MODE` | the first library (required); mode `ro` (default) or `rw` |
| `SUBSTATION_LIBRARY_2`, `_2_NAME`, `_2_MODE` | a second, optional; its mode defaults to the first's |
| `SUBSTATION_LIBRARY_3`, `_3_NAME`, `_3_MODE` | a third, optional; its mode defaults to the first's |
| `SUBSTATION_LIBRARY_4`, `_4_NAME`, `_4_MODE` | a fourth, optional, read-only by default; name it `completed` for finished work (spec 020) |

A read-write mount isn't enough on its own: SubStation runs as user 1000 in its containers, and that user also needs
write permission on the folders themselves (for a Completed library, so it can write `project.json` into project
folders you create from another machine). On TrueNAS, an ACL entry does it without changing owners:
`setfacl -R -m u:1000:rwx,d:u:1000:rwx <folder>`.

Mount libraries read-only unless SubStation should write there. A library mounted read-write is writable for
everything SubStation does with files: the bin can delete there (once you allow it in Settings → Library → Bin),
and it can be an *active* or *archive* library, so collections can be archived to it or brought back from it
(Settings → Library → Folders). A read-only library can do none of these; Settings shows which variable to set.
More than three libraries: add a volume line per folder in an override file, under `/data/library/<name>`.

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
  environment variables, and switch on GitOps polling with "Re-pull image". Point it at the **`edge` branch** for
  `SUBSTATION_VERSION=edge`: that branch only moves once a commit's images are built, so Portainer never redeploys
  before the new images exist (a development branch moves first, and its images arrive minutes later).

An update stops the workers. Whatever they were doing goes back in the queue, and a stack picks up from what it
had finished (its calibrated and registered subs) rather than starting again, so updating while a long stack runs
costs minutes, not the whole stack.

## Backups

SubStation backs up its database every night (Settings → Backups: on or off, the time, how many to keep) as one
`.tar.gz` holding every table and a manifest. Your image files are not in it, only what SubStation knows about
them. Backups go to `station/backups` in your data folder by default. To keep them somewhere else, mount a folder
into the `api` and `worker` services (owned by user 1000) in an override file and name it in Settings → Backups:

```yaml
services:
  api:
    volumes: ["/mnt/pool/backups/substation:/backups"]
  worker:
    volumes: ["/mnt/pool/backups/substation:/backups"]
```

Settings → Backups also backs up on demand, downloads a backup, and restores one: new work pauses, running jobs
finish, and the whole database is replaced in one go. A backup restores into the same SubStation version that made
it.

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

## Post-processing helpers

GraXpert and RC-Astro run best on a machine with a GPU. A helper on that machine takes post-processing jobs from
SubStation over HTTPS (spec 010): set `SUBSTATION_HELPER_TOKEN` on the stack and the same token on the helper, and
`SUBSTATION_SKIP_QUEUES=finish,finish_ctl` so the workers leave those jobs to it.
