"""Deliverables per path, a repository's declared commands and `GitFacts.pushed` (second-release plan I2-26)."""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tempergraph.api import Gate, Judge, Routing, Step, Workflow
from tempergraph.constants import ExitCode
from tempergraph.contracts import SessionRequest, SessionResult
from tempergraph.executors.standins import answer, standin
from tempergraph.model.validate import errors, validate
from tempergraph.run.checks import CheckContext, git_facts
from tempergraph.run.commands import REPO_FILE, CommandRefusal, expand, repository_commands, resolve_command
from tempergraph.run.outcome import deliverable_producers, outcome_check, parse_outcome
from tempergraph.run.runner import RunSettings, start

from .fixtures.workflows import crit, named, routed
from .test_outcome import MINIMAL
from .test_run import MET, registry

NO_SLEEP = RunSettings(sleep=lambda s: None)
CAPS = {"claude": standin("claude").capabilities()}


# -- deliverables per path (research `release-two-readiness-and-gaps` G10, OUT-B15, OUT-B16, OUT-B17) ----------------------------------------------------------


def outcome_ctx(tmp_path: Path, *, path: list[str], arts: dict[str, Any]) -> Any:
    settings = {"deliverables": [{"key": "notes", "kind": "file", "where": "notes.md"},
                                 {"key": "review", "kind": "file", "where": "review.md"}],
                "deliverable_producers": {"notes": ["draft"], "review": ["review"]}, "path_units": path}
    return SimpleNamespace(settings=settings, artifacts=arts, values={}, workdir=tmp_path)


def test_a_deliverable_is_required_only_on_a_path_that_produces_it(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("n\n")
    light = outcome_check(outcome_ctx(tmp_path, path=["draft"], arts={"draft": {"notes": "notes.md"}}))
    assert light.result == "PASS" and "1 of 1 deliverables present; 1 not produced on this path" in light.evidence
    full = outcome_check(outcome_ctx(tmp_path, path=["draft", "review"], arts={"draft": {"notes": "notes.md"}}))
    assert full.result == "FAIL" and [f.message for f in full.findings] == ["deliverable review is missing"]
    unknown = outcome_ctx(tmp_path, path=["draft"], arts={})
    unknown.settings["deliverable_producers"] = {}
    assert len(outcome_check(unknown).findings) == 2  # a key no unit declares stays required


def test_producers_come_from_the_declarations_and_off_path_references_are_optional() -> None:
    spec = routed()
    draft = spec.units["draft"]
    units = {**spec.units,
             "draft": dataclasses.replace(draft, step=dataclasses.replace(draft.step, produces={
                 **draft.step.produces, "notes": "file"})),
             "review": dataclasses.replace(spec.units["review"], step=dataclasses.replace(
                 spec.units["review"].step, produces={"review": "file"}))}
    doc = {**MINIMAL, "deliverables": [{"key": "notes", "kind": "file", "where": "notes.md"},
                                       {"key": "review", "kind": "file", "where": "review.md"}],
           "intermediate": {}}
    o = parse_outcome(doc)
    assert not isinstance(o, list)
    spec = dataclasses.replace(spec, units=units, outcome=o)
    assert deliverable_producers(spec) == {"notes": ["draft"], "review": ["review"]}
    from tempergraph.run.outcome import with_outcome

    judge = with_outcome(spec).units["outcome"].gate.judge
    assert judge is not None and judge.references["review"] == "optional"  # `draft` may route past `review`


# -- a repository's declared commands (research `release-two-readiness-and-gaps` G11, CHK-B11) -------------------------------------------------


def declare(repo: Path, commands: Any) -> None:
    (repo / REPO_FILE).write_text(json.dumps({"schema_version": 1, "commands": commands}))


def test_a_repository_declares_its_commands(tmp_path: Path) -> None:
    declare(tmp_path, {"test": "npm test", "lint": "npm  run lint", "bad": "rm -rf / ; echo", "up": "../tool"})
    assert repository_commands(tmp_path) == ["npm test", "npm run lint"]
    got = resolve_command(["pytest", "@repository"], "npm test -- --watch=false", tmp_path)
    assert not isinstance(got, CommandRefusal) and got.documented and got.resolver == "repository"
    assert got.prefix == "npm test"
    plain = resolve_command(["pytest", "@repository"], "pytest -q", tmp_path)
    assert not isinstance(plain, CommandRefusal) and not plain.documented and plain.resolver == "allow_list"
    refused = resolve_command(["pytest"], "npm test", tmp_path)  # the workflow did not ask for them
    assert isinstance(refused, CommandRefusal) and refused.reason == "not declared"
    assert isinstance(resolve_command(["@repository"], "npm test; rm -rf x", tmp_path), CommandRefusal)
    assert isinstance(resolve_command(["@repository"], "@repository", tmp_path), CommandRefusal)


def test_a_missing_or_malformed_file_declares_nothing(tmp_path: Path) -> None:
    assert repository_commands(tmp_path) == []
    (tmp_path / REPO_FILE).write_text("{not json")
    assert repository_commands(tmp_path) == []
    (tmp_path / REPO_FILE).write_text(json.dumps({"schema_version": 2, "commands": ["make"]}))
    assert repository_commands(tmp_path) == []
    declare(tmp_path, ["make test", "make test", 7])
    assert repository_commands(tmp_path) == ["make test"] and expand(["git status", "@repository"], tmp_path) == (
        "git status", "make test")


class Capture:
    def __init__(self) -> None:
        self.inner = standin("claude")
        self.name = self.inner.name
        self.request: SessionRequest | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def run_step(self, req: SessionRequest, sink: Any) -> SessionResult:
        self.request = req
        return answer("Done.", session_id="s")

    def run_judge(self, req: SessionRequest, views: Any, sink: Any) -> SessionResult:
        return answer(MET, tools=("Read",), session_id="j")


def test_a_step_gets_the_repositorys_commands(repo: Path) -> None:
    declare(repo, ["make test"])
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "commands"], cwd=repo, check=True)
    units = {"verify": Step(prompt="Verify {request}", tools=["read", "shell"], commands=["git status", "@repository"],
                            gate=Gate(judge=Judge(stance="V."), criteria=[crit("c1")]))}
    spec = named(Workflow(order=["verify"], units=units, issue_repository="acme/x",
                          allow_commands=["git status", "@repository"],
                          routing=Routing(description="Verify with the repository's own commands")))
    assert not errors(validate(spec, CAPS))
    ex = Capture()
    out = start(spec, "C-1", {"request": "x"}, repo, registry(ex), NO_SLEEP)
    assert out.exit_code is ExitCode.FINISHED, out.message
    assert ex.request is not None and ex.request.commands == ("git status", "make test")
    assert "- `make test`" in ex.request.prompt and "@repository" not in ex.request.prompt


# -- GitFacts.pushed (research `release-two-readiness-and-gaps` G12, CHK-B10) ------------------------------------------------------------------


def test_pushed_is_set_from_the_remote_tracking_refs(repo: Path, tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    assert git_facts(repo).pushed is False  # no remote
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git("remote", "add", "origin", str(remote))
    git("checkout", "-q", "-b", "feature/x")
    assert git_facts(repo).pushed is False
    git("push", "-q", "origin", "feature/x")
    assert git_facts(repo).pushed is True and git_facts(repo).branch == "feature/x"
    git("checkout", "-q", "-b", "feature/local")
    assert git_facts(repo).pushed is False
    assert isinstance(CheckContext(unit="u", workdir=repo, request={}).git.pushed, bool)
