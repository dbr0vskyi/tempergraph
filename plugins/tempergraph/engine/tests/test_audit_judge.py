"""The sampled audit judge and its settings (JDG-B7, JDG-AC7; RST-B20, RST-B32, ROP-B2, ROP-AC1)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from tempergraph.contracts import SessionResult, Usage
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import ScriptedExecutor, answer, standin
from tempergraph.improve import reliability as rel
from tempergraph.run import audit
from tempergraph.run.runner import start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import two_step
from .test_cli import cli, happy
from .test_run import DRAFT, MET, NO_SLEEP, REVIEW, judge, verdict_block

BACK = verdict_block("UNMET", defect_in="notes")
UNMET = verdict_block("UNMET")


def log(repo: Path, task: str) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def start_run(repo: Path, task: str, main: ScriptedExecutor, others: tuple[ScriptedExecutor, ...] = (),
              **flags: Any) -> Any:
    reg = Registry()
    for ex in (main, *others):
        reg.register(ex)
    seed = flags.pop("audit_seed", None)
    return start(two_step(), task, {"request": "Release 1.2 notes"}, repo, reg,
                 dataclasses.replace(NO_SLEEP, flags=flags, audit_seed=seed))


def effects(recs: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """What a run decided and spent: verdicts, routes, budgets and the cost counters at each gate and at the end."""
    out: list[tuple[Any, ...]] = []
    for r in recs:
        if r["kind"] in ("gate", "budget", "pause", "run_exit"):
            out.append((r["kind"], r.get("unit"), r.get("verdict"), r.get("token"), r.get("route_target"),
                        json.dumps(r.get("cost_so_far"), sort_keys=True), r.get("exit_code")))
        if r["kind"] == "judgement":
            out.append(("judgement", r["unit"], r["attempt"], json.dumps(r["statuses"], sort_keys=True),
                        json.dumps(r["blockers"])))
    return out


def baseline_run(repo: Path) -> Any:
    main = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW], judges=[judge(), judge(BACK), judge(), judge()])
    return start_run(repo, "T-0", main)


def test_rop_ac1_the_audit_options_equal_their_set_spellings(repo: Path) -> None:
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "D-1", "--audit-rate", "0.5",
                       "--audit-executor", "stand")
    assert code == 0, err
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "D-2", "--set", "run.audit_rate=0.5",
                       "--set", "run.audit_executor=stand")
    assert code == 0, err
    got = []
    for task in ("D-1", "D-2"):
        recs = log(repo, task)
        started = next(r for r in recs if r["kind"] == "run_started")
        rows = next(r for r in recs if r["kind"] == "settings_resolved")["rows"]
        got.append(([k for k in started["overridden_keys"] if "audit" in k],
                    {r["key"]: (r["value"], r["layer"]) for r in rows if "audit" in r["key"]}))
    assert got[0] == got[1]
    assert got[0][1] == {"run.audit_rate": (0.5, "flag"), "run.audit_executor": ("stand", "flag")}
    assert sorted(got[0][0]) == ["run.audit_executor", "run.audit_rate"]


def test_jdg_ac7_a_rate_of_one_audits_every_judged_gate_and_changes_nothing(repo: Path) -> None:
    plain = baseline_run(repo)
    main = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW], judges=[judge(), judge(BACK), judge(), judge()])
    other = standin("antigravity", judges=[answer(UNMET), answer(UNMET), answer(MET), answer(MET)])
    out = start_run(repo, "T-1", main, (other,), **{"run.audit_rate": 1.0, "run.audit_executor": "antigravity"})
    assert out.exit_code == plain.exit_code
    base, audited = log(repo, "T-0"), log(repo, "T-1")
    assert [r for r in base if r["kind"] == "audit_judge"] == []
    records = [r for r in audited if r["kind"] == "audit_judge"]
    assert len(records) == 4 and all(r["executor"] == "antigravity" for r in records)  # one per judged gate
    assert [[s["status"] for s in r["statuses"]] for r in records] == [["UNMET"], ["UNMET"], ["MET"], ["MET"]]
    assert [s["id"] for s in records[0]["statuses"]] == ["c-file"] and records[1]["statuses"][0]["id"] == "c-review"
    assert all(r["alias"] and r["usage"] for r in records)
    assert effects(audited) == effects(base)  # verdicts, routes, attempts, budgets and counters: as without audit
    judge_keys = {r["session_key"] for r in audited if r["kind"] == "agent_run" and r["kind"] and
                  r.get("session_key", "").endswith(".judge")}
    assert judge_keys and not judge_keys & {r["session_key"] for r in records}  # its own session key
    assert [c.kind for c in other.calls] == ["judge"] * 4  # a judge session on the audit executor
    runs = [r for r in audited if r["kind"] == "agent_run" and r["session_key"] in {x["session_key"] for x in records}]
    assert len(runs) == 4 and all(r["executor"] == "antigravity" for r in runs)  # its cost is logged like any judge's


def test_jdg_ac7_the_audit_follows_its_gate_and_feeds_the_reliability_labels(repo: Path) -> None:
    main = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW], judges=[judge(), judge(BACK), judge(), judge()])
    other = standin("antigravity", judges=[answer(UNMET), answer(UNMET), answer(MET), answer(MET)])
    start_run(repo, "T-1", main, (other,), **{"run.audit_rate": 1.0, "run.audit_executor": "antigravity"})
    recs = log(repo, "T-1")
    for a in (r for r in recs if r["kind"] == "audit_judge"):
        gate = max((r for r in recs if r["kind"] == "gate" and r["unit"] == a["unit"] and r["seq"] < a["seq"]),
                   key=lambda r: r["seq"])
        later = [r for r in recs if r["kind"] == "gate" and r["unit"] == a["unit"] and gate["seq"] < r["seq"] < a["seq"]]
        assert not later  # the nearest gate before the record is the gate of the audited judgement
    labels = [(x["unit"], x["value"]) for x in rel.derive(recs, "demo/T-1") if x["label_kind"] == "audit"]
    assert labels == [("draft", "disagree"), ("review", "agree"), ("draft", "agree"), ("review", "agree")]


def test_jdg_ac7_the_audit_runs_on_the_judge_executor_when_none_is_set(repo: Path) -> None:
    main = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge(), judge(), judge()])
    start_run(repo, "T-1", main, **{"run.audit_rate": 1.0})
    assert [c.kind for c in main.calls] == ["step", "judge", "judge", "step", "judge", "judge"]  # judge, then its audit
    assert [r["executor"] for r in log(repo, "T-1") if r["kind"] == "audit_judge"] == ["claude", "claude"]


def test_jdg_ac7_a_rate_of_zero_audits_nothing_whatever_the_seed(repo: Path) -> None:
    for n, seed in enumerate((None, 0, 7)):
        main = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
        out = start_run(repo, f"T-{n}", main, **{"run.audit_rate": 0.0, "audit_seed": seed})
        assert out.exit_code == 0 and [c.kind for c in main.calls] == ["step", "judge", "step", "judge"]
        assert [r for r in log(repo, f"T-{n}") if r["kind"] == "audit_judge"] == []


def test_jdg_ac7_the_draw_is_keyed_and_repeats() -> None:
    def draws(seed: int | None) -> list[bool]:
        return [audit.sampled(0.5, seed=seed, thread="demo/T-1", unit="draft", item=None, attempt=n)
                for n in range(1, 201)]

    assert draws(3) == draws(3)  # the same draw on a second call, and after a resume
    assert draws(3) != draws(4)  # the seed is part of the key
    assert 60 < sum(draws(3)) < 140  # about half at 0.5
    one = audit.sampled(0.5, seed=1, thread="demo/T-1", unit="draft", item=None, attempt=1)
    assert one == audit.sampled(0.5, seed=1, thread="demo/T-1", unit="draft", item=None, attempt=1)
    assert any(audit.sampled(0.5, seed=1, thread=t, unit="draft", item=None, attempt=1) != one
               for t in (f"demo/T-{n}" for n in range(2, 60)))  # the thread is part of the key
    assert any(audit.sampled(0.5, seed=1, thread="demo/T-1", unit="draft", item=str(i), attempt=1) != one
               for i in range(60))  # and the item
    assert all(audit.sampled(1.0, seed=s, thread="t", unit="u", item=None, attempt=1) for s in (None, 1, 2))
    assert not any(audit.sampled(0.0, seed=s, thread="t", unit="u", item=None, attempt=1) for s in (None, 1, 2))


def test_jdg_ac7_a_half_rate_audits_the_gates_its_draw_picks(repo: Path) -> None:
    main = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW],
                   judges=[judge(), judge(BACK), judge(), judge()] + [judge()] * 4)
    start_run(repo, "T-1", main, **{"run.audit_rate": 0.5, "audit_seed": 11})
    recs = log(repo, "T-1")
    thread = "demo/T-1"
    gates = [(r["unit"], int(r["attempt"])) for r in recs if r["kind"] == "judgement"]
    want = [(u, a) for u, a in gates if audit.sampled(0.5, seed=11, thread=thread, unit=u, item=None, attempt=a)]
    got = [(r["unit"], int(r["attempt"])) for r in recs if r["kind"] == "audit_judge"]
    assert got == want


def test_jdg_ac7_a_failed_audit_session_writes_no_record_and_changes_nothing(repo: Path) -> None:
    plain = baseline_run(repo)
    dead = SessionResult(ok=False, timed_out=True, usage=Usage())
    main = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW], judges=[judge(), dead, judge(BACK), dead, judge(), dead,
                                                                            judge(), dead])
    out = start_run(repo, "T-1", main, **{"run.audit_rate": 1.0})
    assert out.exit_code == plain.exit_code
    recs = log(repo, "T-1")
    assert [r for r in recs if r["kind"] == "audit_judge"] == []
    assert effects(recs) == effects(log(repo, "T-0"))


def test_jdg_ac7_an_unreadable_audit_reply_writes_no_record(repo: Path) -> None:
    main = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge("no block here"), judge(), judge("none")])
    out = start_run(repo, "T-1", main, **{"run.audit_rate": 1.0})
    assert out.exit_code == 0
    assert [r for r in log(repo, "T-1") if r["kind"] == "audit_judge"] == []


def test_jdg_ac7_an_audit_the_guard_discards_writes_no_record_and_changes_nothing(repo: Path) -> None:
    plain = baseline_run(repo)
    writes = judge(tools=("Read", "Write"))  # a call outside the judge's views: discarded (GRD-AC3)
    main = standin("claude", steps=[DRAFT, REVIEW, DRAFT, REVIEW],
                   judges=[judge(), writes, judge(BACK), writes, judge(), writes, judge(), writes])
    out = start_run(repo, "T-1", main, **{"run.audit_rate": 1.0})
    assert out.exit_code == plain.exit_code
    recs = log(repo, "T-1")
    assert [r for r in recs if r["kind"] == "audit_judge"] == []
    assert effects(recs) == effects(log(repo, "T-0"))
