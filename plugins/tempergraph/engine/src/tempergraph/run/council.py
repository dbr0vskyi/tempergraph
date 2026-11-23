"""What a council decides without a session (CNL-B1 to CNL-B3, CNL-B10 to CNL-B13; ADR-0063).

Everything here is plain code on plain values: the labels `Member A`, `Member B` in an order fixed per attempt, the prompts
a member is given, the reading of its fenced JSON answer block, the tally of the four vote rules, the Borda count with its
two tie-breaks, the outcome of each mode and the three artifacts. It imports no executor and makes no model call, so the
outcome of a council never rests on a model reading the ballots (CNL-B3, CNL-AC2).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.S)
ABSTAIN = "abstain"
NO_DECISION = "no_decision"
SYNTHESIZED = "synthesized"
REASK_TAIL = 1500


class Unparsed(ValueError):
    """A member's answer ends with no readable block (CNL-B11)."""


# ---------------------------------------------------------------------------------------------
# Labels


def order_of(names: Sequence[str], seed: str) -> list[str]:
    """The members in the order of this attempt: fixed by `seed` (the thread, the unit and the attempt), so a resume
    and a rerun of the attempt agree, and another attempt may order them differently (CNL-B9)."""
    return sorted(names, key=lambda n: hashlib.sha256(f"{seed}/{n}".encode()).hexdigest())


def label_map(names: Sequence[str], seed: str) -> dict[str, str]:
    """Member name -> `Member A`, `Member B`, ... in the attempt's order."""
    return {name: f"Member {chr(65 + i)}" for i, name in enumerate(order_of(names, seed))}


# ---------------------------------------------------------------------------------------------
# What a member is told


def _block_help(mode: str, options: Sequence[str], round: int, ranking: bool = False) -> str:
    fields: dict[str, Any] = {"position": "<your answer in one line>"}
    notes = ["`position`: your answer in one line"]
    if mode == "vote":
        fields["choice"] = "<one of: " + ", ".join([*options, ABSTAIN]) + ">"
        notes.append("`choice`: exactly one of " + ", ".join(f"`{o}`" for o in [*options, ABSTAIN]))
    if ranking:
        fields["ranking"] = ["<label>", "<label>"]
        notes.append("`ranking`: every other member's label, best first; never your own")
    fields["confidence"] = 0.7
    notes.append("`confidence`: a number from 0 to 1")
    if round >= 1:
        fields.update(changed=True, why_changed="<why your position moved, or why it held>", dissent="<where you still disagree>")
        notes.append("`changed`: true when your position moved; `why_changed`: the reason; `dissent`: where you still "
                     "disagree with the others, empty only if you do not")
    return ("End your answer with one fenced JSON block, and nothing after it:\n```json\n" + json.dumps(fields, indent=2)
            + "\n```\n" + "\n".join(f"- {n}" for n in notes))


def member_prompt(*, question: str, stance: str, round: int, mode: str, options: Sequence[str] = (),
                  peers: Sequence[tuple[str, str]] = (), anonymize: bool = True, own_previous: str = "") -> str:
    """CNL-B1, CNL-B2. Round 0 holds the question and the member's own stance and nothing of another member. A later round
    adds the others' previous answers, each under its label (or its name when `anonymize` is false), the member's own
    omitted, and requires `changed`, `why_changed` and `dissent`."""
    parts = [question.strip()]
    if stance.strip():
        parts.append(f"Your stance: {stance.strip()}")
    if round >= 1:
        if own_previous.strip():
            parts.append("Your previous answer:\n" + own_previous.strip())
        shown = "\n\n".join(f"{who} answered:\n{text.strip()}" for who, text in peers)
        parts.append("The other members answered in the last round" + (" (anonymized)" if anonymize else "") + ":\n\n"
                     + (shown or "(no other answer arrived)")
                     + "\n\nWeigh their answers. Keep your position or change it, and say which and why.")
    parts.append(_block_help(mode, options, round))
    return "\n\n".join(parts)


def ranking_prompt(*, question: str, peers: Sequence[tuple[str, str]], own_previous: str = "") -> str:
    """The ranking pass of a `rank` council: each member ranks the others' final answers."""
    shown = "\n\n".join(f"{who} answered:\n{text.strip()}" for who, text in peers)
    parts = [question.strip()]
    if own_previous.strip():
        parts.append("Your own final answer:\n" + own_previous.strip())
    parts.append("Rank the other members' final answers, best first:\n\n" + shown)
    parts.append(_block_help("rank", (), 0, ranking=True))
    return "\n\n".join(parts)


def reask_prompt(previous: str, problem: str, *, mode: str, options: Sequence[str], round: int,
                 ranking: bool = False) -> str:
    return (f"Your previous answer could not be read: {problem}. Here is its end:\n\n" + previous[-REASK_TAIL:]
            + "\n\nReply with only the fenced JSON block.\n" + _block_help(mode, options, round, ranking=ranking) + "\n")


def chair_prompt(*, question: str, positions: Sequence[tuple[str, str, str]], mode: str, outcome: str | None,
                 notes: Sequence[str] = (), custom: str = "") -> str:
    """The chair's brief: the question, each member's final answer under its label (position and text), the engine's
    outcome for a `vote` or `rank`, and the judge's notes on a retry. A `synthesize` chair names the dissent."""
    shown = "\n\n".join(f"{label} (position: {pos}):\n{text.strip()}" for label, pos, text in positions)
    parts = [custom.strip() or "You chair this council. Write the answer the members' work supports.", question.strip(),
             "The members' final answers:\n\n" + shown]
    if outcome is not None:
        parts.append(f"The engine tallied the outcome: {outcome}. Write the rationale; do not change the outcome.")
    if notes:
        parts.append("The reviewer did not accept your last answer:\n" + "\n".join(f"- {n}" for n in notes))
    parts.append("State where members still disagree. End with one fenced JSON block holding `dissent`, a text that is "
                 "empty only if the members' positions agree:\n```json\n{\"dissent\": \"<where members differ>\"}\n```")
    return "\n\n".join(parts)


def chair_dissent(text: str) -> str:
    """The `dissent` of a chair's answer block; empty when there is no readable block."""
    blocks = _FENCE.findall(text or "")
    if not blocks:
        return ""
    try:
        data = json.loads(blocks[-1])
    except ValueError:
        return ""
    return str(data.get("dissent") or "").strip() if isinstance(data, dict) else ""


# ---------------------------------------------------------------------------------------------
# What a member answered


@dataclass(frozen=True, kw_only=True)
class Answer:
    status: str  # `ok`, `spoiled` (read twice, never parsed) or `missing` (no session ended)
    text: str = ""
    position: str = ""
    choice: str | None = None
    ranking: tuple[str, ...] = ()
    confidence: float | None = None
    changed: bool | None = None
    why_changed: str = ""
    dissent: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"status": self.status, "text": self.text, "position": self.position, "choice": self.choice,
                "ranking": list(self.ranking), "confidence": self.confidence, "changed": self.changed,
                "why_changed": self.why_changed, "dissent": self.dissent}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Answer:
        return cls(status=str(data.get("status", "missing")), text=str(data.get("text") or ""),
                   position=str(data.get("position") or ""), choice=data.get("choice"),
                   ranking=tuple(str(x) for x in data.get("ranking") or ()), confidence=data.get("confidence"),
                   changed=data.get("changed"), why_changed=str(data.get("why_changed") or ""),
                   dissent=str(data.get("dissent") or ""))


def spoiled(text: str) -> Answer:
    """A second failure to parse: the answer counts against the quorum (CNL-B11)."""
    return Answer(status="spoiled", text=text)


def missing() -> Answer:
    """A member whose session ended on infrastructure: missing for its round (CNL-B15)."""
    return Answer(status="missing")


def parse_answer(text: str, *, mode: str, options: Sequence[str], round: int, peers: Collection[str] = ()) -> Answer:
    """The last fenced JSON block of `text`, read like a judgement block (CNL-B11). In `rank` mode with `peers` the block
    is a ranking pass and must rank every peer label once, never the author's own."""
    blocks = _FENCE.findall(text or "")
    if not blocks:
        raise Unparsed("no fenced JSON block")
    try:
        data = json.loads(blocks[-1])
    except ValueError as exc:
        raise Unparsed("the fenced block is not JSON") from exc
    if not isinstance(data, dict):
        raise Unparsed("the block is not a JSON object")
    position = data.get("position")
    if not isinstance(position, str) or not position.strip():
        raise Unparsed("`position` is missing")
    conf = data.get("confidence")
    if conf is not None and (isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1):
        raise Unparsed("`confidence` is not a number from 0 to 1")
    choice = None
    if mode == "vote":
        choice = data.get("choice")
        if not isinstance(choice, str) or choice not in (*options, ABSTAIN):
            raise Unparsed(f"`choice` is not one of {', '.join([*options, ABSTAIN])}")
    ranking: tuple[str, ...] = ()
    if mode == "rank" and peers:
        raw = data.get("ranking")
        if not isinstance(raw, list) or sorted(map(str, raw)) != sorted(peers) or not all(isinstance(x, str) for x in raw):
            raise Unparsed("`ranking` must list every other member's label once")
        ranking = tuple(raw)
    changed: bool | None = None
    why, dissent = "", ""
    if round >= 1:
        if not isinstance(data.get("changed"), bool) or not isinstance(data.get("why_changed"), str) \
                or not isinstance(data.get("dissent"), str):
            raise Unparsed("`changed`, `why_changed` and `dissent` are required after round 0")
        changed, why, dissent = data["changed"], data["why_changed"], data["dissent"]
    return Answer(status="ok", text=text, position=position.strip(), choice=choice, ranking=ranking,
                  confidence=float(conf) if conf is not None else None, changed=changed, why_changed=why, dissent=dissent)


# ---------------------------------------------------------------------------------------------
# The tally


@dataclass(frozen=True, kw_only=True)
class Tally:
    mode: str
    outcome: str  # an option, a label (`rank`), `synthesized`, or `no_decision`
    rule: str | None
    counts: Mapping[str, int]
    votes: int = 0
    abstained: int = 0
    spoiled: int = 0
    missing: int = 0
    valid: int = 0
    quorum: int = 0
    reason: str | None = None  # why there is no decision: `quorum`, `tie` or `rule`
    ranking: tuple[Mapping[str, Any], ...] = ()


def _census(answers: Mapping[str, Answer], members: int) -> tuple[int, int, int]:
    valid = sum(1 for a in answers.values() if a.status == "ok")
    bad = sum(1 for a in answers.values() if a.status == "spoiled")
    return valid, bad, max(members - valid - bad, 0)


def tally_vote(answers: Mapping[str, Answer], *, options: Sequence[str], rule: str | None, quorum: int | None,
               members: int) -> Tally:
    """CNL-B3: count the final-round `choice`s by `rule`. An abstention is a valid answer for the quorum and no vote;
    a spoiled ballot and a missing member are neither."""
    rule = rule or "majority"
    need = quorum or members
    valid, bad, absent = _census(answers, members)
    counts = {o: 0 for o in options}
    abstained = 0
    for a in answers.values():
        if a.status != "ok":
            continue
        if a.choice == ABSTAIN:
            abstained += 1
        elif a.choice in counts:
            counts[str(a.choice)] += 1
    votes = sum(counts.values())
    base: dict[str, Any] = {"mode": "vote", "rule": rule, "counts": counts, "votes": votes, "abstained": abstained,
                            "spoiled": bad, "missing": absent, "valid": valid, "quorum": need}
    if valid < need:
        return Tally(outcome=NO_DECISION, reason="quorum", **base)
    top = max(counts.values(), default=0)
    leaders = [o for o, n in counts.items() if n == top]
    if votes == 0:
        return Tally(outcome=NO_DECISION, reason="rule", **base)
    if rule == "plurality":
        passed = len(leaders) == 1
    elif rule == "unanimous":
        passed = len(leaders) == 1 and top == votes
    elif rule == "supermajority":
        passed = len(leaders) == 1 and top * 3 >= votes * 2
    else:
        passed = len(leaders) == 1 and top * 2 > votes
    if passed:
        return Tally(outcome=leaders[0], reason=None, **base)
    return Tally(outcome=NO_DECISION, reason="tie" if len(leaders) > 1 else "rule", **base)


def _mean(values: Sequence[float | None]) -> float:
    got = [v for v in values if v is not None]
    return sum(got) / len(got) if got else 0.0


def borda(answers: Mapping[str, Answer], *, labels: Mapping[str, str], confidences: Mapping[str, float | None],
          quorum: int | None) -> Tally:
    """CNL-B12: a Borda count over the peer rankings, k-1 points for the first of k. Ties in points break by the mean
    confidence of the member, then the order of the labels; a tie that both breaks leave at the top is no decision."""
    need = quorum or len(labels)
    valid, bad, absent = _census(answers, len(labels))
    points = {lab: 0 for lab in labels.values()}
    for a in answers.values():
        if a.status != "ok":
            continue
        k = len(a.ranking)
        for place, lab in enumerate(a.ranking):
            if lab in points:
                points[lab] += k - 1 - place
    conf = {labels[n]: _mean([confidences.get(n)]) for n in labels}
    ordered = sorted(points, key=lambda lab: (-points[lab], -conf[lab], lab))
    rows = tuple({"label": lab, "points": points[lab], "mean_confidence": round(conf[lab], 4)} for lab in ordered)
    base: dict[str, Any] = {"mode": "rank", "rule": "borda", "counts": dict(points), "spoiled": bad, "missing": absent,
                            "valid": valid, "quorum": need, "votes": valid}
    if valid < need:
        return Tally(outcome=NO_DECISION, reason="quorum", ranking=tuple(
            {"label": lab, "points": points[lab], "mean_confidence": round(conf[lab], 4)} for lab in sorted(points)), **base)
    if len(ordered) > 1 and (points[ordered[0]], conf[ordered[0]]) == (points[ordered[1]], conf[ordered[1]]):
        return Tally(outcome=NO_DECISION, reason="tie", ranking=tuple(
            {"label": lab, "points": points[lab], "mean_confidence": round(conf[lab], 4)} for lab in sorted(points)), **base)
    return Tally(outcome=ordered[0] if ordered else NO_DECISION, ranking=rows, **base)


def synthesis_tally(answers: Mapping[str, Answer], *, quorum: int | None, members: int) -> Tally:
    """CNL-B12: a `synthesize` council's outcome is the chair's answer, once the round met its quorum."""
    need = quorum or members
    valid, bad, absent = _census(answers, members)
    base: dict[str, Any] = {"mode": "synthesize", "rule": None, "counts": {}, "spoiled": bad, "missing": absent,
                            "valid": valid, "quorum": need}
    if valid < need:
        return Tally(outcome=NO_DECISION, reason="quorum", **base)
    return Tally(outcome=SYNTHESIZED, **base)


def changed_count(answers: Mapping[str, Answer]) -> int:
    """How many members changed position in a round (CNL-B12)."""
    return sum(1 for a in answers.values() if a.status == "ok" and a.changed)


def round_counts(answers: Mapping[str, Answer], members: Sequence[str]) -> dict[str, int]:
    """The counts one `council_round` record and the run detail show (EVT-B13, RDD-B9)."""
    got = [answers.get(m, missing()) for m in members]
    return {"answered": sum(1 for a in got if a.status == "ok"), "spoiled": sum(1 for a in got if a.status == "spoiled"),
            "missing": sum(1 for a in got if a.status == "missing"), "changed": changed_count(answers)}


def positions_differ(answers: Mapping[str, Answer]) -> bool:
    """Whether any member's final position differs from another's (CNL-B12)."""
    return len({a.position.strip().lower() for a in answers.values() if a.status == "ok"}) > 1


# ---------------------------------------------------------------------------------------------
# The three artifacts (CNL-B10)


def decision_text(mode: str, tally: Tally, chair_text: str | None) -> str:
    """The chair's answer, or for a chairless `vote` or `rank` the outcome the engine wrote."""
    if chair_text:
        return chair_text
    if mode == "vote":
        counts = ", ".join(f"{o} {n}" for o, n in tally.counts.items())
        return f"Outcome: {tally.outcome}\nRule: {tally.rule}\nVotes: {counts}; abstained {tally.abstained}"
    if mode == "rank":
        rows = "\n".join(f"{i}. {r['label']} ({r['points']} points)" for i, r in enumerate(tally.ranking, 1))
        return f"Outcome: {tally.outcome}\nRule: borda\n{rows}"
    return f"Outcome: {tally.outcome}"


def positions_json(history: Sequence[Mapping[str, Answer]], labels: Mapping[str, str],
                   ranks: Mapping[str, Answer] | None = None) -> dict[str, Any]:
    """Each member's final answer and its round history, under its label; a `rank` council adds each member's ranking."""
    out: dict[str, Any] = {}
    for name, label in sorted(labels.items(), key=lambda kv: kv[1]):
        rounds = [{"round": r, **history[r].get(name, missing()).to_json()} for r in range(len(history))]
        out[label] = {"rounds": rounds, "final": rounds[-1] if rounds else missing().to_json()}
        if ranks and name in ranks and ranks[name].status == "ok":
            out[label]["ranking"] = list(ranks[name].ranking)
    return out


def tally_json(t: Tally) -> dict[str, Any]:
    return {"mode": t.mode, "outcome": t.outcome, "rule": t.rule, "counts": dict(t.counts), "votes": t.votes,
            "abstained": t.abstained, "spoiled": t.spoiled, "missing": t.missing, "valid": t.valid, "quorum": t.quorum,
            "reason": t.reason, "ranking": [dict(r) for r in t.ranking]}
