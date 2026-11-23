"""What each member is shown: blind in round 0, anonymized later (CNL-B1, CNL-B2, CNL-AC5; task AC 2)."""

from __future__ import annotations

from tempergraph.run import council as cn

NAMES = ["architect", "skeptic", "operator"]
TEXTS = {"architect": "ARCH-ANSWER: use a queue", "skeptic": "SKEPT-ANSWER: a table is enough",
         "operator": "OPER-ANSWER: whatever pages less"}
STANCES = {"architect": "Think about structure", "skeptic": "Doubt every claim", "operator": "Think about on-call"}


def round0(name: str, **kw: object) -> str:
    return cn.member_prompt(question="Which store for the jobs?", stance=STANCES[name], round=0, mode="synthesize",
                            **kw)  # type: ignore[arg-type]


def test_cnl_ac5_a_round_0_prompt_holds_the_question_and_the_own_stance_and_nothing_of_another() -> None:  # CNL-AC5
    labels = cn.label_map(NAMES, "demo/T-1/decide/1")
    for name in NAMES:
        prompt = round0(name)
        assert "Which store for the jobs?" in prompt and STANCES[name] in prompt
        for other in NAMES:
            if other == name:
                continue
            assert STANCES[other] not in prompt and TEXTS[other] not in prompt
            assert other not in prompt  # no name of another member
            assert labels[other] not in prompt  # no label of another member
        for word in ("claude", "antigravity", "messages-api", "small", "medium", "large"):  # no executor or model
            assert word not in prompt.lower().replace("claude code", "")


def test_a_round_0_prompt_asks_for_the_answer_block_and_no_change_fields() -> None:  # CNL-B1, CNL-B11
    prompt = round0("architect")
    assert "```json" in prompt and '"position"' in prompt and '"confidence"' in prompt
    assert "why_changed" not in prompt and "dissent" not in prompt  # rounds 1 and later only


def test_cnl_b2_a_later_round_shows_the_others_answers_under_labels_and_omits_the_own() -> None:  # CNL-B2, CNL-AC5
    labels = cn.label_map(NAMES, "demo/T-1/decide/1")
    peers = [(labels[n], TEXTS[n]) for n in NAMES if n != "skeptic"]
    prompt = cn.member_prompt(question="Which store?", stance=STANCES["skeptic"], round=1, mode="synthesize",
                              peers=peers, own_previous=TEXTS["skeptic"])
    assert TEXTS["architect"] in prompt and TEXTS["operator"] in prompt
    assert labels["architect"] in prompt and labels["operator"] in prompt
    assert "architect" not in prompt.replace(TEXTS["architect"], "") and "operator" not in prompt.replace(TEXTS["operator"], "")
    assert labels["skeptic"] not in prompt  # its own label is omitted
    assert STANCES["architect"] not in prompt and STANCES["operator"] not in prompt
    for field in ("changed", "why_changed", "dissent"):
        assert f'"{field}"' in prompt  # a deliberation round requires all three


def test_the_labels_are_fixed_per_attempt_and_recorded() -> None:  # CNL-B2, CNL-B9
    a = cn.label_map(NAMES, "demo/T-1/decide/1")
    assert a == cn.label_map(NAMES, "demo/T-1/decide/1")  # the same attempt, the same order
    assert sorted(a.values()) == ["Member A", "Member B", "Member C"]
    assert len(set(a.values())) == 3
    orders = {tuple(cn.order_of(NAMES, f"seed-{i}")) for i in range(12)}
    assert len(orders) > 1  # another attempt may order them differently
    assert [cn.label_map(NAMES, "s")[n] for n in cn.order_of(NAMES, "s")] == ["Member A", "Member B", "Member C"]


def test_without_anonymity_a_later_round_names_the_authors() -> None:  # CNL-B2
    prompt = cn.member_prompt(question="Q?", stance="S", round=1, mode="synthesize",
                              peers=[("architect", "ARCH-ANSWER")], anonymize=False, own_previous="MINE")
    assert "architect" in prompt and "ARCH-ANSWER" in prompt and "Member A" not in prompt


def test_a_vote_prompt_lists_the_options_and_a_rank_pass_lists_the_peers() -> None:  # CNL-B11
    vote = cn.member_prompt(question="Ship?", stance="S", round=0, mode="vote", options=("ship", "hold"))
    assert "ship" in vote and "hold" in vote and "abstain" in vote and '"choice"' in vote
    rank = cn.ranking_prompt(question="Which?", peers=[("Member A", "AAA"), ("Member B", "BBB")], own_previous="MINE")
    assert "Member A" in rank and "Member B" in rank and "AAA" in rank and '"ranking"' in rank
