# Engine adapter (Siril)

The only component allowed to talk to Siril (constitution IV). Not implemented in spec 001, which is
header-only. This file fixes the interface later specs implement.

## Process model

- Siril 1.4.2 (`siril-cli`), pinned in the image, started with `-p -r <in fifo> -w <out fifo> -o`
  (pipe mode, offline), one long-lived process per worker that needs it.
- One command in flight per process. Completion is the `status: success <cmd>` or
  `status: error <cmd>` line, never the exit code. `ready` signals start-up; `status: busy` answers a ping
  during work.
- Every `log:` line is captured per command and returned with the result.
- Scripts start with `requires 1.4.0` (otherwise Siril runs nothing and still reports success).

## Interface (to be implemented in specs 002 to 004)

```python
class Engine:
    def run(self, command: str, *, timeout: float) -> CommandResult: ...  # status, log lines, seconds
    def ping(self) -> str: ...  # "ready" or "busy"
    def close(self) -> None: ...


class CommandResult:
    status: Literal["success", "error"]
    log: list[str]
    seconds: float
```

## Quirks the adapter must encode (from docs/spikes)

- `calibrate` and `calibrate_single` read FITS only: convert XISF with `load` + `save` first.
- Siril refuses to `cd` into read-only directories: stage inputs (symlinks inside the container).
- `select`/`unselect` take the 1-based position in the sequence, not the file number: map from the
  `.seq` `I` lines.
- FITS written by Siril are bottom-up; XISF is top-down; star-list Y is measured from the top.
- `-out="…"` keeps quote characters literally: never quote paths.
- Override `core.mem_ratio` (0.9 by default) and disable update checks.
