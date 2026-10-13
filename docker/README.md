# Docker

| File | Image | Contents |
|---|---|---|
| `frontend.Dockerfile` + `Caddyfile` | `substation-frontend` | built React app on Caddy; proxies `/api`, `/_allauth`, `/admin` to the API |
| `api.Dockerfile` | `substation-api` | Django API (uvicorn), migrations, bootstrap admin; no Siril, no library mounts |
| `worker.Dockerfile` | `substation-worker` | watcher, task workers and Siril 1.4.2; the only service that mounts libraries |
| `entrypoint.sh` | api, worker | `api` or `worker` role |
| `compose.example.yml` | | the three services and their mounts |

Build all three from the repository root: `docker compose -f docker/compose.example.yml build`.
