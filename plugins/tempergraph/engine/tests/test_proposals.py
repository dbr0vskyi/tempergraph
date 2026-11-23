"""Clusters, proposals, change classes, the proposer, draft pull requests, case sets and paired trials
(PRP-AC1 to AC-6, PRP-B1 to B8, B10; the `ref:` worktree base of trial cases, WTR-B21)."""

from __future__ import annotations

import ast
import dataclasses
import difflib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.standins import answer, standin
from tempergraph.improve import proposals as prp
from tempergraph.improve import trials as trl
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.package.loader import load
from tempergraph.store.layout import state_root_path

from .conftest import SRC
from .fixtures.packages import minimal_package
from .test_run import DRAFT, REVIEW, go, judge, records

CLUSTER = {"cluster_id": "c-1", "side": "workflow", "unit": "draft", "cause": "retries_spent", "runs": 3,
           "threads": ["release-notes/T-1"], "findings": ["fp"], "issues": []}
RULE = "Write each entry from the change itself, never from its title alone."


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def pkg(repo: Path) -> Path:
    root = minimal_package(repo / "workflows")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "package")
    return root


def patch(pkg: Path, edits: dict[str, str | None]) -> str:
    """A unified diff over the package for `edits` (relative path -> new text, None deletes)."""
    out = []
    for rel, new in edits.items():
        p = pkg / rel
        old = p.read_text().splitlines(keepends=True) if p.exists() else []
        lines = [] if new is None else new.splitlines(keepends=True)
        for ln in difflib.unified_diff(old, lines, "/dev/null" if not old else f"a/{rel}",
                                       "/dev/null" if new is None else f"b/{rel}"):
            out.append(ln if ln.endswith("\n") else ln + "\n\\ No newline at end of file\n")
    return "".join(out)


def outcome_with(pkg: Path, **change: Any) -> str:
    doc = json.loads((pkg / "outcome.json").read_text())
    crit = doc["intermediate"]["draft"]["criteria"][1]
    crit.update(change)
    return json.dumps(doc, indent=4, sort_keys=True) + "\n"  # reordered and reformatted on purpose


def lessons(text: str) -> str:
    return json.dumps({"schema_version": 1, "lessons": [{"id": "L-1", "text": text, "status": "active",
                                                        "source": "person"}]}) + "\n"


PROMPT = "Write release notes for {request} into notes.md. Write each entry from its change.\n"


@pytest.mark.parametrize(("author", "edits", "state", "want"), [
    ("proposer", {"prompts/draft.md": PROMPT}, "drafted", ["prompt"]),
    ("proposer", {"prompts/draft.md": PROMPT, "lessons/draft.json": lessons("Read each change before its entry.")},
     "drafted", ["lessons", "prompt"]),
    ("proposer", {"prompts/draft.md": PROMPT, "workflow/release_notes/checks.py": "CHECK"}, "mixed_sides", None),
    ("proposer", {"outcome.json": "WEAKEN"}, "weakening", None),
    ("person", {"outcome.json": "WEAKEN"}, "drafted", ["outcome", "weakening"]),
])
def test_classes_and_refusals(repo: Path, pkg: Path, author: str, edits: dict[str, str], state: str,
                              want: list[str] | None) -> None:  # PRP-AC1, PRP-B1, PRP-B2
    root = state_root_path(repo)
    for k, v in list(edits.items()):
        if v == "WEAKEN":
            edits[k] = outcome_with(pkg, severity="warning")
        elif v == "CHECK":
            edits[k] = (pkg / k).read_text() + "\n\nEXTRA = 1\n"
    rec = prp.record(root, load(pkg), CLUSTER, patch(pkg, edits), author=author, rule=RULE)
    if want is None:
        assert rec["state"] == "refused" and rec["refusal"] == state
    else:
        assert rec["state"] == "drafted" and rec["classes"] == want, rec
    if author == "person":
        assert rec["labels"] == ["weakens-gate"]


def test_a_reformatted_file_changes_nothing(repo: Path, pkg: Path) -> None:  # PRP-AC1, PRP-B23
    doc = json.loads((pkg / "outcome.json").read_text())
    rec = prp.record(state_root_path(repo), load(pkg), CLUSTER,
                     patch(pkg, {"outcome.json": json.dumps(doc, indent=1, sort_keys=True) + "\n"}),
                     author="proposer", rule=RULE)
    assert rec["refusal"] == "no_change"


def test_a_verifier_moved_down_the_ladder_is_weakening(repo: Path, pkg: Path) -> None:  # PRP-B14, PRP-B15, OUT-B20, OUT-B21
    rec = prp.record(state_root_path(repo), load(pkg), CLUSTER,
                     patch(pkg, {"outcome.json": outcome_with(pkg, verified_by="person")}), author="proposer",
                     rule=RULE)
    assert rec["refusal"] == "weakening"


def test_literals_are_refused(repo: Path, pkg: Path) -> None:  # PRP-B3
    root = state_root_path(repo)
    spec = load(pkg)
    rec = prp.record(root, spec, CLUSTER, patch(pkg, {"prompts/draft.md": PROMPT + "See PROJ-123 first.\n"}),
                     author="proposer", rule=RULE)
    assert rec["refusal"] == "literal" and "ticket_id" in rec["literal"]
    ev = root / "runs" / "release-notes" / "T-1" / "evidence"
    ev.mkdir(parents=True)
    (ev / "record.json").write_text(json.dumps({"request": {"request": "notes for the spring garden launch"}}))
    rec = prp.record(root, spec, CLUSTER, patch(pkg, {"prompts/draft.md": PROMPT + "Cover the spring garden "
                                                                                   "launch well.\n"}),
                     author="proposer", rule=RULE)
    assert rec["refusal"] == "literal" and rec["literal"] == ["request_words"]
    assert prp.record(root, spec, CLUSTER, patch(pkg, {"prompts/draft.md": PROMPT}), author="proposer",
                      rule="Fix PROJ-9 as asked")["refusal"] == "literal"


def test_engine_side_stale_and_invalid(repo: Path, pkg: Path) -> None:  # PRP-B10, PRP-B16, PRP-B17, PRP-B20, PRP-B7, PRP-B8
    root = state_root_path(repo)
    spec = load(pkg)
    assert prp.record(root, spec, {**CLUSTER, "side": "executor:claude"}, "x", author="person",
                      rule=RULE)["refusal"] == "engine_side"
    stale = patch(pkg, {"prompts/draft.md": PROMPT}).replace("-Write release notes", "-Something else")
    assert prp.record(root, spec, CLUSTER, stale, author="person", rule=RULE)["refusal"] == "stale_base"
    broken = patch(pkg, {"workflow/release_notes/__init__.py": "def workflow(:\n"})
    assert prp.record(root, spec, CLUSTER, broken, author="person", rule=RULE)["refusal"] == "invalid"
    outside = "--- a/../x\n+++ b/../x\n@@ -0,0 +1 @@\n+x\n"
    assert prp.record(root, spec, CLUSTER, outside, author="person", rule=RULE)["refusal"] == "outside_package"
    assert (pkg / "prompts" / "draft.md").read_text().startswith("Write release notes for {request}")


def finding(thread: str, side: str, cause: str, at: str, unit: str = "draft", machine: str = "m1") -> dict[str, Any]:
    return {"kind": "finding", "thread": thread, "workflow": "demo", "unit": unit, "cause": cause, "class": "fault",
            "side": side, "fingerprint": f"{side}-{cause}", "at": at, "request_digest": thread, "machine": machine}


def test_clusters_rank_and_fold_twins(tmp_path: Path) -> None:  # PRP-B12
    root = tmp_path / ".tempergraph"
    rows = {"T-1": [finding("demo/T-1", "workflow", "retries_spent", "2026-11-19T00:00:00+00:00"),
                    finding("demo/T-1", "engine", "retries_spent", "2026-11-19T01:00:00+00:00")],
            "T-2": [finding("demo/T-2", "workflow", "judge_blocked:c-1", "2026-11-19T02:00:00+00:00", "review")]}
    for task, fs in rows.items():
        d = root / "runs" / "demo" / task
        d.mkdir(parents=True)
        (d / "findings.json").write_text(json.dumps({"findings": fs}))
        (d / "run.jsonl").write_text(json.dumps({"kind": "agent_run", "unit": "review", "attempt": 2,
                                                 "usage": {"reported_cost_usd": 1.5}}) + "\n")
    (root / "ledger.jsonl").write_text(json.dumps({"kind": "label", "workflow": "demo", "unit": "draft",
                                                   "value": "disagree", "source": "person"}) + "\n")
    got = prp.clusters(root, "demo", now=__import__("datetime").datetime(2026, 11, 20,
                                                                         tzinfo=__import__("datetime").UTC))
    assert [c["unit"] for c in got] == ["draft", "review"]  # 5.00 (one label) above 1.50 (repeat cost)
    assert got[0]["side"] == "workflow" and got[0]["twin_of"] and got[0]["score"] == 5.0
    assert got[1]["repeat_cost_usd"] == 1.5 and got[1]["cause"] == "judge_blocked:c-1"
    assert len(got) == 2  # the engine twin is folded under the side attributed first


def test_no_code_path_merges() -> None:  # PRP-AC2
    hits = []
    for p in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and (
                    node.value == "merge" or "/merge" in node.value or node.value.startswith("merge ")):
                if p.name == "git.py" and node.value == "merge":
                    continue  # the git launch site's local merge of writer branches at a join (WSP-B11), not a pull request's
                hits.append(f"{p.name}: {node.value!r}")
    assert hits == []
    assert not any(hasattr(MemoryCodeHost, n) for n in ("merge", "merge_pr", "merge_pull_request"))


def proposer_ex(edit: dict[str, str], *, verdict: str = "MET", outside: bool = False) -> Any:
    def step(req: SessionRequest) -> SessionResult:
        for rel, text in edit.items():
            (req.workdir / rel).write_text(text)
        if outside:
            (req.workdir.parent / "README.md").write_text("changed\n")
        return answer(f"Changed the template.\nRULE: {RULE}")

    block = {"criteria": [{"n": 1, "status": verdict, "evidence": "diff:1"}, {"n": 2, "status": verdict,
                                                                              "evidence": "rule"}],
             "gap": False, "confidence": 0.75}
    return standin("claude", steps=[step], judges=[answer("```json\n" + json.dumps(block) + "\n```", tools=("Read",))])


def test_the_proposer_works_on_its_own_branch(repo: Path, pkg: Path) -> None:  # PRP-B4
    root = state_root_path(repo)
    spec = load(pkg)
    rec = prp.propose(root, spec, CLUSTER, proposer_ex({"prompts/draft.md": PROMPT}))
    assert rec["state"] == "drafted" and rec["classes"] == ["prompt"] and rec["rule"] == RULE
    assert rec["branch"] == f"improve/{rec['proposal_id']}"
    assert git(repo, "log", "-1", "--format=%s", rec["branch"]).startswith("improve(release-notes)")
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert (pkg / "prompts" / "draft.md").read_text() != PROMPT  # the live package is untouched
    bad = prp.propose(root, spec, CLUSTER, proposer_ex({"prompts/draft.md": PROMPT}, outside=True))
    assert bad["refusal"] == "outside_package"
    rejected = prp.propose(root, spec, CLUSTER, proposer_ex({"prompts/draft.md": PROMPT}, verdict="UNMET"))
    assert rejected["refusal"] == "judge_not_met"


def test_open_pushes_its_branch_and_opens_a_draft(repo: Path, pkg: Path, tmp_path: Path) -> None:  # PRP-B8
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    root = state_root_path(repo)
    spec = load(pkg)
    rec = prp.propose(root, spec, CLUSTER, proposer_ex({"prompts/draft.md": PROMPT}))
    with pytest.raises(prp.ProposalError):  # a drafted proposal on its trial path is opened once decided
        prp.open_pr(root, spec, "nope", MemoryCodeHost())
    host = MemoryCodeHost()
    out = prp.open_pr(root, spec, rec["proposal_id"], host)
    assert out["state"] == "opened" and host.pulls[0]["draft"] is True
    assert host.pulls[0]["head"] == rec["branch"] and host.pulls[0]["base"] == "main"
    assert RULE in host.pulls[0]["body"] and "Not trialled" in host.pulls[0]["body"]
    assert git(remote, "branch", "--list").split() == [rec["branch"]]  # only its own branch, never main
    down = MemoryCodeHost(down=True)
    rec2 = prp.propose(root, spec, CLUSTER, proposer_ex({"prompts/draft.md": PROMPT}))
    assert prp.open_pr(root, spec, rec2["proposal_id"], down).get("open_error")  # PRP-B16, PRP-B17, PRP-B20, PRP-B7, PRP-B8: rerun later
    assert prp.load_proposal(root, rec2["proposal_id"])["state"] == "drafted"


# -- trials ---------------------------------------------------------------------------------------------------

def pairs(w: int, lo: int, t: int, in_sample: int = 0) -> list[dict[str, Any]]:
    return ([{"result": "win"}] * w + [{"result": "loss"}] * lo + [{"result": "tie"}] * t
            + [{"result": "win", "in_sample": True}] * in_sample)


HOLD = [{"name": "run_cost", "state": "held"}]


@pytest.mark.parametrize(("w", "lo", "t", "guards", "want", "reason"), [
    (9, 1, 4, HOLD, "shown_better", None),
    (7, 3, 4, HOLD, "not_shown", None),
    (9, 1, 4, [{"name": "run_cost", "state": "failed"}], "regressed", "guard:run_cost"),
    (4, 1, 9, HOLD, "not_shown", "too_few_pairs"),
])
def test_decision_table(w: int, lo: int, t: int, guards: list[dict[str, Any]], want: str,
                        reason: str | None) -> None:  # PRP-AC3, PRP-B6
    got = trl.decide(pairs(w, lo, t), guards)
    assert (got["decision"], got["reason"]) == (want, reason)
    assert trl.sign_count(10) == 9


def test_cost_guard_margin() -> None:  # PRP-B6 row 3: cost +22%
    g = {x["name"]: x["state"] for x in trl.guard_states({"cost": 10.0}, {"cost": 12.2})}
    assert g["run_cost"] == "failed"
    assert {x["name"]: x["state"] for x in trl.guard_states({"cost": 10.0}, {"cost": 11.0})}["run_cost"] == "held"


def test_in_sample_pairs_never_decide() -> None:  # PRP-AC5
    got = trl.decide(pairs(2, 1, 0, in_sample=12), HOLD)
    assert got["counts"]["in_sample"] == 12 and got["decision"] == "not_shown" and got["reason"] == "too_few_pairs"


def cases(pkg: Path, n: int, base: str = "HEAD", harvested_from: str | None = None) -> None:
    rows = [{"case_id": f"k{i}", "base": base, "request": f"case {i}", "expected_scope": "notes",
             "origin": f"harvested:{harvested_from}#0" if harvested_from and i == 0 else "authored",
             "reviewed_by": "dana"} for i in range(n)]
    (pkg / "evals" / "cases.json").write_text(json.dumps({"schema_version": 1, "cases": rows}))


def fake_runner(plan: dict[str, list[float]], cost: float = 1.0) -> Any:
    """Arm A/B values per case index; each call returns a synthetic run log."""
    calls: list[tuple[str, str]] = []

    def run(spec: Any, case: Any, arm: str, tid: str) -> list[dict[str, Any]]:
        calls.append((case.case_id, arm))
        i = int(case.case_id[1:])
        ok = plan[arm[0]][i] >= 1
        return [{"kind": "gate", "unit": "draft", "verdict": "PROCEED" if ok else "RETRY", "seq": 1},
                {"kind": "check", "unit": "draft", "result": "PASS"},
                {"kind": "run_exit", "exit_code": 0, "cost": {"reported": cost}}]
    run.calls = calls  # type: ignore[attr-defined]
    return run


def drafted(repo: Path, pkg: Path) -> tuple[Path, Any, dict[str, Any]]:
    root = state_root_path(repo)
    spec = load(pkg)
    rec = prp.record(root, spec, CLUSTER, patch(pkg, {"prompts/draft.md": PROMPT}), author="person", rule=RULE)
    assert rec["state"] == "drafted"
    return root, spec, rec


def test_a_trial_decides_on_paired_cases(repo: Path, pkg: Path) -> None:  # PRP-B6, PRP-B18, PRP-B19, PRP-B20
    cases(pkg, 14)
    root, spec, rec = drafted(repo, pkg)
    a = [0] * 14
    b = [1] * 9 + [0] + [0] * 4
    a[9] = 1  # one loss
    run = fake_runner({"A": a, "B": b})
    out = trl.trial(root, spec, rec["proposal_id"], run)
    assert out["decision"] == "shown_better" and out["counts"] == {"wins": 9, "losses": 1, "ties": 4, "in_sample": 0}
    assert out["noise_floor"] == "unknown" and out["spend"]["total"] == 28.0
    assert prp.load_proposal(root, rec["proposal_id"])["state"] == "shown_better"
    host = MemoryCodeHost()
    opened = prp.open_pr(root, spec, rec["proposal_id"], host, push=False)
    body = host.pulls[0]["body"]
    assert opened["state"] == "opened" and "9 wins, 1 losses, 4 ties" in body and "case 3" not in body


def test_a_cap_stops_cleanly(repo: Path, pkg: Path) -> None:  # PRP-B7
    cases(pkg, 14)
    root, spec, rec = drafted(repo, pkg)
    run = fake_runner({"A": [0] * 14, "B": [1] * 14}, cost=25.0)
    out = trl.trial(root, spec, rec["proposal_id"], run, cap_usd=200)
    assert out["decision"] == "aborted" and len(out["pairs"]) == 4  # 4 cases x 2 arms x $25 = $200
    assert len(run.calls) == 8


def test_judge_graded_target_with_an_unmeasured_judge_spends_nothing(repo: Path, pkg: Path) -> None:  # PRP-AC4
    cases(pkg, 10)
    root, spec, rec = drafted(repo, pkg)
    run = fake_runner({"A": [0] * 10, "B": [1] * 10})
    with pytest.raises(trl.TrialRefused, match="before spend"):
        trl.trial(root, spec, rec["proposal_id"], run, target="gate_pass(draft)")
    assert run.calls == [] and not trl.all_trials(root)


def test_refusals_before_spend(repo: Path, pkg: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # PRP-B16, PRP-B17, PRP-B20, PRP-B7, PRP-B8
    root, spec, rec = drafted(repo, pkg)
    run = fake_runner({"A": [0], "B": [1]})
    (pkg / "evals" / "cases.json").write_text(json.dumps({"cases": []}))
    with pytest.raises(trl.TrialRefused, match="no reviewed case set"):
        trl.trial(root, spec, rec["proposal_id"], run)
    cases(pkg, 3)
    monkeypatch.setattr(trl, "month_spend", lambda *a, **k: 10_000.0)
    with pytest.raises(trl.TrialRefused, match="monthly trial cap"):
        trl.trial(root, spec, rec["proposal_id"], run)
    assert run.calls == []


def test_in_sample_case_is_reported_apart(repo: Path, pkg: Path) -> None:  # PRP-B17, PRP-AC5
    cases(pkg, 10, harvested_from="release-notes/T-1")
    root, spec, rec = drafted(repo, pkg)
    out = trl.trial(root, spec, rec["proposal_id"], fake_runner({"A": [0] * 10, "B": [1] * 10}))
    assert out["pairs"][0]["in_sample"] and out["counts"]["in_sample"] == 1 and out["counts"]["wins"] == 9


def test_aa_records_the_noise_floor(repo: Path, pkg: Path) -> None:  # PRP-B18, PRP-B19, PRP-B20 noise floor
    cases(pkg, 4)
    root, spec, _ = drafted(repo, pkg)
    flip = {"n": 0}

    def run(spec_: Any, case: Any, arm: str, tid: str) -> list[dict[str, Any]]:
        flip["n"] += 1
        code = 3 if case.case_id in ("k0", "k1", "k2") and arm == "A2" else 0
        return [{"kind": "run_exit", "exit_code": code, "cost": {"reported": 0.5}}]

    out = trl.aa(root, spec, run)
    assert out["noise_floor"] == 0.75
    _, digest = trl.case_set(spec)
    assert trl.noise_floor(root, spec.name, digest) == 0.75
    got = trl.decide(pairs(9, 1, 0), HOLD, 0.75)
    assert "noisy_case_set" in got["warnings"]


def test_trial_cases_start_at_their_base(repo: Path) -> None:  # WTR-B21 `ref:` base, ADR-0090 S4
    first = git(repo, "rev-parse", "HEAD").strip()
    (repo / "later.md").write_text("later\n")
    git(repo, "add", "later.md")
    git(repo, "commit", "-q", "-m", "later")
    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    out = go(repo, ex, task="R-1", flags={"run.worktree.base": f"ref:{first}"})
    assert out.exit_code is ExitCode.FINISHED, out.message
    ws = next(r for r in records(repo, "R-1") if r["kind"] == "workspace")
    assert ws["base_commit"] == first
    assert not (Path(ws["path"]) / "later.md").exists()
    bad = go(repo, standin("claude"), task="R-2", flags={"run.worktree.base": "ref:no-such-ref"})
    assert bad.exit_code is ExitCode.USAGE and bad.reason == "base_unresolved"


def test_child_runs_are_dry_trial_threads(repo: Path) -> None:  # PRP-AC6
    from .fixtures.workflows import two_step

    ex = standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()])
    reg = __import__("tempergraph.executors.registry", fromlist=["Registry"]).Registry()
    reg.register(ex)
    runner = trl.ChildRuns(repo=repo, registry=reg,
                           settings=lambda rs: dataclasses.replace(rs, sleep=lambda s: None))
    recs = runner(two_step(), trl.TrialCase(case_id="k0", base="HEAD", request="notes"), "A", "t1")
    started = next(r for r in recs if r["kind"] == "run_started")
    assert started["origin"] == "trial" and started.get("dry_run") is True
    seg = [json.loads(x) for x in (state_root_path(repo) / "ledger.jsonl").read_text().splitlines()
           if '"run_segment"' in x]
    assert seg and all(s["origin"] == "trial" for s in seg)
