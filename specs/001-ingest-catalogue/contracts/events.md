# Contract: live events (Server-Sent Events)

`GET /api/v1/events` (authenticated session) returns `text/event-stream`. Each event has `id`
(monotonic integer, resumable with the `Last-Event-ID` header), `event` (type) and `data` (JSON).
A comment heartbeat is sent every 15 s. Events older than 24 h are pruned; a client resuming from a pruned
id receives `event: resync` and must refetch.

| Event | Data | Emitted when |
|---|---|---|
| `frame.catalogued` | `{sha256, frame_type, dataset_id, night, path}` | a new frame is catalogued |
| `frame.updated` | `{sha256, fields}` | metadata, classification or status changes |
| `copy.moved` | `{sha256, from, to}` | a move or rename is detected |
| `copy.missing` | `{sha256, path}` | a copy disappears |
| `dataset.updated` | `{dataset_id, sub_count, integration_s, state}` | membership, counts or state change |
| `reconciliation.opened` / `.resolved` | `{id, kind, frame?, dataset?}` | items change |
| `queue.changed` | `{ready_by_priority, running, failed}` | at most every 2 s while the queue changes |
| `library.status` | `{library_id, status, sweep_progress?}` | sweeps start or finish, reachability changes |
| `resync` | `{}` | client must refetch state |
