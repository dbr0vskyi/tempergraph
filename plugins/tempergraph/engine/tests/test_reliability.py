"""Labels derived from runs, reliability grades, the labelling queue and the binding-shift watch
(FBK-AC-1 to AC-5, FBK-B1 to B5, B7)."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.improve import reliability as rel
from tempergraph.run.runner import resume
from tempergraph.store.layout import state_root_path

from .test_run import DRAFT, NO_SLEEP, REVIEW, go, judge, registry, two_step, verdict_block

NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)
PERSON = {"decided_by": "person"}
AGENT = {"decided_by": "agent"}
B1 = {"executor": "claude", "executor_version": "2.1", "alias": "medium", "model_slug": "m-1",
      "brief_digest": "b", "criteria_digest": "c"}


def ts(minutes: int) -> str:
    return (NOW + timedelta(minutes=minutes)).isoformat()


def gate_block(unit: str, verdict: str, seq: int, statuses: tuple[str, ...] = ("MET",), check: str | None = None,
               attempt: int = 1) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"kind": "attempt_start", "unit": unit, "session_kind": "step", "attempt": attempt,
                                  "seq": seq}]
    if check:
        out.append({"kind": "check", "unit": unit, "result": check, "seq": seq + 1})
    out += [{"kind": "agent_run", "unit": unit, "session_kind": "judge", "attempt": attempt, "executor": "claude",
             "cli_version": "2.1", "alias": "medium", "usage": {"by_model": {"m-1": {}}, "turns": 3}, "seq": seq + 2},
            {"kind": "judgement", "unit": unit, "seq": seq + 3, "confidence": 0.75, "confidence_source": "judge",
             "statuses": [{"n": i, "id": f"{unit}-{i}", "status": s} for i, s in enumerate(statuses, 1)],
             "brief_digest": "b", "criteria_digest": "c"},
            {"kind": "gate", "unit": unit, "verdict": verdict, "seq": seq + 4, "ts": ts(seq), "segment": 0}]
    return out


def pause(unit: str, kind: str, seq: int) -> dict[str, Any]:
    return {"kind": "pause", "unit": unit, "pause_kind": kind, "seq": seq, "ts": ts(seq)}


def human(unit: str, decision: str, seq: int, caller: dict[str, Any] = PERSON) -> dict[str, Any]:
    return {"kind": "human", "unit": unit, "decision": decision, "caller": caller, "seq": seq, "ts": ts(seq + 60)}


START = {"kind": "run_started", "workflow_version": "0.1.0", "seq": 0, "ts": ts(0)}


def kinds(labels: list[dict[str, Any]]) -> list[tuple[str, str, Any]]:
    return [(x["label_kind"], x["value"], x["unit"]) for x in labels]


@pytest.mark.parametrize(("recs", "want"), [
    # approval accepted / declined / reworked (FBK-B1)
    ([START, *gate_block("a", "PROCEED", 1), pause("a", "approval", 10), human("a", "proceed", 11)],
     [("approval", "agree", "a")]),
    ([START, *gate_block("a", "PROCEED", 1), pause("a", "approval", 10), human("a", "stop", 11)],
     [("approval", "disagree", "a")]),
    ([START, *gate_block("a", "PROCEED", 1), pause("a", "approval", 10), human("a", "retry", 11)],
     [("approval", "disagree", "a")]),
    # pushback: back to a unit an earlier PROCEED let through
    ([START, *gate_block("a", "PROCEED", 1), *gate_block("b", "ESCALATE", 10, ("UNVERIFIABLE",)),
      pause("b", "escalation", 20), human("b", "back:a", 21)], [("pushback", "disagree", "a")]),
    # override: a person's proceed on an ESCALATE whose check ran and passed
    ([START, *gate_block("a", "ESCALATE", 1, ("UNVERIFIABLE",), check="PASS"), pause("a", "escalation", 10),
      human("a", "proceed", 11)], [("override", "disagree", "a")]),
    ([START, *gate_block("a", "ESCALATE", 1, ("UNVERIFIABLE",)), pause("a", "escalation", 10),
      human("a", "proceed", 11)], []),  # no check ran: not an override
    # audit, per criterion
    ([START, *gate_block("a", "PROCEED", 1, ("MET", "MET")),
      {"kind": "audit_judge", "unit": "a", "seq": 10, "ts": ts(10),
       "statuses": [{"id": "a-1", "status": "MET"}, {"id": "a-2", "status": "UNMET"}]}],
     [("audit", "agree", "a"), ("audit", "disagree", "a")]),
])
def test_every_kind_is_derived_without_a_model(recs: list[dict[str, Any]], want: list[Any]) -> None:  # FBK-AC-1
    assert kinds(rel.derive(recs, "demo/T-1")) == want


def test_rerun_disagrees_with_the_source_runs_last_proceed() -> None:  # FBK §2.2 rerun
    old = [START, *gate_block("a", "PROCEED", 1)]
    new = [{"kind": "run_started", "seq": 0, "ts": ts(60 * 24), "rerun_of": {"thread": "demo/T-1"},
            "caller": PERSON}]
    got = rel.derive(new, "demo/T-2", earlier=lambda t: old)
    assert kinds(got) == [("rerun", "disagree", "a")] and got[0]["thread"] == "demo/T-1"
    late = [{**new[0], "ts": ts(60 * 24 * 15)}]
    assert rel.derive(late, "demo/T-2", earlier=lambda t: old) == []  # outside 14 days


def test_label_ids_are_stable_and_agent_answers_are_agent() -> None:  # FBK-B2, FBK §4
    recs = [START, *gate_block("a", "PROCEED", 1), pause("a", "approval", 10), human("a", "retry", 11, AGENT)]
    one, two = rel.derive(recs, "demo/T-1"), rel.derive(recs, "demo/T-1")
    assert [x["label_id"] for x in one] == [x["label_id"] for x in two]
    assert one[0]["source"] == "agent" and one[0]["binding"] == B1


def labels(n: int, false_pass: int, known_bad_blocks: int = 0, *, binding: dict[str, Any] = B1,
           source: str = "person", audits: tuple[int, int] = (0, 0), days_ago: int = 1) -> list[dict[str, Any]]:
    """`n` graded labels: `false_pass` disagree on PROCEED, `known_bad_blocks` agree on a block, the rest agree
    on PROCEED; plus `audits` = (agreeing, total) audit labels."""
    at = (NOW - timedelta(days=days_ago)).isoformat()
    out = []
    for i in range(n):
        if i < false_pass:
            verdict, value = "PROCEED", "disagree"
        elif i < false_pass + known_bad_blocks:
            verdict, value = "RETRY", "agree"
        else:
            verdict, value = "PROCEED", "agree"
        out.append({"unit": "g", "thread": f"demo/T-{i}", "gate_record": 5, "label_kind": "explicit",
                    "value": value, "gate_verdict": verdict, "source": source, "at": at, "binding": binding,
                    "confidence": 0.75, "confidence_source": "judge"})
    agree, total = audits
    for i in range(total):
        out.append({"unit": "g", "thread": f"demo/A-{i}", "gate_record": 5, "label_kind": "audit",
                    "criterion_id": "c", "value": "agree" if i < agree else "disagree", "gate_verdict": "PROCEED",
                    "source": "fact", "at": at, "binding": binding})
    return out


@pytest.mark.parametrize(("rows", "live", "want"), [
    (labels(12, 0), True, "unmeasured"),
    (labels(40, 3, 4, audits=(51, 60)), True, "reliable"),  # 0.10 of 30 PROCEED... see below
    (labels(40, 0, audits=(57, 60)), True, "unmeasured"),
    (labels(40, 8, audits=(54, 60)), True, "unreliable"),
    (labels(40, 2, audits=(31, 45)), True, "unreliable"),
])
def test_grades_reproduce_the_table(rows: list[dict[str, Any]], live: bool, want: str) -> None:  # FBK-AC-2
    fig = rel.figures(rows, "g", B1, NOW)
    assert rel.grade(fig, live, NOW)[0] == want


def test_table_figures() -> None:  # FBK-B3 row 2: 7 known-bad, false-pass rate 0.10, audit 0.85 over 60
    fig = rel.figures(labels(40, 3, 4, audits=(51, 60)), "g", B1, NOW)
    assert fig.known_bad == 7 and fig.false_pass_rate == pytest.approx(3 / 36, abs=0.02)
    assert fig.audit_agreement == pytest.approx(0.85) and fig.audited == 60
    assert fig.confidence_bands["0.75"] == pytest.approx(fig.false_pass_rate)
    assert rel.grade(fig, False, NOW)[0] == "unmeasured"  # no passing live score
    stale = rel.figures(labels(40, 3, 4, days_ago=45), "g", B1, NOW)
    assert rel.grade(stale, True, NOW) == ("unmeasured", ["no label in the last 30 days"])


def test_agent_labels_change_no_figure() -> None:  # FBK-AC-4
    base = labels(40, 3, 4)
    with_agents = base + labels(40, 40, source="agent")
    a, b = rel.figures(base, "g", B1, NOW), rel.figures(with_agents, "g", B1, NOW)
    assert a.to_json() == b.to_json()


def test_a_binding_change_starts_unmeasured() -> None:  # FBK-AC-5, FBK-B4
    b2 = {**B1, "model_slug": "m-2"}
    rows = labels(40, 3, 4)
    assert rel.grade(rel.figures(rows, "g", B1, NOW), True, NOW)[0] == "reliable"
    fig = rel.figures(rows, "g", b2, NOW)
    assert fig.n == 0 and rel.grade(fig, True, NOW)[0] == "unmeasured"


def test_orphan_labels_are_counted_apart() -> None:  # FBK §4
    rows = [{**labels(1, 0)[0], "gate_record": None}]
    fig = rel.figures(rows, "g", B1, NOW)
    assert fig.orphan_labels == 1 and fig.n == 0


def test_labels_are_metadata_only_after_a_run(repo: Path) -> None:  # FBK-AC-3, FBK-B1 end to end
    spec = two_step()
    units = dict(spec.units)
    units["review"] = dataclasses.replace(units["review"], gate=dataclasses.replace(units["review"].gate,
                                                                                  approval=True))
    spec = dataclasses.replace(spec, units=units)
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    assert go(repo, ex, spec).exit_code is ExitCode.PAUSED
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge()]
    resume(spec, "T-1", repo, registry(ex), decision="retry", settings=NO_SLEEP)
    root = state_root_path(repo)
    rows = rel.read_labels(root, "demo")
    assert [(r["label_kind"], r["value"], r["unit"]) for r in rows] == [("approval", "disagree", "review")]
    assert rows[0]["binding"]["brief_digest"] and rows[0]["binding"]["criteria_digest"]
    text = json.dumps(rows)
    assert "Release 1.2 notes" not in text and "notes.md" not in text  # no request or output text
    rel.record_labels(root, "demo", "T-1")
    assert len(rel.read_labels(root, "demo")) == 1  # a second derivation writes nothing new


def test_queue_orders_the_most_informative_first(repo: Path) -> None:  # FBK §2.4
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge(verdict_block("MET"))])
    assert go(repo, ex).exit_code is ExitCode.FINISHED
    rows = rel.queue(state_root_path(repo), "demo", {"draft": "unmeasured", "review": "reliable"})
    assert rows[0]["gate"] == "draft" and rows[0]["why"] == "unmeasured_binding"
    assert rows[0]["command"] == "tempergraph label demo/T-1 draft --value agree|disagree"


def test_binding_shift_is_visible(tmp_path: Path) -> None:  # FBK-B7
    root = tmp_path / ".tempergraph"
    old = {**B1, "executor": "antigravity"}
    new = {**old, "executor_version": "2.2"}

    def write(task: str, verdict: str, b: dict[str, Any], minute: int) -> None:
        d = root / "runs" / "demo" / task
        d.mkdir(parents=True)
        recs = [{"kind": "attempt_start", "unit": "g", "session_kind": "step", "attempt": 1, "seq": 1},
                {"kind": "agent_run", "unit": "g", "session_kind": "judge", "attempt": 1, "executor": b["executor"],
                 "cli_version": b["executor_version"], "alias": b["alias"], "usage": {"by_model": {"m-1": {}}},
                 "seq": 2},
                {"kind": "judgement", "unit": "g", "seq": 3, "statuses": [], "brief_digest": "b",
                 "criteria_digest": "c"},
                {"kind": "gate", "unit": "g", "verdict": verdict, "seq": 4, "ts": ts(minute)}]
        (d / "run.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")

    for i in range(30):
        write(f"O-{i:02d}", "PROCEED" if i < 21 else "RETRY", old, i)
    for i in range(10):
        write(f"N-{i:02d}", "PROCEED" if i < 4 else "RETRY", new, 100 + i)
    got = rel.shifts(root, "demo")
    assert len(got) == 1 and got[0]["side"] == "executor:antigravity" and got[0]["changed"] == ["executor_version"]
    assert got[0]["pass_rate"] == [0.7, 0.4]
    keys = {"workflow": "demo", "workflow_version": "0.1.0", "machine": "m", "repo": None}
    written = rel.record_shifts(root, "demo", keys)
    assert written and written[0]["cause"] == "binding_shift" and written[0]["executor_version"] == ["2.1", "2.2"]
    assert rel.record_shifts(root, "demo", keys) == []  # once per gate and binding
