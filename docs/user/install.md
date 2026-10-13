# Install with Compose

SubStation is three containers that work together:

| Service | What it does |
|---|---|
| `frontend` | Serves the web interface on one port |
| `api` | The catalogue and its database |
| `worker` | Watches your folders, reads files and does the heavy work (Siril lives here) |

All three must run on **the same machine**. The catalogue is a SQLite database, which needs a local disk.

## The `/data` layout

```
/data/substation          read-write, local disk: database, work files, previews and stacks
/data/library/<name>      read-only: one folder per library (capture folder, archive, …)
```

Each folder under `/data/library` becomes a library named after it. Mount every library **read-only**
(`:ro`); SubStation never needs to write there.

!!! warning "Keep `/data/substation` on local disk"
    Don't put `/data/substation` on a network share (SMB or NFS). SQLite needs real file locking, and a
    share can corrupt the catalogue. Your libraries can be anywhere, including shares.

## Start it

1. Copy `docker/compose.example.yml` and edit the volume lines: the local folder for `/data/substation`,
   and one line per library.
2. Set `SUBSTATION_ADMIN_USERNAME` and `SUBSTATION_ADMIN_PASSWORD` for the first admin account.
3. Optionally set your site (`SUBSTATION_SITE_LAT`, `SUBSTATION_SITE_LON`). SubStation reads the site from
   your headers when it can; this is the fallback for working out which night a sub belongs to.
4. Run:

    ```bash
    docker compose -f compose.yml up -d
    ```

5. Open `http://<your machine>:8080` and sign in. If port 8080 is taken, set `SUBSTATION_PORT`.

On first start SubStation reads every library. A large archive takes a while; the queue indicator in the
header shows how far it has got, and live subs still appear straight away.

## More workers

`SUBSTATION_WORKERS` sets how many files a worker container handles at once (2 by default). For more, either
raise it or run more worker containers on the same machine:

```bash
docker compose up -d --scale worker=3
```

Work is shared safely: each task runs once, and only one container watches the folders at a time. The number
of Siril stacks allowed at once is a separate setting, so more containers never means more stacks than your
memory allows.

## Updating

Pull the new images and run `docker compose up -d` again. The database is upgraded on start.
