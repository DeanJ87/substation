"""Siril engine adapter (constitution IV; see README.md here). The only code that talks to Siril.

One long-lived `siril-cli` in pipe mode per worker process: commands go in through one named pipe,
`log:`/`status:` lines come back through the other. A command is finished when its `status: success <cmd>`
or `status: error <cmd>` line arrives, never by exit code. Proven in docs/spikes phase 1 step 4f.
"""

from __future__ import annotations

import atexit
import contextlib
import logging
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Literal

log = logging.getLogger("substation.engine")

STATUS = re.compile(r"^status: (\w+)(?: (.*))?$")
SETUP = (
    "requires 1.4.0",  # must come first, or Siril runs nothing and still says success
    "set32bits",
    "setext fit",
    "setcpu {threads}",
    "setmem {mem_ratio}",
    "set astrometry.update_default_scale=0",  # a solve mustn't change the focal length assumed for the next sub
)


def siril_env() -> dict[str, str]:
    """Siril 1.4 prepares its own Python environment in a background thread at start-up, from the first
    `python3` on PATH. If that is SubStation's virtualenv the preparation fails and can crash Siril mid-command
    (seen as exit −11 during `save`), so Siril gets a PATH without our virtualenv."""
    import sys

    ours = os.path.join(sys.prefix, "bin")
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP") and not k.startswith("UV_")
    }
    env["PATH"] = (
        os.pathsep.join(
            p for p in env.get("PATH", "").split(os.pathsep) if p and p != ours and "venv" not in p
        )
        or "/usr/bin:/bin"
    )
    return env


class EngineError(RuntimeError):
    """A Siril command failed; carries the command and its log for the user and the queue console."""

    def __init__(self, command: str, log_lines: list[str], message: str | None = None) -> None:
        self.command = command
        self.log = log_lines
        tail = "; ".join(line for line in log_lines[-3:] if line.strip())
        super().__init__(message or f"Siril couldn't run “{command.split()[0]}”: {tail or 'no details'}")


class EngineDied(EngineError):
    pass


@dataclass
class CommandResult:
    command: str
    status: Literal["success", "error"]
    log: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "success"


class Siril:
    current: str | None = None  # the command running now, if any

    def __init__(
        self,
        workdir: str = "/tmp",
        binary: str = "siril-cli",
        threads: int | None = None,
        mem_ratio: float = 0.5,
    ) -> None:
        self.workdir = workdir
        self.binary = binary
        self.threads = threads or max(1, (os.cpu_count() or 2) // 2)
        self.mem_ratio = mem_ratio
        self.proc: subprocess.Popen[str] | None = None
        self.version = ""
        self._lines: queue.Queue[str] = queue.Queue()
        self._lock = threading.RLock()  # run() may start the process, and start() runs setup commands

    # -- lifetime ------------------------------------------------------------------------------------
    def start(self, timeout: float = 60) -> None:
        if shutil.which(self.binary) is None:
            raise EngineDied("start", [], f"{self.binary} isn't installed in this container.")
        self._lines = queue.Queue()  # a fresh queue: a dead process's end-of-file must not reach the new one
        self._dir = tempfile.mkdtemp(prefix="siril-pipes-")
        cin, cout = os.path.join(self._dir, "in"), os.path.join(self._dir, "out")
        os.mkfifo(cin)
        os.mkfifo(cout)
        os.makedirs(self.workdir, exist_ok=True)
        self.proc = subprocess.Popen(
            [self.binary, "-p", "-r", cin, "-w", cout, "-o", "-d", self.workdir],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=siril_env(),
        )
        self._stdout: list[str] = []
        threading.Thread(target=self._drain_stdout, daemon=True).start()
        # Order matters: Siril opens its output pipe for writing, then its input for reading.
        self._out = open(cout)  # noqa: SIM115
        threading.Thread(target=self._read, daemon=True).start()
        self._in = open(cin, "w")  # noqa: SIM115
        self._wait(lambda line: line.strip() == "ready", timeout, "start")
        for cmd in SETUP:
            r = self.run(cmd.format(threads=self.threads, mem_ratio=self.mem_ratio), check=False)
            if not r.ok:
                log.warning("Siril setup command %r failed: %s", cmd, r.log[-2:])
        self._await_python_setup()
        try:
            out = subprocess.run([self.binary, "-v"], capture_output=True, text=True, timeout=20).stdout
            self.version = next(
                (ln.strip() for ln in out.splitlines() if re.search(r"\d+\.\d+", ln)), "siril"
            )
        except (OSError, subprocess.TimeoutExpired):
            self.version = "siril"
        log.info("Siril started (pid %s): %s", self.proc.pid, self.version)

    def _await_python_setup(self, timeout: float = 60) -> None:
        """Siril prepares its Python environment in a background thread after start-up. Work sent while that runs
        can crash Siril if the preparation fails, so wait for its outcome (or for it plainly not to start)."""
        end = time.monotonic() + timeout
        started = False
        while time.monotonic() < end:
            try:
                line = self._lines.get(timeout=1.0 if started else 3.0)
            except queue.Empty:
                if not started:
                    return  # no preparation began
                if not self.alive():
                    raise EngineDied(
                        "start", self._stdout[-5:], "Siril stopped while preparing its Python environment."
                    ) from None
                continue
            low = line.lower()
            if "python" in low or "venv" in low:
                started = True
                if (
                    "up-to-date" in low
                    and "checking" not in low
                    or "unable to install" in low
                    or "failed" in low
                ):
                    if "unable" in low or "failed" in low:
                        log.warning("Siril couldn't prepare its Python module; SubStation doesn't use it.")
                    return
        log.warning("Siril's Python preparation didn't finish within %.0f s; carrying on.", timeout)

    def _drain_stdout(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            self._stdout.append(line.rstrip())
            del self._stdout[:-200]

    def _read(self) -> None:
        for line in self._out:
            self._lines.put(line.rstrip("\n"))
        self._lines.put("<<EOF>>")

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.alive() else None  # type: ignore[union-attr]

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            if self.alive():
                self._in.write("exit\n")
                self._in.flush()
                self.proc.wait(10)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
        finally:
            self.proc = None
            shutil.rmtree(getattr(self, "_dir", ""), ignore_errors=True)

    # -- commands ------------------------------------------------------------------------------------
    def _wait(self, done, timeout: float, command: str, on_line=None) -> list[str]:  # noqa: ANN001
        got: list[str] = []
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise EngineError(
                    command, got, f"Siril took longer than {timeout:.0f} s on “{command.split()[0]}”."
                )
            try:
                line = self._lines.get(timeout=min(left, 1.0))
            except queue.Empty:
                self._stop_if_cancelled(command)
                if not self.alive():
                    raise EngineDied(
                        command,
                        got + self._stdout[-5:],
                        f"Siril stopped while running “{command.split()[0]}” (exit {self.proc.returncode if self.proc else '?'}"
                        f"; last output: {' | '.join(self._stdout[-3:]) or 'none'}).",
                    ) from None
                continue
            if line == "<<EOF>>":
                if self.proc is not None:
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        self.proc.wait(5)
                raise EngineDied(
                    command,
                    got + self._stdout[-5:],
                    f"Siril stopped while running “{command.split()[0]}” (exit "
                    f"{self.proc.returncode if self.proc else '?'}; last output: "
                    f"{' | '.join(self._stdout[-3:]) or 'none'}).",
                )
            got.append(line)
            if on_line is not None:
                try:
                    on_line(line)
                except Exception:  # noqa: BLE001 — progress reporting must never break a command
                    log.debug("progress callback failed", exc_info=True)
            if done(line):
                return got

    def _stop_if_cancelled(self, command: str) -> None:
        """A cancelled task stops Siril mid-command; it starts afresh for the next task."""
        from substation.tasks import Cancelled, cancel_requested

        if cancel_requested():
            log.info("Stopping Siril during “%s”: the task was cancelled.", command.split()[0])
            if self.proc is not None:
                self.proc.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    self.proc.wait(5)
            self.proc = None
            shutil.rmtree(getattr(self, "_dir", ""), ignore_errors=True)
            raise Cancelled(f"Cancelled during “{command.split()[0]}”.")

    def run(self, command: str, timeout: float = 600, check: bool = True, on_line=None) -> CommandResult:  # noqa: ANN001
        """Run one command and wait for its status line. Raises EngineError on failure if `check`. `on_line` sees
        every line Siril prints while the command runs ("progress: 42%", "log: …"), for live progress."""
        with self._lock:
            if not self.alive():
                self.start()
            name = command.split()[0]
            t = time.monotonic()
            self.current = command  # shown on the worker's row in Activity (005 T009)
            self._in.write(command + "\n")
            self._in.flush()

            def done(line: str) -> bool:
                m = STATUS.match(line)
                return (
                    m is not None
                    and m.group(1) in ("success", "error", "exit")
                    and (m.group(2) or "").startswith(name)
                )

            try:
                lines = self._wait(done, timeout, command, on_line)
            finally:
                self.current = None
            m = STATUS.match(lines[-1])
            status: Literal["success", "error"] = "success" if m and m.group(1) == "success" else "error"
            result = CommandResult(
                command,
                status,
                [line[5:] for line in lines if line.startswith("log: ")],
                round(time.monotonic() - t, 3),
            )
        if check and not result.ok:
            raise EngineError(command, result.log)
        return result

    def script(self, commands: list[str], timeout: float = 3600) -> list[CommandResult]:
        """Run commands one after another, stopping at the first failure (raised)."""
        return [self.run(c, timeout=timeout) for c in commands if c.strip() and not c.strip().startswith("#")]


# -- one engine per worker process --------------------------------------------------------------------
_engine: Siril | None = None
_engine_lock = threading.Lock()


_limits_checked = 0.0
_heavy_active = False  # a stacking-slot job holds a bigger memory share: leave the limits alone meanwhile


def limits() -> tuple[int | None, float]:
    """Siril threads and memory share from Settings → Workers (005 T003), else the environment. The default share
    divides 90% of free memory among this machine's workers, so eight Sirils can't each claim half of it."""
    from django.conf import settings

    threads, ratio = settings.SIRIL_THREADS, None
    try:
        from apps.libraries.models import InstallationSettings

        s = InstallationSettings.load()
        threads = s.siril_threads or threads
        ratio = s.siril_mem_ratio
        from datetime import timedelta

        from django.utils import timezone

        from substation.tasks.models import Worker, WorkerKind

        # every worker process on this machine, whatever container it is in
        workers = Worker.objects.filter(
            kind=WorkerKind.WORKER, heartbeat_at__gte=timezone.now() - timedelta(seconds=60)
        ).count() or (s.worker_count or settings.SUBSTATION_WORKERS)
    except Exception:  # noqa: BLE001 (no database yet, e.g. in tests of the engine alone)
        workers = settings.SUBSTATION_WORKERS
    if ratio is None:
        ratio = min(settings.SIRIL_MEM_RATIO, round(0.9 / max(1, int(workers)), 2))
    return threads, max(0.05, min(0.9, ratio))


def engine() -> Siril:
    """This process's Siril, started on first use and restarted if it died. Every minute it takes up any change to
    the threads and memory share in Settings → Workers (setcpu, setmem: no restart)."""
    global _engine, _limits_checked
    with _engine_lock:
        if _engine is None or not _engine.alive():
            from django.conf import settings

            if _engine is not None:
                _engine.close()
            threads, ratio = limits()
            _engine = Siril(workdir=str(settings.WORK_DIR), threads=threads, mem_ratio=ratio)
            _engine.start()
            _limits_checked = time.monotonic()
        elif time.monotonic() - _limits_checked > 60 and not _heavy_active:
            _limits_checked = time.monotonic()
            threads, ratio = limits()
            threads = threads or max(1, (os.cpu_count() or 2) // 2)
            if (threads, ratio) != (_engine.threads, _engine.mem_ratio):
                _engine.run(f"setcpu {threads}", check=False)
                _engine.run(f"setmem {ratio}", check=False)
                _engine.threads, _engine.mem_ratio = threads, ratio
                log.info("Siril limits now %s threads, %.0f%% of free memory", threads, ratio * 100)
        return _engine


@contextlib.contextmanager
def heavy_memory(share: float | None = None):  # noqa: ANN201
    """For a stacking-slot job (integrate, combine, build a master): Siril may use at least `share` of free memory
    (SUBSTATION_SIRIL_HEAVY_MEM, default 0.8) and every CPU this container has while it runs, then goes back to the
    per-worker share and threads. There is one stacking slot, so this can't overcommit the way giving every worker
    that much would (005 T003). With 2 threads and 60% a 135-sub stack ran over an hour (2026-10-13)."""
    global _heavy_active
    share = share if share is not None else float(os.environ.get("SUBSTATION_SIRIL_HEAVY_MEM", "0.8"))
    eng = engine()
    before, threads_before = eng.mem_ratio, eng.threads
    want = max(before, share)
    cores = max(threads_before, os.cpu_count() or threads_before)
    if want != before:
        eng.run(f"setmem {want}", check=False)
        eng.mem_ratio = want
    if cores != threads_before:
        eng.run(f"setcpu {cores}", check=False)
        eng.threads = cores
    _heavy_active = True
    try:
        yield eng
    finally:
        _heavy_active = False
        if eng.alive() and eng.mem_ratio != before:
            eng.run(f"setmem {before}", check=False)
            eng.mem_ratio = before
        if eng.alive() and eng.threads != threads_before:
            eng.run(f"setcpu {threads_before}", check=False)
            eng.threads = threads_before


def engine_pid() -> int | None:
    return _engine.pid if _engine is not None else None


@atexit.register
def _close() -> None:
    if _engine is not None:
        _engine.close()
