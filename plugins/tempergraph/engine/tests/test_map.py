"""The sequential map: one fresh session per item, each gated on its own (MAP-AC1 to AC-4, VAL-B4)."""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph.api import CheckResult, Gate, Judge, Map, Routing, Step, Value, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import CheckFinding, MapItem, SessionRequest, SessionResult, WorkflowSpec
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import errors, validate
from tempergraph.run.runner import RunSettings, resume, start
from tempergraph.store.layout import run_dir, state_root_path

from .fixtures.workflows import crit, named
from .test_run import judge, registry, verdict_block

NO_SLEEP = RunSettings(sleep=lambda s: None)
FAIL = verdict_block("UNMET")
THREE = [{"id": "p1", "text": "First phase"}, {"id": "p2", "text": "Second phase"},
         {"id": "p3", "text": "Third phase"}]


def planner(items: Any) -> Any:
    """A scripted plan step that writes the list into the workspace."""
    def reply(req: SessionRequest) -> SessionResult:
        (req.workdir / "phases.json").write_text(items if isinstance(items, str) else json.dumps(items))
        return answer("Planned.\nARTIFACT phases: phases.json", session_id="plan")
    return reply


def item_ok(note: str = "done") -> SessionResult:
    return answer(f"Did it.\nARTIFACT note: {note}", session_id="item")


def p2_fails_once(ctx: Any) -> CheckResult:
    if ctx.item == "p2" and ctx.attempt == 1:
        return CheckResult(result="FAIL", evidence="missing", findings=[
            CheckFinding(status="fail", criterion="c-item", message="not there")])
    return CheckResult(result="PASS", evidence="ok", facts={"item_seen": str(ctx.item)})


def no_phases(ctx: Any) -> list[MapItem]:
    return []


def raising(ctx: Any) -> list[MapItem]:
    raise KeyError("phases")


def by_item(item: MapItem) -> str:
    return "small" if item.id == "p1" else "huge" if item.id == "p3" else "medium"


def mapped(*, check: Any = None, retry_budget: int = 1, join_back: bool = True, item_gate: dict[str, Any] | None = None,
           **map_fields: Any) -> WorkflowSpec:
    item = Step(prompt="Do {item_id} ({item_index}/{item_count}): {item}", tools=["read", "write"],
                produces={"note": Value()},
                gate=Gate(check=check, judge=Judge(stance="V."), criteria=[crit("c-item")], retry_budget=retry_budget,
                          **(item_gate or {})))
    units = {
        "plan": Step(prompt="Plan {request}", tools=["read", "write"], produces={"phases": "file"},
                     gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-plan")])),
        "phase": Map(items_from=("plan", "phases"), step=item, **map_fields),
        "join": Step(prompt="Join", tools=["read"],
                     gate=Gate(judge=Judge(stance="V."), criteria=[crit("c-join")],
                               back_targets=["plan"] if join_back else [])),
    }
    return named(Workflow(order=["plan", "phase", "join"], units=units, issue_repository="acme/x",
                          routing=Routing(description="Plan, then one session per phase")))


def run(repo: Path, spec: WorkflowSpec, steps: list[Any], judges: list[Any], task: str = "M-1", **kw: Any) -> Any:
    ex = standin("claude", steps=steps, judges=judges)
    out = start(spec, task, {"request": "x"}, repo, registry(ex), dataclasses.replace(NO_SLEEP, **kw))
    return out, ex


def recs(repo: Path, kind: str, task: str = "M-1") -> list[dict[str, Any]]:
    p = run_dir(state_root_path(repo), "demo", task) / "run.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["kind"] == kind]


def keys(ex: Any, kind: str = "step") -> list[str]:
    return [c.request.session_key for c in ex.calls if c.kind == kind]


def test_one_session_per_item_each_gated_on_its_own(repo: Path) -> None:  # MAP-B1 and its table, MAP-AC3
    spec = mapped(check=p2_fails_once)
    steps = [planner(THREE), item_ok(), item_ok(), item_ok(), item_ok(), item_ok()]
    out, ex = run(repo, spec, steps, [judge(), judge(), judge(), judge(FAIL), judge(FAIL)])
    # p1 passes; p2 fails its check then passes; p3 spends its budget of one retry and asks
    assert keys(ex) == ["plan.1.step", "phase.p1.1.step", "phase.p2.1.step", "phase.p2.2.retry", "phase.p3.1.step",
                        "phase.p3.2.retry"]
    assert out.exit_code is ExitCode.PAUSED, out.message
    assert (out.payload["kind"], out.payload["unit"], out.payload["item"]) == ("budget", "phase", "p3")
    (items,) = recs(repo, "map_items")
    assert (items["count"], items["ids"]) == (3, ["p1", "p2", "p3"])
    ex2 = standin("claude", steps=[item_ok(), answer("Joined.", session_id="join")], judges=[judge(), judge()])
    done = resume(spec, "M-1", repo, registry(ex2), decision="retry", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    assert keys(ex2) == ["phase.p3.3.retry", "join.1.step"]  # only p3 reruns; the join starts after the third
    prompt = [c for c in ex.calls if c.kind == "step"][2].request.prompt  # VAL-B4: p2's own keys
    assert "Do p2 (2/3): Second phase" in prompt


def test_items_keep_their_own_artifacts_and_facts(repo: Path) -> None:  # MAP-B8, MAP-B9, MAP-B10
    spec = mapped(check=p2_fails_once)
    steps = [planner(THREE[:2]), item_ok("one"), item_ok("bad"), item_ok("two"), answer("Joined.")]
    out, _ = run(repo, spec, steps, [judge(), judge(), judge(), judge()])
    assert out.exit_code is ExitCode.FINISHED, out.message
    checks = recs(repo, "check")
    assert [(c["item"], c["result"]) for c in checks if c["unit"] == "phase"] == [("p1", "PASS"), ("p2", "FAIL"),
                                                                                 ("p2", "PASS")]
    gates = [(g["item"], g["token"]) for g in recs(repo, "gate") if g["unit"] == "phase"]
    assert gates == [("p1", "NEXT"), ("p2", "RETRY"), ("p2", "PROCEED")]


def test_an_empty_list_runs_the_whole_artifact_as_one_item(repo: Path) -> None:  # MAP-B2
    spec = mapped(extract=no_phases, on_empty="one_item")
    out, ex = run(repo, spec, [planner("# Plan\nNo phase heading here."), item_ok(), answer("Joined.")],
                  [judge(), judge(), judge()])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert keys(ex) == ["plan.1.step", "phase.all.1.step", "join.1.step"]
    assert "No phase heading here." in [c for c in ex.calls if c.kind == "step"][1].request.prompt


def test_an_empty_list_stops_or_skips(repo: Path) -> None:  # MAP-B7 on_empty
    out, ex = run(repo, mapped(extract=no_phases), [planner("x")], [judge()])
    assert out.exit_code is ExitCode.STOPPED and out.reason == "map" and keys(ex) == ["plan.1.step"]
    out, ex = run(repo, mapped(extract=no_phases, on_empty="skip"), [planner("x"), answer("Joined.")],
                  [judge(), judge()], task="M-2")
    assert out.exit_code is ExitCode.FINISHED and keys(ex) == ["plan.1.step", "join.1.step"]


def test_a_trip_back_reruns_every_item(repo: Path) -> None:  # MAP-B3
    spec = mapped()
    steps = [planner(THREE[:2]), item_ok(), item_ok(), answer("Joined."),
             planner([THREE[0], THREE[2]]), item_ok(), item_ok(), answer("Joined.")]
    judges = [judge(), judge(), judge(), judge(verdict_block("UNMET", defect_in="phases")),
              judge(), judge(), judge(), judge()]
    out, ex = run(repo, spec, steps, judges)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert keys(ex) == ["plan.1.step", "phase.p1.1.step", "phase.p2.1.step", "join.1.step",
                        "plan.2.step", "phase.p1.2.step", "phase.p3.1.step", "join.2.step"]
    assert [r["ids"] for r in recs(repo, "map_items")] == [["p1", "p2"], ["p1", "p3"]]


def test_a_drained_run_resumes_at_the_pending_item(repo: Path) -> None:  # MAP-B4, MAP-AC3
    spec = mapped()
    out, ex = run(repo, spec, [planner(THREE), item_ok(), item_ok()], [judge(), judge(), judge()],
                  flags={"run.attempt_cap": 3})
    assert out.exit_code is ExitCode.STOPPED and keys(ex)[-1] == "phase.p2.1.step"
    ex2 = standin("claude", steps=[item_ok(), answer("Joined.")], judges=[judge(), judge()])
    done = resume(spec, "M-1", repo, registry(ex2), settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    assert keys(ex2) == ["phase.p3.1.step", "join.1.step"]


def test_too_many_items_stop_before_any_item(repo: Path) -> None:  # MAP-B5
    many = [f"i{n}" for n in range(25)]
    out, ex = run(repo, mapped(max_items=20), [planner(many)], [judge()])
    assert out.exit_code is ExitCode.STOPPED and out.reason == "map"
    assert keys(ex) == ["plan.1.step"]
    (items,) = recs(repo, "map_items")
    assert (items["count"], items["error"]) == (25, "map_too_many")
    stop = [g for g in recs(repo, "gate") if g["unit"] == "phase"]
    assert stop[0]["token"] == "STOP"


@pytest.mark.parametrize(("items", "extract", "error"), [
    ("not json", None, "map_list_unreadable"),
    ([{"id": "a"}, {"id": "a"}], None, "map_duplicate_id"),
    ([{"id": "bad id!"}], None, "map_item_id"),
    ([{"text": "no id"}], None, "map_list_unreadable"),
    (["a"], raising, "map_extract_raised"),
])
def test_a_list_that_cannot_be_used_stops_the_run(repo: Path, items: Any, extract: Any, error: str) -> None:
    out, ex = run(repo, mapped(extract=extract), [planner(items)], [judge()])  # MAP-B8, MAP-B9, MAP-B10 row 1, MAP-B8, MAP-B10, MAP-B9
    assert out.exit_code is ExitCode.STOPPED and out.reason == "map"
    assert recs(repo, "map_items")[0]["error"] == error and keys(ex) == ["plan.1.step"]
    if extract is raising:
        assert "KeyError" in recs(repo, "map_items")[0]["detail"]


def test_a_person_stops_or_retries_one_item(repo: Path) -> None:  # MAP-B6 for the sequential form
    spec = mapped(retry_budget=0)
    out, _ = run(repo, spec, [planner(THREE), item_ok(), item_ok()], [judge(), judge(), judge(FAIL)])
    assert out.exit_code is ExitCode.PAUSED and out.payload["item"] == "p2"
    ex2 = standin("claude")
    done = resume(spec, "M-1", repo, registry(ex2), decision="stop", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.STOPPED and ex2.calls == []


def test_a_person_passes_one_item_and_the_next_runs(repo: Path) -> None:  # MAP-B8, MAP-B9, MAP-B10 rows 4 and 5
    spec = mapped(retry_budget=0)
    out, _ = run(repo, spec, [planner(THREE), item_ok(), item_ok()], [judge(), judge(), judge(FAIL)])
    ex2 = standin("claude", steps=[item_ok(), answer("Joined.")], judges=[judge(), judge()])
    done = resume(spec, "M-1", repo, registry(ex2), decision="proceed", settings=NO_SLEEP)
    assert done.exit_code is ExitCode.FINISHED, done.message
    assert keys(ex2) == ["phase.p3.1.step", "join.1.step"]


def test_each_item_sees_the_commits_before_it(repo: Path) -> None:  # MAP-AC4
    seen: dict[str, list[str]] = {}

    def worker(req: SessionRequest) -> SessionResult:
        iid = req.session_key.split(".")[1]
        seen[iid] = sorted(p.name for p in req.workdir.glob("done-*"))
        (req.workdir / f"done-{iid}").write_text(iid)
        subprocess.run(["git", "add", "-A"], cwd=req.workdir, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", iid],
                       cwd=req.workdir, check=True)
        return item_ok()

    out, _ = run(repo, mapped(), [planner(THREE), worker, worker, worker, answer("Joined.")],
                 [judge(), judge(), judge(), judge(), judge()])
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert seen == {"p1": [], "p2": ["done-p1"], "p3": ["done-p1", "done-p2"]}


def test_item_model_picks_among_declared_aliases(repo: Path) -> None:  # MAP-B7, MAP-B8, MAP-B10, MAP-B9
    spec = mapped(item_model=by_item, models=["small", "medium"])
    out, ex = run(repo, spec, [planner(THREE), item_ok(), item_ok()], [judge(), judge(), judge()])
    assert [c.request.alias for c in ex.calls if c.kind == "step"][1:] == ["small", "medium"]
    assert out.exit_code is ExitCode.PAUSED and out.payload["reason"] == "workflow_fault"  # p3 asked for `huge`
    assert out.payload["item"] == "p3"


@pytest.mark.parametrize(("build", "code"), [
    (lambda: mapped(item_gate={"back_targets": ["plan"]}), "map-back-target"),
    (lambda: _reordered(), "map-items-unknown"),
    (lambda: _wrong_key(), "map-items-unknown"),
    (lambda: mapped(mode="concurrent"), "not_in_release"),
    (lambda: mapped(max_items=80), "map-invalid"),
    (lambda: mapped(on_empty="guess"), "map-invalid"),
    (lambda: mapped(item_model=by_item), "map-invalid"),
    (lambda: mapped(item_model=by_item, models=["huge"]), "alias-unbound"),
])
def test_validation(build: Any, code: str) -> None:  # MAP-AC2
    found = [f.code for f in errors(validate(build(), {"claude": DECLARED["claude"]}))]
    assert code in found, found


def _wrong_key() -> WorkflowSpec:
    spec = mapped()
    m = spec.units["phase"]
    assert m.map is not None
    bad = dataclasses.replace(m, map=dataclasses.replace(m.map, items_from=("plan", "nothing")))
    return dataclasses.replace(spec, units={**spec.units, "phase": bad})


def _reordered() -> WorkflowSpec:
    spec = mapped(join_back=False)
    return dataclasses.replace(spec, order=("phase", "plan", "join"))


def test_the_fixture_is_valid() -> None:
    assert errors(validate(mapped(check=p2_fails_once), {"claude": DECLARED["claude"]})) == []


def test_map_takes_only_a_step() -> None:
    with pytest.raises(TypeError):
        Map(items_from=("plan", "phases"), step=mapped().units["phase"])
