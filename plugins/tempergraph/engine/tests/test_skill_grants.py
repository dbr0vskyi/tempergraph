"""Skill grants that hold on step sessions (ECC-B25, LIF-B19, TSA-B14; GitHub issue #221)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from tempergraph.api import Gate, Judge, Step, Workflow
from tempergraph.contracts import EventSink, SessionRequest
from tempergraph.executors.capabilities import DECLARED
from tempergraph.executors.claude import ClaudeExecutor, list_skills, step_argv, step_env
from tempergraph.improve import digest
from tempergraph.model.validate import validate

from .fixtures import streams as S
from .fixtures.workflows import crit, named
from .test_session_review import rec, session

FLAGS = frozenset({"--permission-prompts", "--disable-slash-commands"})
LISTED = ["deep-research", "notes:alpha", "notes:beta", "code-review"]


def req(tmp_path: Path, **kw: object) -> SessionRequest:
    fields: dict[str, object] = {"kind": "step", "prompt": "Write notes.", "workdir": tmp_path, "alias": "medium",
                                 "session_key": "draft.1.step"}
    fields.update(kw)
    return SessionRequest(**fields)  # type: ignore[arg-type]


def flag(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv else None


# -- ECC-B25: the launch ----------------------------------------------------------------------------------------


def test_ecc_ac20_a_declared_skill_is_allowed_by_name_and_every_other_listed_skill_is_denied(tmp_path: Path) -> None:
    r = req(tmp_path, tools=("read", "skill:notes:alpha"))
    argv, _ = step_argv(r, "sonnet", None, FLAGS, None, LISTED)
    assert "Skill(notes:alpha)" in (flag(argv, "--allowedTools") or "").split(",")
    assert "Skill" not in (flag(argv, "--allowedTools") or "").split(",")  # no bare rule any more
    denied = (flag(argv, "--disallowedTools") or "").split(",")
    assert denied == ["EnterWorktree", "ExitWorktree", "Skill(deep-research)", "Skill(notes:beta)",
                      "Skill(code-review)"]
    assert "--disable-slash-commands" not in argv
    assert "Skill" in (flag(argv, "--tools") or "").split(",")


def test_ecc_ac21_a_step_that_declares_no_skill_runs_with_skills_switched_off(tmp_path: Path) -> None:
    argv, _ = step_argv(req(tmp_path, tools=("read",)), "sonnet", None, FLAGS)
    assert "--disable-slash-commands" in argv
    assert flag(argv, "--disallowedTools") == "EnterWorktree,ExitWorktree"
    argv, _ = step_argv(req(tmp_path, tools=("read",)), "sonnet", None, frozenset())
    assert "--disable-slash-commands" not in argv  # only when the probe saw the flag


def test_ecc_ac20_the_listing_launch_reads_the_skills_at_init_and_stops(tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    S.fake_claude(tmp_path, monkeypatch, {"lines": [{**S.init(), "skills": LISTED}], "hang": 30})
    found = list_skills(["claude", "-p"], tmp_path, step_env("sonnet"), timeout_s=10)
    assert found == LISTED


def test_ecc_ac20_a_listing_with_no_init_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    S.fake_claude(tmp_path, monkeypatch, {"lines": [S.result()]})
    assert list_skills(["claude", "-p"], tmp_path, step_env("sonnet"), timeout_s=10) is None


def test_ecc_ac20_a_step_with_a_declared_skill_launches_with_the_denials(tmp_path: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    record = tmp_path / "rec.json"
    S.fake_claude(tmp_path, monkeypatch, {"record": str(record), "help": "--tools --strict-mcp-config "
                                          "--disable-slash-commands",
                                          "lines": [{**S.init(), "skills": LISTED}, S.result()]})
    ex = ClaudeExecutor(bindings=None, home=tmp_path)
    monkeypatch.setattr(ClaudeExecutor, "binding", property(lambda self: _Binding()))
    res = ex.run_step(req(tmp_path, tools=("read", "skill:notes:alpha")), EventSink())
    assert res.ok
    argv = json.loads(record.read_text())["argv"]
    assert "Skill(notes:beta)" in argv[argv.index("--disallowedTools") + 1]


def test_ecc_ac20_a_declared_skill_is_refused_when_the_listing_fails(tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    S.fake_claude(tmp_path, monkeypatch, {"lines": [S.result()]})
    ex = ClaudeExecutor(bindings=None, home=tmp_path)
    monkeypatch.setattr(ClaudeExecutor, "binding", property(lambda self: _Binding()))
    monkeypatch.setattr("tempergraph.executors.claude.list_skills", lambda *a, **k: None)
    res = ex.run_step(req(tmp_path, tools=("read", "skill:notes:alpha")), EventSink())
    assert not res.ok and res.error_kind == "refused" and "skills" in (res.text or "")


class _Binding:
    def model(self, alias: str | None) -> str:
        return "sonnet"


# -- LIF-B17: a prompt that names a skill its step does not declare --------------------------------------------------


def _package(tmp_path: Path, tools: list[str]) -> Path:
    root = tmp_path / "pkg"
    (root / "skills" / "alpha").mkdir(parents=True)
    (root / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: Use when.\n---\nDo it.\n")
    return root


def test_lif_ac14_a_step_prompt_naming_an_undeclared_package_skill_is_an_error(tmp_path: Path) -> None:
    root = _package(tmp_path, [])
    for tools, expect in ((["read"], True), (["read", "skill:pkg:alpha"], False)):
        wf = Workflow(order=["draft"], units={"draft": Step(
            prompt="Open skill `alpha` first. {request}", tools=tools,
            gate=Gate(judge=Judge(stance="V."), criteria=[crit("c1")]))})
        spec = dataclasses.replace(named(wf), package_root=root)
        found = [f for f in validate(spec, DECLARED) if f.code == "lint-skill-undeclared"]
        assert bool(found) is expect, tools
        if expect:
            assert found[0].severity == "error" and found[0].unit == "draft"


# -- TSA-B14: the digest lists each undeclared skill called, and the review names it ---------------------------------


def test_tsa_ac7_an_undeclared_skill_call_is_listed_and_becomes_a_cause(tmp_path: Path) -> None:
    calls = [{"name": "Skill", "cap": "skill", "summary": "notes:alpha"},
             {"name": "Skill", "cap": "skill", "summary": "code-review", "ok": False}]
    sdir = session(tmp_path, "K-1", "draft.1.step", calls)
    d = digest.build(sdir, rec("draft.1.step"), {"tools": ["read", "skill:notes:alpha"]})
    assert d["skills_undeclared"] == ["code-review"]
    found = {(c["unit"], c["cause"]) for c in digest.causes([d])}
    assert ("draft", "skill_undeclared:code-review") in found
    assert not any(c.startswith("skill_undeclared:notes") for _, c in found)
