"""The check worker: a gate's check runs in a child engine process (CHK-B16, ADR-0019).

The engine sends the check context as one JSON document on standard input. The worker imports the check
by its reference, calls it, normalises the result and writes it as one JSON document on standard output;
anything the check prints goes to standard error. The child is started through the session launcher, so
the limit (`check_timeout_s` plus WORKER_GRACE_S) ends the worker and its whole process tree.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from tempergraph.contracts import CheckFinding, CheckResult, EventSink, GateSpec
from tempergraph.package import importer
from tempergraph.run import checks as checkmod

WORKER_GRACE_S = 30
_PRINT_LIMIT = 4_000


def context_doc(gate: GateSpec, ctx: checkmod.CheckContext) -> dict[str, Any]:
    assert gate.check is not None
    g = ctx.git
    return {
        "check": {"module": gate.check.module, "qualname": gate.check.qualname},
        "check_timeout_s": gate.check_timeout_s,
        "sys_path": [p for p in sys.path if p],
        "packages": importer.mapping(),  # private package names (PKG-B15, PKG-B16, PKG-B17 step 3)
        "context": {
            "unit": ctx.unit, "workdir": str(ctx.workdir), "request": ctx.request, "item": ctx.item,
            "visit": ctx.visit, "attempt": ctx.attempt, "preview": ctx.preview,
            "main_checkout": str(ctx.main_checkout) if ctx.main_checkout else None,
            "artifacts": ctx.artifacts, "values": ctx.values, "facts": ctx.facts, "settings": ctx.settings,
            "criteria": list(ctx.criteria), "allow": list(ctx.allow),
            "session": None if ctx.session is None else [dict(c) for c in ctx.session],  # CHK-B24, CHK-B25
            "out_dir": str(ctx.out_dir) if ctx.out_dir else None,
            "reuse_store": str(ctx.reuse_store) if ctx.reuse_store else None,
            "base_dir": str(ctx.base_dir) if ctx.base_dir else None,
            "no_reuse_exit_codes": {k: list(v) for k, v in ctx.no_reuse_exit_codes.items()},
            "changed_paths": list(ctx.changed_paths),
            "git": None if g is None else {
                "branch": g.branch, "base": g.base, "head": g.head, "base_head": g.base_head, "clean": g.clean,
                "pushed": g.pushed, "changed_paths": list(g.changed_paths),
                "commits_since_base": list(g.commits_since_base)},
        },
    }


def _context_from(doc: dict[str, Any]) -> checkmod.CheckContext:
    c = doc["context"]
    g = c.get("git")
    held = c.get("session")
    return checkmod.CheckContext(
        session=tuple(dict(x) for x in held if isinstance(x, dict)) if isinstance(held, list) else None,
        changed_paths=tuple(c.get("changed_paths") or ()),
        unit=c["unit"], workdir=Path(c["workdir"]), request=c.get("request") or {}, item=c.get("item"),
        visit=int(c.get("visit", 1)), attempt=int(c.get("attempt", 1)), preview=bool(c.get("preview")),
        main_checkout=Path(c["main_checkout"]) if c.get("main_checkout") else None,
        artifacts=c.get("artifacts") or {}, values=c.get("values") or {}, facts=c.get("facts") or {},
        settings=c.get("settings") or {}, criteria=tuple(c.get("criteria") or ()), allow=tuple(c.get("allow") or ()),
        out_dir=Path(c["out_dir"]) if c.get("out_dir") else None,
        reuse_store=Path(c["reuse_store"]) if c.get("reuse_store") else None,
        base_dir=Path(c["base_dir"]) if c.get("base_dir") else None,
        no_reuse_exit_codes={k: tuple(v) for k, v in (c.get("no_reuse_exit_codes") or {}).items()},
        git=None if g is None else checkmod.GitFacts(
            branch=g.get("branch", ""), base=g.get("base", ""), head=g.get("head", ""),
            base_head=g.get("base_head", ""), clean=bool(g.get("clean", True)), pushed=bool(g.get("pushed")),
            changed_paths=tuple(g.get("changed_paths") or ()),
            commits_since_base=tuple(g.get("commits_since_base") or ())))


def result_from(doc: dict[str, Any]) -> CheckResult:
    return CheckResult(
        result=doc.get("result", "FAIL"), evidence=str(doc.get("evidence") or ""),
        environmental=bool(doc.get("environmental")), untracked_only=bool(doc.get("untracked_only")),
        findings=[CheckFinding(status=f.get("status", "maybe"), criterion=f.get("criterion"),
                               place=f.get("place", ""), fix=f.get("fix", ""), message=f.get("message", ""),
                               kind=f.get("kind") if f.get("kind") in ("substance", "output_contract") else None)
                  for f in doc.get("findings") or []],
        facts=dict(doc.get("facts") or {}), runs=list(doc.get("runs") or []))


def main() -> int:
    """The worker's entry: one document in, one document out."""
    out = sys.stdout
    sys.stdout = sys.stderr  # a check's own prints never mix with the result
    try:
        doc = json.loads(sys.stdin.read())
        for p in reversed(doc.get("sys_path") or []):
            if p not in sys.path:
                sys.path.insert(0, p)
        importer.install(doc.get("packages"))
        from tempergraph.contracts import CallableRef, Criterion

        ref = CallableRef(module=doc["check"]["module"], qualname=doc["check"]["qualname"])
        gate = GateSpec(criteria=(Criterion(text="-"),), check=ref, check_timeout_s=int(doc["check_timeout_s"]))
        res, notes = checkmod.run_check(gate, _context_from(doc))
        payload = {"result": checkmod.to_json(res), "notes": notes}
    except Exception as exc:  # noqa: BLE001 - the worker itself failed; the engine reads it as environmental
        payload = {"worker_error": type(exc).__name__}
    out.write(json.dumps(payload, default=str))
    out.flush()
    return 0


def run_in_worker(gate: GateSpec, ctx: checkmod.CheckContext, *, python: str | None = None
                  ) -> tuple[CheckResult, list[str]]:
    """Run the gate's check in a check worker; a worker past its limit is an environmental FAIL."""
    if gate.check is None:
        return CheckResult(result="PASS", evidence=""), []
    return run_doc(context_doc(gate, ctx), ctx.workdir, gate.check_timeout_s, f"check-{ctx.unit}-{ctx.attempt}",
                   python=python)


def run_doc(doc: dict[str, Any], workdir: Path, timeout_s: int, key: str, *, python: str | None = None
            ) -> tuple[CheckResult, list[str]]:
    """One worker run of a context document; the check preview sends a stored one (CHK-B17)."""
    base_dir = tempfile.mkdtemp(prefix="tempergraph-base-")  # CHK-B21: outside the workspace, removed below
    try:
        return _run_doc(doc, base_dir, workdir, timeout_s, key, python)
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)  # a worker ended at its limit leaves no checkout


def _run_doc(doc: dict[str, Any], base_dir: str, workdir: Path, timeout_s: int, key: str, python: str | None
             ) -> tuple[CheckResult, list[str]]:
    from tempergraph.executors.launcher import LaunchSpec, launch

    doc = {**doc, "context": {**doc["context"], "base_dir": base_dir}}
    payload = json.dumps(doc, default=str).encode()
    spec = LaunchSpec(argv=[python or sys.executable, "-m", "tempergraph.run.check_worker"], stdin_payload=payload,
                      workdir=workdir, timeout_s=timeout_s + WORKER_GRACE_S,
                      session_key=key, prompt_window_s=float(timeout_s))
    got: list[bytes] = []

    def keep(line: bytes) -> list[Any]:
        got.append(line)
        return []

    raw = launch(spec, keep, EventSink())
    if raw.stop_reason is not None or raw.killed:
        return CheckResult(result="FAIL", evidence=f"check worker ended at its limit of {timeout_s} s",
                           environmental=True), ["check_worker_limit"]
    text = b"".join(got).decode("utf-8", errors="replace").strip()
    try:
        out = json.loads(text) if text else {}
    except ValueError:
        out = {}
    if raw.spawn_error is not None or "result" not in out:
        why = out.get("worker_error") or (type(raw.spawn_error).__name__ if raw.spawn_error else "no result")
        return CheckResult(result="FAIL", evidence=f"check worker failed: {str(why)[:_PRINT_LIMIT]}",
                           environmental=True), [f"check_worker_failed: {why}"]
    return result_from(out["result"]), list(out.get("notes") or [])


if __name__ == "__main__":
    raise SystemExit(main())
