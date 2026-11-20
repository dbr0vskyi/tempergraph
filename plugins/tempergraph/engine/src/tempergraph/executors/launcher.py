"""The session launcher: the one place a model session's process is started (EXI §2.3, SEC §2.2).

It owns what the engine must not delegate to a CLI: list argv, the prompt on stdin written right after
spawn (EXI-B2), the wall-clock timeout (EXI-B3), the idle watchdog (EXI-B4), the process tree's lifetime
(EXI-B5), the stop contract (EXI-B15), the prompt-gap record (EXI-B13), the caller variables (PRV §4)
and the raw stream files under the session folder (LOS §2.1). It also runs the executors' model-free
probes and the host-speed timing (EXI-B14), so every executor launch stays at this one site.
"""

from __future__ import annotations

import contextlib
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Literal

from tempergraph.contracts import Event, EventSink

CALLER_VARS = ("TEMPERGRAPH_SUPERVISOR_TOKEN", "TEMPERGRAPH_CALLER", "TEMPERGRAPH_CALLER_APP")
SESSION_KEY_VAR = "TEMPERGRAPH_SESSION_KEY"
IDLE_FLOOR_TOOL_S = 900
GRACE_S = 10.0
PROMPT_GAP_WARN_S = 1.0
PROMPT_WINDOW_S = 30.0  # the prompt must be taken within this window, or the session is stopped
HOST_SPEED_FLOOR_S = 3.0
HOST_WALK_LIMIT = 2000
RELEASE_AFTER_EXIT_S = 2.0

KillReason = Literal["timeout", "idle", "signal", "stop"]
Clock = Callable[[], float]


@dataclass(frozen=True, kw_only=True)
class LaunchSpec:
    argv: list[str]
    stdin_payload: bytes
    workdir: Path
    timeout_s: int
    session_key: str
    idle_s: int | None = None
    idle_floor_tool_s: int = IDLE_FLOOR_TOOL_S
    env_overlay: Mapping[str, str] = field(default_factory=dict)
    session_dir: Path | None = None
    grace_s: float = GRACE_S
    prompt_window_s: float = PROMPT_WINDOW_S


@dataclass(kw_only=True)
class RawOutcome:
    exit_code: int | None = None
    killed: bool = False  # the tree was killed after the grace period
    stop_reason: KillReason | None = None  # why a stop was sent, killed or not
    spawn_error: OSError | None = None
    broken_pipe: bool = False
    prompt_delivered: bool = False
    prompt_timeout: bool = False  # the CLI did not take the prompt within its window
    prompt_gap_s: float | None = None
    lines: int = 0
    line_times: list[float] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    unparsable: int = 0
    duration_s: float = 0.0
    warnings: list[str] = field(default_factory=list)


class StopRequest:
    """A drain or signal request the launcher polls; set from a signal handler or another thread."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.reason: KillReason = "stop"

    def request(self, reason: KillReason = "stop") -> None:
        self.reason = reason
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


def idle_action(age_s: float, tool_open: bool, idle_s: int | None, floor_s: int = IDLE_FLOOR_TOOL_S
                ) -> Literal["wait", "kill"]:
    """EXI-B4: the watchdog's decision for one tick."""
    if idle_s is None:
        return "wait"
    limit = max(idle_s, floor_s) if tool_open else idle_s
    return "kill" if age_s > limit else "wait"


def session_env(overlay: Mapping[str, str], session_key: str, base: Mapping[str, str] | None = None
                ) -> dict[str, str]:
    env = {k: v for k, v in (os.environ if base is None else base).items() if k not in CALLER_VARS}
    env.update(overlay)
    env[SESSION_KEY_VAR] = session_key
    return env


def _popen_kwargs() -> dict[str, object]:
    if os.name == "posix":
        return {"start_new_session": True}
    return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}


def _signal_group(proc: subprocess.Popen[bytes], hard: bool) -> None:
    if os.name == "posix":
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL if hard else signal.SIGTERM)
    elif hard:  # Windows: end the whole tree (EXI-B5); the job-object form is the next step there
        with contextlib.suppress(OSError):
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        with contextlib.suppress(OSError, ValueError):
            proc.send_signal(getattr(signal, "CTRL_BREAK_EVENT", signal.SIGTERM))


def _open_raw(session_dir: Path | None) -> tuple[IO[bytes] | None, IO[bytes] | int]:
    if session_dir is None:
        return None, subprocess.DEVNULL
    session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = open(session_dir / "raw.jsonl", "ab")  # noqa: SIM115 - closed in launch()'s finally
    err = open(session_dir / "stderr.log", "ab")  # noqa: SIM115
    for name in ("raw.jsonl", "stderr.log"):
        os.chmod(session_dir / name, 0o600)
    return raw, err


PS_ARGV = ("ps", "-A", "-o", "pgid=,rss=,time=")  # constant argv: no field of the session reaches it


def process_listing() -> str:
    """The read-only process listing behind a session's `resources` line (EVT §2.3); empty on failure."""
    try:
        return subprocess.run(list(PS_ARGV), capture_output=True, text=True, timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def launch(spec: LaunchSpec, parse_line: Callable[[bytes], list[Event]], sink: EventSink, *,
           stop: StopRequest | None = None, clock: Clock = time.monotonic, poll_s: float = 0.05) -> RawOutcome:
    """Run one session to its end and return what was observed. Never raises for a session failure."""
    out = RawOutcome()
    raw, err = _open_raw(spec.session_dir)
    try:
        t0 = clock()
        try:
            proc = subprocess.Popen(  # noqa: S603 - list argv from executor constants (SEC §2.1)
                spec.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, cwd=spec.workdir,
                env=session_env(spec.env_overlay, spec.session_key), **_popen_kwargs())  # type: ignore[call-overload]
        except OSError as exc:
            out.spawn_error = exc
            return out
        assert proc.stdin is not None and proc.stdout is not None
        stdin, stdout = proc.stdin, proc.stdout
        started = getattr(sink, "process_started", None)  # the group id, for `resources` lines (EVT §2.3)
        if os.name == "posix" and callable(started):
            with contextlib.suppress(Exception):
                started(proc.pid)

        def write_prompt() -> None:  # started before the reader (EXI-B2)
            try:
                stdin.write(spec.stdin_payload)
                stdin.flush()
                stdin.close()
                out.prompt_delivered = True
            except (BrokenPipeError, ConnectionResetError):
                out.broken_pipe = True
            except (OSError, ValueError):
                pass
            out.prompt_gap_s = clock() - t0

        writer = threading.Thread(target=write_prompt, name="prompt-writer", daemon=True)
        writer.start()
        lines: queue.Queue[tuple[float, bytes] | None] = queue.Queue()

        def read_stream() -> None:
            for line in iter(stdout.readline, b""):
                lines.put((clock(), line))
            lines.put(None)

        reader = threading.Thread(target=read_stream, name="stream-reader", daemon=True)
        reader.start()

        open_tools: set[str] = set()
        last = t0
        eof = False
        saw_result = False
        stop_sent_at: float | None = None
        exited_at: float | None = None

        def send_stop(reason: KillReason) -> None:
            nonlocal stop_sent_at
            if stop_sent_at is None:
                out.stop_reason = reason
                stop_sent_at = clock()
                _signal_group(proc, hard=False)

        while True:
            try:
                item = lines.get(timeout=poll_s)
            except queue.Empty:
                item = ()  # type: ignore[assignment]
            if item is None:
                eof = True
            elif item:
                ts, line = item
                last = ts
                out.lines += 1
                out.line_times.append(ts - t0)
                if raw is not None:
                    raw.write(line if line.endswith(b"\n") else line + b"\n")
                try:
                    events = parse_line(line)
                except Exception:  # noqa: BLE001 - an unparsable line never fails the session (EXI-B6)
                    out.unparsable += 1
                    events = []
                for ev in events:
                    ev = Event(kind=ev.kind, data=ev.data, ts=ts - t0)
                    if ev.kind == "tool_started":
                        open_tools.add(str(ev.data.get("call_id", "")))
                    elif ev.kind == "tool_finished":
                        open_tools.discard(str(ev.data.get("call_id", "")))
                    elif ev.kind == "result":
                        saw_result = True
                    out.events.append(ev)
                    sink.push(ev)
                continue  # drain every queued line before judging the clock
            now = clock()
            if proc.poll() is not None:
                if eof:
                    break
                exited_at = exited_at if exited_at is not None else now
                if now - exited_at > RELEASE_AFTER_EXIT_S:
                    break  # the leader ended by itself; what it left running is left alone (EXI-B5)
            if not out.prompt_delivered and not out.broken_pipe and now - t0 > spec.prompt_window_s:
                out.prompt_timeout = True
                send_stop("stop")
            if stop is not None and stop.is_set():
                send_stop(stop.reason)
            if not saw_result and now - t0 > spec.timeout_s:
                send_stop("timeout")
            if idle_action(now - last, bool(open_tools), spec.idle_s, spec.idle_floor_tool_s) == "kill":
                send_stop("idle")
            if stop_sent_at is not None and not out.killed and now - stop_sent_at >= spec.grace_s \
                    and proc.poll() is None:
                _signal_group(proc, hard=True)
                out.killed = True
            if eof and out.killed:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=spec.grace_s)
                break
        if out.killed:
            _signal_group(proc, hard=True)  # anything left in the group once the leader is gone
        elif stop_sent_at is not None and proc.poll() is None:
            _signal_group(proc, hard=True)
            out.killed = True
        out.exit_code = proc.wait()
        writer.join(timeout=1.0)
        out.duration_s = clock() - t0
        if out.prompt_gap_s is not None and out.prompt_gap_s > PROMPT_GAP_WARN_S:
            out.warnings.append(f"prompt_gap: {out.prompt_gap_s:.2f} s")
        return out
    finally:
        if raw is not None:
            raw.close()
        if not isinstance(err, int):
            err.close()


# ---------------------------------------------------------------------------------------------
# Model-free probes and host speed


@dataclass(frozen=True, kw_only=True)
class ProbeRun:
    exit_code: int | None
    stdout: str
    stderr: str
    error: str = ""


def run_probe(argv: list[str], *, timeout_s: float = 20.0, cwd: Path | None = None) -> ProbeRun:
    """Run one read-only, model-free probe command (``--version``, ``auth status``, ``--help``)."""
    try:
        done = subprocess.run(  # noqa: S603 - constant argv from an executor module
            argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout_s, cwd=cwd, check=False,
            env=session_env({}, "probe"))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ProbeRun(exit_code=None, stdout="", stderr="", error=type(exc).__name__)
    return ProbeRun(exit_code=done.returncode, stdout=done.stdout.decode("utf-8", "replace"),
                    stderr=done.stderr.decode("utf-8", "replace"))


@dataclass(frozen=True, kw_only=True)
class HostSpeed:
    spawn_s: float
    walk_s: float
    entries: int
    slow: bool


def host_speed(workdir: Path, *, floor_s: float = HOST_SPEED_FLOOR_S, clock: Clock = time.monotonic) -> HostSpeed:
    """EXI-B14: time one interpreter spawn and a bounded file walk of the workspace."""
    t0 = clock()
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run([sys.executable, "-c", ""], stdin=subprocess.DEVNULL, capture_output=True,  # noqa: S603
                       timeout=60, check=False)
    spawn = clock() - t0
    t1 = clock()
    entries = 0
    for _root, dirs, files in os.walk(workdir):
        dirs[:] = [d for d in dirs if d not in (".git", ".tempergraph")]
        entries += len(files) + len(dirs)
        if entries >= HOST_WALK_LIMIT:
            break
    walk = clock() - t1
    return HostSpeed(spawn_s=spawn, walk_s=walk, entries=entries, slow=spawn + walk > floor_s)


@dataclass(frozen=True, kw_only=True)
class ShellTiming:
    login_s: float
    plain_s: float


def shell_timing(budget_s: float) -> ShellTiming | None:
    """The audit's host-speed probe (ARC `slow-host`): `$SHELL -lc true` against `$SHELL -c true`, each under
    the budget; None when the shell cannot start."""
    shell = os.environ.get("SHELL") or "/bin/sh"

    def timed(argv: list[str]) -> float | None:
        t0 = time.monotonic()
        try:
            subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=budget_s,  # noqa: S603
                           check=False)
        except subprocess.TimeoutExpired:
            return budget_s
        except OSError:
            return None
        return time.monotonic() - t0

    plain = timed([shell, "-c", "true"])
    login = timed([shell, "-lc", "true"])
    return None if plain is None or login is None else ShellTiming(login_s=login, plain_s=plain)
