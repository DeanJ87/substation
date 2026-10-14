# Docker

| File | Image | Contents |
|---|---|---|
| `frontend.Dockerfile` + `Caddyfile` | `substation-frontend` | built React app on Caddy; proxies `/api`, `/_allauth`, `/admin` to the API |
| `api.Dockerfile` | `substation-api` | Django API (uvicorn), migrations, bootstrap admin; no Siril |
| `worker.Dockerfile` | `substation-worker` | watcher, task workers and Siril 1.4.2; mounts the libraries |
| `finisher.Dockerfile` | `substation-finisher` | a post-processing helper (GraXpert, RC-Astro) for another machine |
| `entrypoint.sh` | all | `api`, `worker` or `helper` role |
| `compose.yml` + `.env.example` | | the reference stack: PostgreSQL and the three services |
| `compose.traefik.yml` | | an override for running behind Traefik |
| `compose.helper.yml` | | a helper on a Linux machine with an NVIDIA GPU |

Installing and updating: `docs/user/install.md`.
