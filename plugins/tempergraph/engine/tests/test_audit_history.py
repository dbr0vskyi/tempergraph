"""The audit's history layer (AUD-B3, AUD-B5, AUD-B10, AUD-B11, AUD-B12, AUD-B15; AUD-AC3): the reader turns the
workflow's local run records into per-unit facts, counts the runs read and the runs left out, and the layer skips a
rule below its minimum sample with its `n`, never as passed.

This module also holds the writer of synthetic run records the other audit history tests import: `write_run` writes
one run log and, when asked, its activity journals under a state root.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from tempergraph.audit import AuditContext, audit
from tempergraph.audit import catalog as cat
from tempergraph.audit.history import HistoryFacts, read_history
from tempergraph.contracts import WorkflowSpec
from tempergraph.executors.capabilities import DECLARED
from tempergraph.run.log import RunLog

from .test_audit import clean_step, wf

TODAY = dt.date(2026, 11, 22)
WORKFLOW = "w"


def iso(days_ago: float = 1.0) -> str:
    return (dt.datetime.combine(TODAY, dt.time(12, 0), tzinfo=dt.UTC) - dt.timedelta(days=days_ago)).isoformat()


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _session(unit: str, i: int, kind: str, a: dict[str, Any], ts: str
             ) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    """The records of one session (`attempt_start`, `agent_run`), its key and its activity journal rows."""
    key = f"{unit}.{i}.{kind}"
    start: dict[str, Any] = {"kind": "attempt_start", "ts": ts, "session_key": key, "session_kind": kind,
                             "timeout_s": a.get("timeout_s", 600), "prompt_digest": a.get("prompt_digest", "d0")}
    if a.get("prompt_cut"):
        start["prompt_cut"] = True
    if a.get("missing"):
        start["prompt_note"] = f"⟨missing:{a['missing']}⟩"
    usage = {"reported_cost_usd": a.get("cost", 1.0), "peak_context_tokens": a.get("peak_context", 50_000),
             "output_tokens": a.get("output_tokens", 1_000)}
    run = {"kind": "agent_run", "ts": ts, "session_key": key, "session_kind": kind, "unit": unit, "usage": usage,
           "ok": a.get("ok", True), "timed_out": a.get("timed_out", False), "stalled": a.get("stalled", False),
           "duration_s": a.get("duration_s", 60.0), "tool_wall_share": a.get("tool_wall_share", 0.1),
           "infra_cause": a.get("infra_cause"), "tools": [c["name"] for c in a.get("calls", [])],
           "alias": a.get("alias", "medium"), **({"end_shape": a["end_shape"]} if a.get("end_shape") else {})}
    rows: list[dict[str, Any]] = [{"ev": "session_started", "tools": a.get("tools_started", ["Read"])}]
    for n, c in enumerate(a.get("calls", []), start=1):
        rows.append({"ev": "tool_started", "call_id": str(n), "name": c["name"], "capability": c.get("capability"),
                     "input_summary": c.get("input_summary")})
        rows.append({"ev": "tool_finished", "call_id": str(n), "ok": c.get("ok", True)})
    rows += [{"ev": "denied", **d} for d in a.get("denied", [])]
    return [start, run], key, rows


def write_run(root: Path, task: str, *, workflow: str = WORKFLOW, days_ago: float = 1.0, version: str = "1",
              unit: str = "draft", attempts: list[dict[str, Any]] | None = None, journal: bool = True,
              extra: list[dict[str, Any]] | None = None, run_started: dict[str, Any] | None = None,
              findings: list[dict[str, Any]] | None = None,
              other_units: dict[str, list[dict[str, Any]]] | None = None) -> Path:
    """One synthetic run: `run_started`, a visit of `unit` (and of each of `other_units`) made of `attempts`,
    `run_exit`, plus `extra` records.

    An attempt is a dict; keys (all optional): kind (step|retry), ok, duration_s, timed_out, stalled, timeout_s,
    infra_cause, tool_wall_share, cost, peak_context, verdict (PROCEED|RETRY|ESCALATE|FALLBACK), blockers,
    no_change, check (a `check` record body), prompt_digest, prompt_cut, missing, tools_started, calls (dicts of
    name, capability, input_summary, ok), denied (dicts of name, input_summary), end_shape, and `judge`: an attempt
    dict (tools_started, calls, denied, ...) of the judge session of that attempt.
    """
    ts = iso(days_ago)
    rd = root / "runs" / workflow / task
    rec: list[dict[str, Any]] = [{"kind": "schema", "schema": 1},
                                 {"kind": "run_started", "ts": ts, "workflow_version": version,
                                  "thread_id": f"{workflow}/{task}", **(run_started or {})}]
    sessions: dict[str, list[dict[str, Any]]] = {}
    blocks = {unit: attempts if attempts is not None else [{}], **(other_units or {})}
    for name, steps in blocks.items():
        rec.append({"kind": "unit_entered", "ts": ts, "unit": name})
        for i, a in enumerate(steps, start=1):
            kind = a.get("kind", "step" if i == 1 else "retry")
            made, key, rows = _session(name, i, kind, a, ts)
            rec += made
            if journal:
                sessions[key] = rows
            if a.get("check") is not None:
                rec.append({"kind": "check", "ts": ts, "unit": name, "result": "PASS", "environmental": False,
                            "evidence": "", **a["check"]})
            if a.get("judge") is not None:
                made, key, rows = _session(name, i, "judge", a["judge"], ts)
                rec += made
                if journal:
                    sessions[key] = rows
            verdict = a.get("verdict", "PROCEED")
            rec.append({"kind": "judgement", "ts": ts, "unit": name, "attempt": i, "blockers": a.get("blockers", []),
                        "brief_digest": a.get("brief_digest", "b0"),
                        **({"no_change": a["no_change"]} if a.get("no_change") else {})})
            rec.append({"kind": "gate", "ts": ts, "unit": name, "verdict": verdict, "token": verdict})
    rec += list(extra or [])
    rec.append({"kind": "run_exit", "ts": ts, "exit_code": 0})
    _jsonl(rd / "run.jsonl", rec)
    for key, rows in sessions.items():
        _jsonl(rd / "sessions" / key / "activity.jsonl", rows)
    if findings is not None:
        (rd / "findings.json").write_text(json.dumps({"schema_version": 1, "findings": findings}), encoding="utf-8")
    return rd


def many(root: Path, n: int, **kw: Any) -> None:
    for i in range(n):
        write_run(root, f"t{i:03d}", **kw)


def read(root: Path, **kw: Any) -> HistoryFacts:
    base: dict[str, Any] = {"version": "all", "window_days": 30, "today": TODAY}
    base.update(kw)
    return read_history(root, WORKFLOW, base.pop("version"), base.pop("window_days"), base.pop("today"), **base)


def audit_history(spec: WorkflowSpec, facts: HistoryFacts | None, tmp: Path, **kw: Any) -> Any:
    ctx = AuditContext(target=tmp, caps={"claude": DECLARED["claude"]}, probe=lambda name: "2.1.329",
                       timing=lambda budget: None, which=lambda prog: f"/usr/bin/{prog}",
                       plugin_cache=tmp / "no-cache", history=facts, today=TODAY, **kw)
    return audit(spec, {"history"}, ctx)


HISTORY_RULES = [r for r in cat.RULES if r.layer == "history"]


# -- the reader -------------------------------------------------------------------------------------------------------


def test_reader_counts_runs_in_the_window(tmp_path: Path) -> None:
    """AUD-B3, AUD-B11: only runs in `--window` days are read."""
    write_run(tmp_path, "new", days_ago=2)
    write_run(tmp_path, "old", days_ago=40)
    facts = read(tmp_path, window_days=30)
    assert (facts.runs, facts.unreadable) == (1, 0)
    assert read(tmp_path, window_days=60).runs == 2
    assert read(tmp_path, window_days=1).runs == 0


def test_reader_version_current_all_and_an_id(tmp_path: Path) -> None:
    """AUD-B11: `--version` takes `current`, `all` or an id."""
    write_run(tmp_path, "a", version="1")
    write_run(tmp_path, "b", version="2")
    write_run(tmp_path, "c", version="2")
    assert read(tmp_path, version="all").runs == 3
    assert read(tmp_path, version="current", current="2").runs == 2
    assert read(tmp_path, version="1").runs == 1
    assert read(tmp_path, version="9").runs == 0


def test_reader_counts_unreadable_runs_and_goes_on(tmp_path: Path) -> None:
    """AUD-B15, AUD-B12: a truncated log is left out and counted in the header, never raised."""
    write_run(tmp_path, "ok")
    cut = tmp_path / "runs" / WORKFLOW / "cut"
    cut.mkdir(parents=True)
    (cut / "run.jsonl").write_text('{"kind": "schema", "schema": 1}\n{"kind": "run_sta', encoding="utf-8")
    (tmp_path / "runs" / WORKFLOW / "empty").mkdir()
    facts = read(tmp_path)
    assert (facts.runs, facts.unreadable) == (1, 1)


def test_older_log_without_a_journal_is_unclassified_never_zero(tmp_path: Path) -> None:
    """AUD-AC3 (AUD-B10): refusal counts of runs with no activity journal read `unclassified`, not 0."""
    write_run(tmp_path, "a", journal=False, attempts=[{"denied": [{"name": "Bash"}]}])
    facts = read(tmp_path)
    assert facts.runs == 1 and facts.unclassified == 1
    assert facts.refusal_counts() == "unclassified"
    write_run(tmp_path, "b", attempts=[{"denied": [{"name": "Bash", "input_summary": "grep x"}]}])
    assert read(tmp_path).unclassified == 1 and read(tmp_path).refusal_counts() == 1
    write_run(tmp_path, "c")
    only = read(tmp_path, window_days=30)
    assert only.refusal_counts() == 1  # a journal exists for the others: counted from them


def test_reader_writes_nothing(tmp_path: Path) -> None:
    """AUD-B6: the reader is read-only."""
    from .conftest import hash_tree

    many(tmp_path, 3)
    before = hash_tree(tmp_path)
    read(tmp_path)
    assert hash_tree(tmp_path) == before


def test_reader_reads_the_engines_own_run_log(tmp_path: Path) -> None:
    """The reader reads what `RunLog` writes (the envelope: unit and attempt come from the session key)."""
    path = tmp_path / "runs" / WORKFLOW / "real" / "run.jsonl"
    log = RunLog(path)
    log.write("run_started", workflow_version="1")
    log.write("unit_entered", unit="draft")
    log.write("agent_run", session_key="draft.1.step", kind="step", usage={"reported_cost_usd": 0.5}, ok=True,
              duration_s=3.0, timed_out=False, stalled=False, tools=[], tool_wall_share=0.0, infra_cause=None)
    log.write("gate", unit="draft", verdict="PROCEED", token="PROCEED")
    facts = read(tmp_path, today=dt.datetime.now(dt.UTC).date())
    assert facts.runs == 1 and [a.unit for a in facts.attempts] == ["draft"]
    assert facts.visits[0].first_pass is True


# -- the layer (AUD-B1, AUD-B5, AUD-AC3) --------------------------------------------------------------------------------


def test_no_runs_skips_the_layer_and_every_history_rule_with_its_min_n(tmp_path: Path) -> None:
    """AUD-AC3 (AUD-B1): no runs: the layer is skipped with `no runs in window`, each rule skipped with `min_n`."""
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    assert rep.layers_run == [] and {"layer": "history", "reason": "no runs in window"} in rep.layers_skipped
    skipped = {s["rule"]: s for s in rep.rules_skipped}
    for r in HISTORY_RULES:
        assert r.id in skipped and skipped[r.id]["min_n"] == r.min_n, r.id
        assert skipped[r.id]["reason"] in ("no runs in window", "owner not present"), r.id
    assert rep.findings == [] or all(f.layer != "history" for f in rep.findings)


def test_a_rule_below_its_min_n_is_skipped_with_n(tmp_path: Path) -> None:
    """AUD-AC3 (AUD-B5): 3 runs and a minimum of 5: skipped as `n=3 of 5`, no finding."""
    many(tmp_path, 3, attempts=[{"verdict": "RETRY", "blockers": ["c1"]}] * 5)
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    assert rep.layers_run == ["history"] and rep.runs == 3
    skipped = {s["rule"]: s for s in rep.rules_skipped}
    assert skipped["loop-driver-criterion"]["reason"] == "n=3 of 5"
    assert skipped["low-first-pass"]["reason"] == "n=3 of 5"
    assert not [f for f in rep.findings if f.rule in ("loop-driver-criterion", "low-first-pass")]


def test_the_header_counts_runs_read_and_unreadable(tmp_path: Path) -> None:
    """AUD-B12: the header carries the window, the runs read and the runs left out."""
    many(tmp_path, 2)
    cut = tmp_path / "runs" / WORKFLOW / "cut"
    cut.mkdir()
    (cut / "run.jsonl").write_text("{", encoding="utf-8")
    rep = audit_history(wf({"draft": clean_step()}), read(tmp_path), tmp_path)
    assert (rep.runs, rep.unreadable_runs) == (2, 1)
    doc = rep.to_json()
    assert doc["runs"] == 2 and doc["unreadable_runs"] == 1
    assert "2 runs read, 1 runs unreadable" in rep.to_text()


def test_a_bare_audit_runs_history_only_when_runs_exist(tmp_path: Path) -> None:
    """AUD-B1: with no `--layer`, history runs when runs exist and is skipped with its reason otherwise."""
    from .test_audit import ctx

    spec = wf({"draft": clean_step()})
    layers = {"definition", "host", "history"}
    none = audit(spec, layers, ctx(tmp_path, history=read(tmp_path)))  # type: ignore[arg-type]
    assert none.layers_run == ["definition", "host"]
    assert {"layer": "history", "reason": "no runs in window"} in none.layers_skipped
    many(tmp_path, 2)
    some = audit(spec, layers, ctx(tmp_path, history=read(tmp_path)))  # type: ignore[arg-type]
    assert some.layers_run == ["definition", "host", "history"] and some.runs == 2
