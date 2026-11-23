"""The fenced JSON answer block of a member, the single re-ask and the spoiled answer (CNL-B11, CNL-AC3; task AC 3)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tempergraph.run import council as cn


def block(**fields: Any) -> str:
    return "My reasoning.\n```json\n" + json.dumps(fields) + "\n```\n"


def parse(text: str, **kw: Any) -> cn.Answer:
    base: dict[str, Any] = {"mode": "synthesize", "options": (), "round": 0, "peers": ()}
    base.update(kw)
    return cn.parse_answer(text, **base)


def test_cnl_ac3_a_synthesize_block_is_read() -> None:  # CNL-AC3 (CNL-B11)
    a = parse(block(position="use a queue", confidence=0.8))
    assert a.status == "ok" and a.position == "use a queue" and a.confidence == 0.8 and a.choice is None
    assert a.text.startswith("My reasoning.")


def test_cnl_ac3_a_vote_block_takes_an_option_or_abstain() -> None:  # CNL-AC3 (CNL-B11)
    opts = ("ship", "hold")
    assert parse(block(position="p", choice="ship", confidence=1), mode="vote", options=opts).choice == "ship"
    assert parse(block(position="p", choice="abstain", confidence=0.1), mode="vote", options=opts).choice == "abstain"
    with pytest.raises(cn.Unparsed):
        parse(block(position="p", choice="maybe", confidence=0.5), mode="vote", options=opts)
    with pytest.raises(cn.Unparsed):
        parse(block(position="p", confidence=0.5), mode="vote", options=opts)


def test_cnl_ac3_a_ranking_names_every_peer_and_never_its_own() -> None:  # CNL-AC3 (CNL-B11)
    peers = ("Member B", "Member C")
    ok = parse(block(position="p", ranking=["Member C", "Member B"], confidence=0.5), mode="rank", peers=peers)
    assert ok.ranking == ("Member C", "Member B")
    for bad in (["Member B"], ["Member B", "Member B"], ["Member B", "Member A"], "Member B"):
        with pytest.raises(cn.Unparsed):
            parse(block(position="p", ranking=bad, confidence=0.5), mode="rank", peers=peers)


def test_a_deliberation_round_requires_changed_why_changed_and_dissent() -> None:  # CNL-AC3 (CNL-B11, CNL-B2)
    full = block(position="p", confidence=0.4, changed=True, why_changed="saw the cost", dissent="")
    a = parse(full, round=1)
    assert a.changed is True and a.why_changed == "saw the cost" and a.dissent == ""
    for missing in ("changed", "why_changed", "dissent"):
        fields = {"position": "p", "confidence": 0.4, "changed": False, "why_changed": "", "dissent": "x"}
        del fields[missing]
        with pytest.raises(cn.Unparsed):
            parse(block(**fields), round=1)
    assert parse(block(position="p", confidence=0.4), round=0).changed is None  # round 0 has none


@pytest.mark.parametrize("text", ["no block at all", "```json\nnot json\n```", "```json\n[1, 2]\n```",
                                  block(position=""), block(confidence=0.5), block(position="p", confidence=2),
                                  block(position="p", confidence="high")])
def test_a_block_that_does_not_parse_raises(text: str) -> None:  # CNL-AC3 (CNL-B11)
    with pytest.raises(cn.Unparsed):
        parse(text)


def test_the_last_block_is_the_one_read() -> None:  # CNL-B11
    text = block(position="first", confidence=0.1) + "\nOn reflection:\n" + block(position="second", confidence=0.9)
    assert parse(text).position == "second"


def test_a_reask_names_the_problem_and_asks_for_the_block_only() -> None:  # CNL-AC3 (CNL-B11)
    text = cn.reask_prompt("I think a queue. Thanks!", "no fenced JSON block", mode="synthesize", options=(), round=0)
    assert "no fenced JSON block" in text and "```json" in text and "I think a queue" in text


def test_a_spoiled_answer_keeps_its_text_and_counts_as_spoiled() -> None:  # CNL-AC3 (CNL-B11)
    a = cn.spoiled("garbled")
    assert a.status == "spoiled" and a.text == "garbled" and a.choice is None and a.ranking == ()
    assert cn.Answer.from_json(a.to_json()) == a


def test_an_answer_round_trips_through_json() -> None:  # CNL-B14
    a = parse(block(position="p", confidence=0.3, changed=False, why_changed="", dissent="d"), round=2)
    assert cn.Answer.from_json(a.to_json()) == a
