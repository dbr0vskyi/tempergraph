"""Unattended credential kinds and the per-executor check (TCK-B5, TCK-B6, TCK-B18, TCK-B19; TCK-AC6, AC 4).

A fixture per executor and kind, with a scripted environment and no model call."""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path

import pytest

from tempergraph.cli import schedule_cli
from tempergraph.executors.capabilities import DECLARED
from tempergraph.schedule import credentials, store
from tempergraph.store.layout import home_path

from .conftest import hash_tree
from .test_schedule_cli import NOW, WARSAW, add, home_hash

ALL = ("api_key", "cloud", "oauth_token", "interactive_login")
SIGNALS = {"api_key": {"ANTHROPIC_API_KEY": "sk-x"}, "cloud": {"CLAUDE_CODE_USE_BEDROCK": "1"},
           "oauth_token": {"CLAUDE_CODE_OAUTH_TOKEN": "tok"}}


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
                "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(home_path().parent))  # no cached sign-in unless a test writes one


def held(executor: str, env: dict[str, str], profile: dict[str, str] | None = None, login: bool = False) -> frozenset[str]:
    return credentials.resolve_kinds(executor, env, profile or {}, login_present=login)


def check(executor: str, role: str, kinds: set[str] | frozenset[str], *, bare: bool = False, at_fire: bool = False
          ) -> credentials.Check:
    return credentials.check([{"executor": executor, "role": role, "bare": bare}], {executor: frozenset(kinds)}, at_fire=at_fire)


def test_tck_ac6_each_executor_declares_the_kinds_it_can_use_unattended_as_a_capability() -> None:
    assert DECLARED["claude"].unattended_credentials == frozenset(ALL)
    assert DECLARED["agent-sdk"].unattended_credentials == DECLARED["messages-api"].unattended_credentials == frozenset(
        {"api_key", "cloud"})
    assert DECLARED["antigravity"].unattended_credentials == frozenset({"api_key"})  # interactive_login waits for P-SCH-3


def test_tck_ac6_the_kinds_are_read_from_the_environment_and_the_profile_as_presence_only() -> None:
    assert held("claude", {}) == frozenset()
    assert held("claude", SIGNALS["api_key"]) == {"api_key"}
    assert held("claude", {}, {"apiKeyHelper": "/opt/bin/key"}) == {"api_key"}  # a helper command in the profile
    assert held("claude", SIGNALS["cloud"]) == {"cloud"}
    assert held("claude", SIGNALS["oauth_token"]) == {"oauth_token"}
    assert held("claude", {}, login=True) == {"interactive_login"}
    assert held("antigravity", {"GEMINI_API_KEY": "g"}) == {"api_key"}
    assert held("messages-api", {"ANTHROPIC_API_KEY": "k", "CLAUDE_CODE_OAUTH_TOKEN": "t"}) == {"api_key"}  # not its kind
    assert credentials.profile_values({"ANTHROPIC_API_KEY": "sk-x"}) == {"ANTHROPIC_API_KEY": "sk-x"}


@pytest.mark.parametrize("kind", ["api_key", "cloud", "oauth_token"])
def test_tck_ac6_claude_accepts_api_key_cloud_and_oauth_token(kind: str) -> None:
    r = check("claude", "step", {kind})
    assert r.refusal is None and r.warnings == [] and r.checked[0]["result"] == "ok"


def test_tck_ac6_claude_accepts_interactive_login_with_the_may_expire_warning() -> None:
    r = check("claude", "step", {"interactive_login"})
    assert r.refusal is None and r.warnings == ["credential_may_expire"] and r.checked[0]["may_expire"] is True


def test_tck_ac6_no_credential_at_add_is_saved_with_a_warning_and_refused_at_a_fire() -> None:
    # TCK-AC6, TCK-B19: found by the live fire in the cloud container, whose host-managed sign-in no kind names
    r = check("claude", "step", set())
    assert r.refusal is None and r.warnings == ["credential_none"] and r.checked[0]["result"] == "none"
    assert credentials.WARNING_TEXT["credential_none"]


@pytest.mark.parametrize("kinds", [{"oauth_token"}, {"interactive_login"}, {"oauth_token", "interactive_login"}])
def test_tck_b6_a_bare_judge_needs_api_key_or_cloud_else_judge_credential(kinds: set[str]) -> None:
    r = check("claude", "judge", kinds, bare=True)
    assert r.refusal is not None and r.refusal[0] == "judge_credential"
    assert "API key" in r.refusal[1] and "apiKeyHelper" in r.refusal[1] and "cloud" in r.refusal[1]
    for ok in ({"api_key"}, {"cloud"}, {"api_key", "oauth_token"}):
        assert check("claude", "judge", ok, bare=True).refusal is None
    assert check("claude", "judge", {"oauth_token"}, bare=False).refusal is None  # a judge not launched with --bare


@pytest.mark.parametrize("executor", ["agent-sdk", "messages-api"])
def test_tck_ac6_the_api_executors_accept_api_key_and_cloud_and_refuse_the_rest(executor: str) -> None:
    for kind in ("api_key", "cloud"):
        assert check(executor, "step", {kind}).refusal is None
    for kind in ("oauth_token", "interactive_login"):
        r = check(executor, "step", {kind})
        assert r.refusal is not None and r.refusal[0] == "credential_unattended" and executor in r.refusal[1]


def test_tck_ac6_antigravity_accepts_an_api_key_and_refuses_a_cached_sign_in() -> None:
    assert check("antigravity", "step", {"api_key"}).refusal is None
    r = check("antigravity", "step", {"interactive_login"})  # P-SCH-3 has not confirmed it
    assert r.refusal is not None and r.refusal[0] == "credential_unattended"
    assert check("antigravity", "step", {"interactive_login", "api_key"}).refusal is None


def test_tck_ac6_a_missing_credential_is_refused_at_a_fire_only() -> None:
    at_add = check("claude", "step", set())
    assert at_add.refusal is None and at_add.checked[0]["kinds"] == [] and at_add.checked[0]["result"] == "none"
    at_fire = check("claude", "step", set(), at_fire=True)
    assert at_fire.refusal is not None and at_fire.refusal[0] == "credential" and "claude" in at_fire.refusal[1]
    wrong = check("antigravity", "step", {"interactive_login"}, at_fire=True)
    assert wrong.refusal is not None and wrong.refusal[0] == "credential_unattended"


def test_tck_ac6_one_row_per_executor_and_role_and_an_unknown_executor_is_not_checked() -> None:
    r = credentials.check([{"executor": "claude", "role": "step", "bare": False}, {"executor": "claude", "role": "step"},
                           {"executor": "claude", "role": "judge", "bare": False}, {"executor": "scripted", "role": "step"}],
                          {"claude": frozenset({"api_key"}), "scripted": frozenset()}, at_fire=True)
    assert [(c["executor"], c["role"], c["result"]) for c in r.checked] == [
        ("claude", "step", "ok"), ("claude", "judge", "ok"), ("scripted", "step", "not_checked")]
    assert r.refusal is None  # an executor with no declared kinds has no credential to miss


def test_tck_ac6_the_check_makes_no_model_call_and_starts_no_process(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **k: object) -> None:
        raise AssertionError("a process was started")

    monkeypatch.setattr(subprocess, "Popen", boom)
    credentials.check([{"executor": "claude", "role": "step"}], {"claude": frozenset({"oauth_token"})}, at_fire=True)
    held("claude", SIGNALS["oauth_token"])


def test_tck_ac6_add_writes_executors_checked_with_kinds_and_no_value(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "the-oauth-secret")
    code, doc, err = add(repo)
    assert code == 0, err
    entry = store.read_entry(str(doc["schedule_id"]))
    assert {(c["executor"], c["role"]) for c in entry["executors_checked"]} == {("claude", "step"), ("claude", "judge")}
    assert all(c["kinds"] == ["oauth_token"] and c["result"] == "ok" for c in entry["executors_checked"])
    for p in home_path().rglob("*"):  # no entry or log of any trigger holds a credential value
        if p.is_file():
            assert "the-oauth-secret" not in p.read_text(encoding="utf-8", errors="replace"), p


def test_tck_b19_an_interactive_login_at_add_saves_with_a_warning(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    login = home_path().parent / ".claude" / ".credentials.json"
    login.parent.mkdir(parents=True)
    login.write_text("{}")
    code, doc, err = add(repo)
    assert code == 0 and "credential_may_expire" in err, err
    assert doc["warnings"] == ["credential_may_expire"]


def test_tck_b6_a_bare_judge_with_only_an_oauth_token_exits_2_judge_credential_at_add(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(credentials, "bare_judge", lambda executor: executor == "claude")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    before = home_hash()
    code, _, err = add(repo)
    assert code == 2 and "judge_credential" in err, err
    assert home_hash() == before  # saved nothing
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert add(repo)[0] == 0


def test_tck_ac6_a_kind_the_executor_cannot_use_exits_2_credential_unattended_at_add_and_edit(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, doc, _ = add(repo)
    sid = str(doc["schedule_id"])
    narrow = dataclasses.replace(DECLARED["claude"], unattended_credentials=frozenset({"api_key"}))
    monkeypatch.setitem(DECLARED, "claude", narrow)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    before, repo_before = home_hash(), hash_tree(repo)
    code, _, err = add(repo)
    assert code == 2 and "credential_unattended" in err and home_hash() == before
    code, _, err = schedule_edit(repo, sid)
    assert code == 2 and "credential_unattended" in err and home_hash() == before and hash_tree(repo) == repo_before


def schedule_edit(repo: Path, sid: str) -> tuple[int, object, str]:
    from .test_schedule_cli import sched

    return sched(repo, "edit", sid, "--overlap", "queue", "--yes")


def test_tck_b18_the_entry_records_checked_kinds_only(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
    _, doc, _ = add(repo)
    text = (home_path() / "schedules" / str(doc["schedule_id"]) / "entry.json").read_text(encoding="utf-8")
    assert "sk-secret-value" not in text and json.loads(text)["executors_checked"][0]["kinds"] == ["api_key"]
