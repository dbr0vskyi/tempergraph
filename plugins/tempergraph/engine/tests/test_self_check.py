"""The check preview a step runs from inside its attempt (CHK §2.5, CHK-B7, CHK-AC-6)."""

from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path
from typing import Any

from tempergraph.api import CheckFinding, CheckResult, Gate, Judge, Routing, Step, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.claude import allow_rules
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import errors, validate
from tempergraph.run import selfcheck
from tempergraph.run.runner import RunSettings, start
from tempergraph.store.layout import run_dir, state_root_path

from .conftest import hash_tree
from .fixtures.workflows import crit, named
from .test_run import MET, registry

NO_SLEEP = RunSettings(sleep=lambda s: None)
CAPS = {"claude": standin("claude").capabilities()}


def plan_check(ctx: Any) -> CheckResult:
    """Passes once plan.md says `done`; says whether it ran as a preview."""
    text = (ctx.workdir / "plan.md").read_text() if (ctx.workdir / "plan.md").exists() else ""
    ok = "done" in text
    return CheckResult(result="PASS" if ok else "FAIL", evidence=f"preview={ctx.preview}",
                       findings=[CheckFinding(status="pass" if ok else "fail", criterion="c1", place="plan.md",
                                              message="the plan is complete" if ok else "the plan is not done",
                                              fix="" if ok else "finish the plan")])


def wf(self_check: bool = True, check: Any = plan_check) -> Any:
    units = {"expand": Step(prompt="Expand the plan for {request}", tools=["read", "write"], self_check=self_check,
                            gate=Gate(check=check, judge=Judge(stance="V."), criteria=[crit("c1")]))}
    return named(Workflow(order=["expand"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Expand a plan")))


class Previewing:
    """A stand-in step session that calls the preview the way a model would run the granted command."""

    def __init__(self, repo: Path, calls: int, foreign: str | None = None) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.repo, self.calls, self.foreign = repo, calls, foreign
        self.seen: list[tuple[int, str]] = []
        self.request: SessionRequest | None = None
        self.state_during: dict[str, str] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        self.request = req
        (ticket,) = set(re.findall(r"tempergraph self-check ([0-9a-f]{32})", req.prompt))
        root = state_root_path(self.repo)
        before = {k: v for k, v in hash_tree(root).items() if "tickets/" not in k and "checks/" not in k
                  and "command_runs" not in k}
        for i in range(self.calls):
            out = io.StringIO()
            code = selfcheck.run(root, self.foreign or ticket, out)
            self.seen.append((code, out.getvalue()))
            if i == 0:
                (Path(req.workdir) / "plan.md").write_text("done\n")
        after = {k: v for k, v in hash_tree(root).items() if "tickets/" not in k and "checks/" not in k
                 and "command_runs" not in k}
        self.state_during = {"same": str(before == after)}
        return answer("Expanded.", session_id="s")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        return answer(MET, tools=("Read",), session_id="j")


def recs(repo: Path, kind: str) -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", "S-1") / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def go(repo: Path, ex: Any, spec: Any = None) -> Any:
    (repo / ".gitignore").write_text("plan.md\n")
    return start(spec or wf(), "S-1", {"request": "x"}, repo, registry(ex), NO_SLEEP)


def test_two_previews_then_the_gates_own_check(repo: Path) -> None:  # CHK-B7
    ex = Previewing(repo, calls=2)
    out = go(repo, ex)
    assert out.exit_code is ExitCode.FINISHED, out.message
    (first, second) = ex.seen
    assert first[0] == 0 and "self-check 1 of 3: FAIL" in first[1] and "finish the plan" in first[1]
    assert "preview=True" in first[1] and second[0] == 0 and "self-check 2 of 3: PASS" in second[1]
    previews = recs(repo, "self_check")
    assert [(p["unit"], p["attempt"], p["result"]) for p in previews] == [("expand", 1, "FAIL"), ("expand", 1, "PASS")]
    assert previews[0]["findings"] == {"pass": 0, "fail": 1, "maybe": 0}
    (check,) = recs(repo, "check")  # the gate's check ran after the session, as itself
    assert check["result"] == "PASS" and "preview=False" in check["evidence"]


def test_a_preview_writes_no_state_and_spends_no_budget(repo: Path) -> None:  # CHK-AC-6
    ex = Previewing(repo, calls=2)
    go(repo, ex)
    assert ex.state_during == {"same": "True"}
    assert recs(repo, "budget") == [] and len(recs(repo, "gate")) == 1
    assert not list((state_root_path(repo) / "tickets").glob("*.json"))  # the ticket ended with the attempt


def test_the_limit_and_a_foreign_ticket_are_refused(repo: Path) -> None:
    ex = Previewing(repo, calls=4)
    go(repo, ex)
    assert [c for c, _ in ex.seen] == [0, 0, 0, 2] and "limit of 3" in ex.seen[3][1]
    assert len(recs(repo, "self_check")) == 3
    out = io.StringIO()
    assert selfcheck.run(state_root_path(repo), "0" * 32, out) == 2 and "unknown or expired" in out.getvalue()
    assert selfcheck.run(state_root_path(repo), "../../etc/passwd", io.StringIO()) == 2


def test_the_prompt_and_the_grant(repo: Path) -> None:
    ex = Previewing(repo, calls=0)
    go(repo, ex)
    req = ex.request
    assert req is not None and "## Check your work before you end" in req.prompt
    (cmd,) = [c for c in req.commands if c.startswith("tempergraph self-check ")]
    assert f"- `{cmd}`" in req.prompt
    assert f"Bash({cmd})" in allow_rules(("read",), req.commands, False)  # granted with no `shell` declared
    plain = Previewing(repo, calls=0)
    with contextlib.suppress(ValueError):  # the stand-in looks for a ticket this prompt does not hold
        start(wf(self_check=False), "S-2", {"request": "x"}, repo, registry(plain), NO_SLEEP)
    assert plain.request is not None and "self-check" not in plain.request.prompt


def test_self_check_needs_a_gate_check() -> None:  # CHK §4
    assert not errors(validate(wf(), CAPS))
    assert "self-check-without-check" in {f.code for f in errors(validate(wf(check=None), CAPS))}
