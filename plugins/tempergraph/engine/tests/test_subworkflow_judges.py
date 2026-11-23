"""A sub-workflow child's judges keep the child's own bindings and calibration cases, not the parent's
(SWF-B9, SWF-AC1; task AC 1; JCL-B14, JCL-B17)."""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

from tempergraph.api import Gate, Judge, Routing, Step, Subworkflow, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult, WorkflowSpec
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import ScriptedExecutor, answer, standin
from tempergraph.improve import calibration as cal
from tempergraph.model import subworkflow
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.subworkflows import home_dir, register_workflow
from .fixtures.workflows import crit, named
from .test_run import DRAFT, judge, verdict_block
from .test_subworkflow_run import WORK

OK = answer("Done.", session_id="s")
UNMET = verdict_block("UNMET")
RUNGS = ("medium", "high", "xhigh")
CASES = [(f"bad-{i}", True) for i in range(20)] + [(f"good-{i}", False) for i in range(20)]


def oracle(req: SessionRequest) -> SessionResult:
    """A judge stand-in that grades a calibration case by the marker its request carries."""
    p = req.prompt
    order = re.findall(r"^(\d+)\. \[([^\]]+)\]", p.split("## Criteria", 1)[1], re.M)
    bad = "### request\nBAD" in p
    rows = []
    for n, cid in order:
        status = "UNVERIFIABLE" if "You cannot read" in p else "UNMET" if bad else "MET"
        rows.append({"n": int(n), "id": cid, "status": status,
                     "evidence": "notes.md:1" if status == "MET" else "missing"})
    block = {"criteria": rows, "gap": False, "confidence": 0.75}
    return answer("Graded.\n```json\n" + json.dumps(block) + "\n```", tools=("Read",), cost=0.01)


def accept(name: str) -> WorkflowSpec:
    """Score the registered workflow `name`'s `work` gate on its own calibration cases and return its spec."""
    child = subworkflow.read_child(name)
    assert isinstance(child, subworkflow.Child)
    cal.score(child.spec, "work", standin("claude", judges=[oracle] * 400))
    assert cal.state(child.spec, "work").state == "accepted"
    return child.spec


def parent(workflow: str = "child", judge_alias: str | None = None) -> WorkflowSpec:
    """A parent `deliver` with its own gate `work` on a step with an effort ladder, then the sub-workflow unit `setup`."""
    units = {"work": Step(prompt="Do {request}", tools=["read", "write"], produces={}, model="medium",
                          effort_ladder=RUNGS, gate=Gate(judge=Judge(stance="Verify.", model=judge_alias),
                                                         criteria=[crit("c-parent")])),
             "setup": Subworkflow(workflow=workflow, inputs={"request": "request"}, produces=("overview",))}
    return named(Workflow(order=["work", "setup"], units=units, routing=Routing(description="A fixture parent"),
                          issue_repository="acme/parent"), "deliver")


def run(repo: Path, ex: ScriptedExecutor, spec: WorkflowSpec) -> Any:
    r = Registry()
    r.register(ex)
    return start(spec, "T-1", {"request": "Release notes"}, repo, r, RunSettings(sleep=lambda s: None))


def records(repo: Path) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "deliver", "T-1") / "run.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()]


def test_a_child_gate_and_a_parent_gate_of_one_name_each_judge_on_their_own_cases(
        tmp_path: Path, repo: Path) -> None:  # SWF-AC1, AC 1
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], ladder=True, cases=CASES,
                      judge_alias="medium")
    child_spec = accept("child")
    # each `work` gate fails once, so its gate decides the ladder and the decision carries the judgement's `judge_state`;
    # the parent's judge reports another executor version, which the child's judge state must not read as its own
    newer = dataclasses.replace  # (a reply that names the version of the CLI that made it)
    ex = standin("claude", steps=[OK, OK, WORK, WORK],
                 judges=[newer(judge(UNMET), cli_version="9.9"), newer(judge(), cli_version="9.9"),
                         judge(UNMET), judge(), judge()])
    out = run(repo, ex, parent())
    assert out.exit_code is ExitCode.FINISHED, (out.message, out.payload)
    decided = [r for r in records(repo) if r["kind"] == "ladder_decision" and r["unit"] == "work"]
    mine = [r for r in decided if not r.get("child")]
    theirs = [r for r in decided if r.get("child") == "setup"]
    assert [r["judge_state"] for r in mine] == ["unscored"]  # the parent's `work` has no cases of its own
    assert [r["judge_state"] for r in theirs] == ["accepted"]  # the child's `work` keeps the child's
    assert [r["held_by"] for r in mine] == ["judge_not_trusted"] and [r["held_by"] for r in theirs] == [None]
    # the state read for the parent's gate does not turn accepted from the child's cases, and the reverse
    assert cal.state(parent(), "work").state == "unscored"
    assert cal.state(child_spec, "work").state == "accepted"


def test_a_child_judge_runs_on_the_alias_it_declares(tmp_path: Path, repo: Path) -> None:  # SWF-AC1, AC 1
    register_workflow(home_dir(), tmp_path / "pkgs", "child", produces=["overview"], judge_alias="strong")
    ex = standin("claude", steps=[DRAFT, WORK], judges=[judge(), judge(), judge(), judge()])
    out = run(repo, ex, parent(judge_alias="medium"))
    assert out.exit_code is ExitCode.FINISHED, (out.message, out.payload)
    aliases = {c.request.session_key: c.request.alias for c in ex.calls if c.request.kind == "judge"}
    assert aliases["work.1.judge"] == "medium"
    assert aliases["setup/work.1.judge"] == "strong"
    opened = {r["session_key"]: r["alias"] for r in records(repo) if r["kind"] == "session_opened"
              and str(r.get("session_key", "")).endswith("work.1.judge")}
    assert opened == {"work.1.judge": "medium", "setup/work.1.judge": "strong"}
