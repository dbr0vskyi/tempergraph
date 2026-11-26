"""ECC-AC19: the live probe of the MCP isolation reads every turn of a session (offline tests of its helper)."""

from __future__ import annotations

from typing import Any

from .fixtures import mcp_turns as M


def _init(tools: list[str]) -> dict[str, Any]:
    return {"type": "system", "subtype": "init", "tools": tools, "mcp_servers": []}


def _turn(tokens: int) -> dict[str, Any]:
    usage = {"input_tokens": 10, "cache_read_input_tokens": tokens - 110, "cache_creation_input_tokens": 100,
             "output_tokens": 5}
    return {"type": "assistant", "message": {"usage": usage, "content": []}}


def _stream(*tokens: int, tools: list[str] | None = None) -> list[dict[str, Any]]:
    return [_init(tools if tools is not None else ["Read"]), *[_turn(t) for t in tokens],
            {"type": "result", "subtype": "success"}]


def test_ecc_ac19_clean_isolated_session_has_no_leak_and_three_readings() -> None:
    ev = _stream(9000, 9050, 9100)
    assert M.leaks(ev) == []
    rs = M.turn_readings(ev)
    assert len(rs) == 3
    assert [r["turn"] for r in rs] == [1, 2, 3]
    assert rs[0]["context"] == 9000
    assert rs[0]["tools"] == ["Read"]
    assert M.enough_turns(ev)


def test_ecc_ac19_a_context_jump_at_the_second_turn_is_a_leak_naming_turn_2() -> None:
    ev = _stream(8800, 174123)
    out = M.leaks(ev)
    assert len(out) == 1 and "turn 2" in out[0] and "174123" in out[0]


def test_ecc_ac19_account_connector_tools_in_init_are_a_leak() -> None:
    out = M.leaks(_stream(9000, 9000, tools=["Read", "mcp__claude_ai_Gmail__search"]))
    assert len(out) == 1 and "mcp__claude_ai_Gmail__search" in out[0]


def test_ecc_ac19_tools_of_an_undeclared_server_are_a_leak() -> None:
    ev = _stream(9000, 9000, tools=["Read", "mcp__other__get"])
    assert len(M.leaks(ev)) == 1


def test_ecc_ac19_a_declared_servers_own_tools_are_not_a_leak() -> None:
    ev = _stream(9000, 9000, tools=["Read", "mcp__tracker__get_issue"])
    assert M.leaks(ev, declared=("tracker",)) == []


def test_ecc_ac19_one_turn_is_too_short_to_prove_isolation() -> None:
    ev = _stream(9000)
    assert not M.enough_turns(ev)
    assert M.leaks(ev) == []


def test_ecc_ac19_a_judge_shaped_stream_is_read_the_same_way() -> None:
    judge = [_init(["Read"]), _turn(9000), {"type": "user", "message": {"content": []}}, _turn(9200),
             {"type": "result", "subtype": "success"}]
    assert M.enough_turns(judge) and M.leaks(judge) == []
    judge[3] = _turn(60000)
    assert len(M.leaks(judge)) == 1
