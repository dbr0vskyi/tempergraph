"""Caller provenance (PRV-B13, PRV-B14, B1–B10, AC-1, AC-4, AC-5)."""

from __future__ import annotations

import itertools
import json
import os
from pathlib import Path
from typing import Any

import pytest

from tempergraph.provenance import CallerRefused, classify, decide, may_widen

from .test_cli import cli, happy
from .test_feedback import records
from .test_run import DRAFT, REVIEW, judge

CC = {"CLAUDE_CODE_CHILD_SESSION": "1", "CLAUDE_CODE_SESSION_ID": "sess-1", "CLAUDECODE": "1"}


@pytest.mark.parametrize(("env", "tty", "declared", "app", "kind", "confidence", "host"), [
    ({}, True, None, None, "person", "observed", "terminal"),  # PRV-B1
    (CC, False, None, None, "agent", "marked", "claude-code"),  # PRV-B2
    ({"CLAUDECODE": "1"}, True, None, None, "person", "observed", "terminal"),  # PRV-B3
    ({"GITHUB_ACTIONS": "true", "CI": "true"}, False, None, None, "pipeline", "marked", "ci:github-actions"),  # B7
    ({}, False, None, None, "unknown", "none", "unknown"),  # PRV-B8
    ({}, False, "agent", "triage-bot", "agent", "declared", "messages-api-app"),  # PRV-B10
    ({}, True, "pipeline", None, "pipeline", "declared", "unknown"),
    ({}, False, "person", None, "unknown", "declared", "unknown"),  # row 7
])
def test_classification_rows(env: dict[str, str], tty: bool, declared: str | None, app: str | None, kind: str,
                             confidence: str, host: str) -> None:  # PRV-AC1
    b = classify(env, tty, declared=declared, caller_app=app)
    assert (b["kind"], b["confidence"], b["host"]) == (kind, confidence, host)
    if env.get("CLAUDECODE") and not env.get("CLAUDE_CODE_CHILD_SESSION"):
        assert {"signal": "S3", "value": "set"} in b["evidence"]


@pytest.mark.parametrize(("env", "declared", "code"), [
    (CC, "person", "caller_conflict"), ({}, "orchestrator", "caller_reserved"),
    ({"TEMPERGRAPH_SESSION_KEY": "draft-1"}, None, "engine_session_caller"),
    ({"TEMPERGRAPH_SUPERVISOR_TOKEN": "x"}, None, "supervisor_token_invalid"),
    ({"TEMPERGRAPH_SCHEDULE_TOKEN": "x"}, None, "schedule_token_invalid")])
def test_refused_callers(env: dict[str, str], declared: str | None, code: str) -> None:  # PRV-B5, PRV-B18, PRV-B17, PRV-B14, PRV-B13, PRV-B19, PRV-B15
    with pytest.raises(CallerRefused) as exc:
        classify(env, True, declared=declared)
    assert exc.value.code == code


def test_a_schedule_token_with_a_matching_entry_is_the_scheduler() -> None:  # TCK-AC4, TCK-B17
    import hashlib

    entry = {"schedule_id": "digest-1a2b", "token_digest": hashlib.sha256(b"s3cret").hexdigest(),
             "created": {"caller": {"kind": "person", "decided_by": "person"}}}
    seen: list[str] = []

    def lookup(fire_id: str) -> dict[str, Any] | None:
        seen.append(fire_id)
        return entry if fire_id.startswith("digest-1a2b@") else None

    fire = "digest-1a2b@20261124T0800Z"
    b = classify({"TEMPERGRAPH_SCHEDULE_TOKEN": "s3cret"}, False, schedule=fire, entry_for_fire=lookup)
    assert (b["kind"], b["confidence"], b["host"], seen) == ("scheduler", "attested", "schedule", [fire])
    assert b["schedule"] == {"schedule_id": "digest-1a2b", "fire_id": fire, "slot": "2026-11-24T08:00:00Z",
                             "created_by": {"kind": "person", "decided_by": "person"}}
    for env, name in (({"TEMPERGRAPH_SCHEDULE_TOKEN": "nope"}, fire), ({"TEMPERGRAPH_SCHEDULE_TOKEN": "s3cret"}, "x@20261124T0800Z")):
        with pytest.raises(CallerRefused) as exc:
            classify(env, False, schedule=name, entry_for_fire=lookup)
        assert exc.value.code == "schedule_token_invalid"
    with pytest.raises(CallerRefused) as exc:  # with no lookup the old refusal holds
        classify({"TEMPERGRAPH_SCHEDULE_TOKEN": "s3cret"}, False, schedule=fire)
    assert exc.value.code == "schedule_token_invalid"


def test_a_marker_never_gives_a_person() -> None:  # PRV-AC4
    extras = [("CLAUDECODE", "1"), ("CI", "true"), ("GITHUB_ACTIONS", "true")]
    for n in range(len(extras) + 1):
        for combo in itertools.combinations(extras, n):
            for tty, declared in itertools.product((True, False), (None, "agent", "pipeline", "person")):
                env = {"CLAUDE_CODE_CHILD_SESSION": "1", **dict(combo)}
                try:
                    b = classify(env, tty, declared=declared)
                except CallerRefused:
                    continue
                assert b["kind"] != "person"


def journal(home: Path, *turns: dict[str, Any]) -> None:
    p = home / "supervision" / "claude-code" / "sess-1.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps({"kind": "person_turn", **t}) + "\n" for t in turns))


@pytest.mark.parametrize(("turns", "relayed", "decided_by", "relay"), [
    ([{"at": "2026-11-20T10:05:00+00:00", "names": ["proceed"]}], True, "person", "turn_named"),
    ([{"at": "2026-11-20T10:05:00+00:00", "names": []}], True, "person", "turn_only"),
    ([{"at": "2026-11-20T09:40:00+00:00", "names": ["proceed"]}], True, "agent", "claimed"),
    ([{"at": "2026-11-20T10:05:00+00:00", "names": ["proceed"]}], False, "agent", "none"),
])
def test_relay_table(tmp_path: Path, turns: list[dict[str, Any]], relayed: bool, decided_by: str,
                     relay: str) -> None:  # PRV-B4
    journal(tmp_path, *turns)
    b = decide(classify(CC, False), relayed=relayed, words=("proceed",), since="2026-11-20T10:00:00+00:00",
               home=tmp_path)
    assert (b["decided_by"], b["relay"]) == (decided_by, relay)
    assert may_widen(b) is (relay == "turn_named")


def test_cli_records_the_caller_and_refuses_a_conflict(repo: Path) -> None:  # PRV-B1, B5
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "P-1")
    assert code == 0, err
    c = records(repo, "P-1", "run_started")[0]["caller"]
    assert c["kind"] == "person" and c["confidence"] == "observed" and c["call_id"]
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "P-2", "--caller", "person",
                       signals=(CC, False))
    assert code == 2 and "caller_conflict" in err
    assert not (repo / ".tempergraph" / "runs" / "demo" / "P-2").exists()
    code, _, err = cli(repo, happy(), "run", "demo", "notes", "--task-id", "P-3", "--relayed")
    assert code == 2 and "relay_not_applicable" in err


def test_a_relayed_grant_needs_a_named_person_turn(repo: Path) -> None:  # PRV-B9, AC-5
    from tempergraph.executors.standins import answer, standin

    home = Path(os.environ["TEMPERGRAPH_HOME"])
    blocked = answer("No tracker\nBLOCKED: refused", denied=("mcp__tracker__get_issue",))
    ex = standin("claude", steps=[blocked], judges=[])
    assert cli(repo, ex, "run", "demo", "notes", "--task-id", "P-4", signals=(CC, False))[0] == 3
    grant = ["resume", "demo", "P-4", "--decision", "retry", "--grant", "draft=mcp:tracker/get_issue", "--relayed"]
    code, _, err = cli(repo, ex, *grant, signals=(CC, False))
    assert code == 2 and "widening_by_agent" in err
    journal(home, {"at": "2999-01-01T00:00:00+00:00", "names": ["retry"]})
    ex.steps, ex.judges = [DRAFT, REVIEW], [judge(), judge()]
    code, _, err = cli(repo, ex, *grant, signals=(CC, False))
    assert code == 0, err
    human = records(repo, "P-4", "human")[-1]["caller"]
    assert human["kind"] == "agent" and human["decided_by"] == "person" and human["relay"] == "turn_named"
