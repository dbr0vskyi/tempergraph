"""The judge prompt, the judgement block and verdict derivation (JDG §2.1, §2.2; CON §2.8; contract C4).

The engine derives the verdict by rule; a verdict the judge writes is ignored. A judging failure never
passes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from tempergraph.contracts import CheckResult, Criterion, CriterionFinding, GateSpec, Judgement, Verdict
from tempergraph.security.scrub import head_tail

REQUEST_LIMIT = 32_000
ACCOUNT_LIMIT = 8_000
REASK_TAIL = 8_000
STATUSES = frozenset({"MET", "PARTIAL", "UNMET", "N/A", "UNVERIFIABLE"})
_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.S)

ENGINE_BRIEF = (
    "You are an independent reviewer. Grade the work below against each numbered criterion. Read the files "
    "yourself with the read-only tools you have; the step's own account is a claim to verify, not a fact. "
    "You cannot change anything. Report one finding per criterion.")
MECHANICAL_SENTENCE = "The deterministic check verified this criterion; take its evidence as given."
OUT_OF_REACH = ("You cannot read {key} with your tools. Report UNVERIFIABLE for criteria that depend on it; "
                "do not accept the step's word for it.")
ANSWER_FORMAT = """## How to answer
End your answer with one fenced JSON block:
```json
{"criteria": [{"n": 1, "id": "<id or null>", "status": "MET|PARTIAL|UNMET|N/A|UNVERIFIABLE",
  "evidence": "<what you saw, with file and line>", "place": "<where>", "fix": "<one line>",
  "defect_in": null, "no_change": false}],
 "gap": false, "confidence": 0.0, "summary": "<one line>"}
```
Confidence: 1.0 you checked every criterion directly; 0.75 most, with small gaps; 0.5 several criteria rest on
indirect evidence; 0.25 you could check little. Set `gap` true when something you needed was out of reach.
Use `defect_in` with an earlier artifact key when the defect is in that earlier output. Use `no_change` when the
step's own output cannot fix it (a missing source, a person's decision, an outside system).
This line is an example and not valid JSON: {criteria: [n: 1, status: MET]}"""


CLAIM_CRITERION_ID = "upstream-claim"


def claim_criterion(target: str, defect: str) -> Criterion:
    """The one criterion a step's upstream claim is judged against (BUD §2.1): MET confirms the claim."""
    return Criterion(
        id=CLAIM_CRITERION_ID, no_change_policy="retry",
        text=(f"The step claims a defect in the output of the earlier unit `{target}` that it cannot work around. "
              f"The claim, to verify and not to trust: {head_tail(defect, 1000)}"),
        check_method=(f"Read the output of `{target}` listed under What to grade. MET only when the defect is there "
                      f"as claimed and the claiming step could not do its work without `{target}` changing its "
                      f"output; UNMET when the defect is absent or the step could have worked around it; "
                      f"UNVERIFIABLE when you cannot read what the claim is about."))


@dataclass(frozen=True, kw_only=True)
class JudgeInputs:
    gate: GateSpec
    stance: str
    brief: str
    request: str
    references: Mapping[str, str] = field(default_factory=dict)  # key -> pointer or value
    subject: Mapping[str, str] = field(default_factory=dict)
    out_of_reach: Sequence[str] = ()
    check: CheckResult | None = None
    step_account: str = ""
    workspace_facts: Mapping[str, Any] = field(default_factory=dict)
    feedback: str = ""
    rulings: Sequence[str] = ()
    previous_blockers: Sequence[Mapping[str, Any]] = ()
    visit_reason: str = ""


def brief_digest(stance: str, brief: str) -> str:
    """FBK §2.1, JCL §2.3 binding field: the judge's stance and brief as the judge reads them."""
    import hashlib

    return hashlib.sha256(json.dumps([stance.strip(), brief.strip()]).encode()).hexdigest()[:16]


def judged(g: Any) -> Any:
    """The gate as its judge sees it (OUT §2.2): without the criteria a person signs or nobody verifies, which
    go to the approval payload or the outcome record. A gate with nothing else keeps its criteria."""
    import dataclasses

    graded = tuple(c for c in g.criteria if c.verified_by not in ("person", "none"))
    return dataclasses.replace(g, criteria=graded) if graded and len(graded) != len(g.criteria) else g


def criteria_digest(criteria: Sequence[Criterion]) -> str:
    """FBK §2.1, JCL §2.1 binding field: the criterion texts, check methods and severities a judge grades."""
    import hashlib

    rows = [[c.id, c.text, c.check_method, c.severity] for c in criteria]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


def _criterion_line(i: int, c: Criterion, check: CheckResult | None) -> str:
    line = f"{i}. [{c.id or '-'}] ({c.severity}) {c.text}"
    if c.check_method:
        line += f"\n   How to check: {c.check_method}"
    scale = (c.verifier or {}).get("scale") if c.verified_by == "judge" else None
    if isinstance(scale, Mapping):  # OUT §2.2.1: what each status means for this criterion
        for word, label in (("met", "MET means"), ("partial", "PARTIAL means"), ("unmet", "UNMET means"),
                            ("evidence", "Cite for MET"), ("n_a", "N/A only when")):
            if scale.get(word):
                line += f"\n   {label}: {scale[word]}"
    found = [f for f in (check.findings if check else []) if c.id and f.criterion == c.id]
    if c.mechanical and found:
        f = found[0]
        line += f"\n   Check finding: {f.status} {f.place} {f.message}".rstrip() + f"\n   {MECHANICAL_SENTENCE}"
    elif found and found[0].status == "n_a":
        line += f"\n   The check found this not applicable: {found[0].message}"
    return line


def render_judge(inp: JudgeInputs) -> str:
    parts = [ENGINE_BRIEF]
    if inp.stance:
        parts.append("## Stance\n" + inp.stance.strip())
    if inp.brief:
        parts.append("## Brief\n" + inp.brief.strip())
    if inp.workspace_facts:
        parts.append("## Workspace facts\n" + "\n".join(f"- {k}: {v}" for k, v in inp.workspace_facts.items()))
    refs = [f"### request\n{head_tail(inp.request, REQUEST_LIMIT)}"]
    refs += [f"### {k}\n{v}" for k, v in inp.references.items()]
    parts.append("## References\n" + "\n\n".join(refs))
    subj = [f"- {k}: {v}" for k, v in inp.subject.items()]
    if inp.check is not None and (inp.check.evidence or inp.check.findings):
        subj.append(f"Check result: {inp.check.result}")
        if inp.check.evidence:
            subj.append("Check evidence:\n" + head_tail(inp.check.evidence, 4000))
        for f in inp.check.findings:
            subj.append(f"- finding {f.status} {f.criterion or ''} {f.place} {f.message} {f.fix}".rstrip())
    if subj:
        parts.append("## What to grade\n" + "\n".join(subj))
    for key in inp.out_of_reach:
        parts.append(OUT_OF_REACH.format(key=key))
    if inp.step_account:
        parts.append("## The step's account (claims to verify, not facts)\n" + head_tail(inp.step_account, ACCOUNT_LIMIT))
    if inp.feedback or inp.rulings:
        fb = ["## Direction from a person (wins over a reference)"]
        fb += [inp.feedback] if inp.feedback else []
        fb += [f"- Ruling: {r}" for r in inp.rulings]
        if inp.rulings:  # one engine blocker per attempt (RRN §2.2, JDG §2.1)
            fb.append("Grade one more blocker, `ruling`: the output follows every ruling above. A blocker you "
                      "cannot fix without breaking a ruling is `no_change`.")
        parts.append("\n".join(fb))
    if inp.previous_blockers:
        parts.append("## Re-check these blockers first, then grade the full rubric\n" + "\n".join(
            f"- {b.get('criterion')}: {b.get('problem', '')}" for b in inp.previous_blockers))
    if inp.visit_reason:
        parts.append("## This unit was sent back\nAn extra blocker: every point of this reason is addressed.\n"
                     + inp.visit_reason)
    parts.append("## Criteria\n" + "\n".join(_criterion_line(i, c, inp.check)
                                              for i, c in enumerate(inp.gate.criteria, 1)))
    parts.append(ANSWER_FORMAT)
    return "\n\n".join(parts) + "\n"


def reask_prompt(first_answer: str, gate: GateSpec) -> str:
    return ("Your previous review ended without a valid judgement block. Here is its end:\n\n"
            + first_answer[-REASK_TAIL:] + "\n\nReply with only the fenced JSON block for these criteria:\n"
            + "\n".join(f"{i}. [{c.id or '-'}] {c.text}" for i, c in enumerate(gate.criteria, 1))
            + "\n\n" + ANSWER_FORMAT + "\n")


class Unparsed(ValueError):
    pass


def parse_judgement(text: str, gate: GateSpec) -> Judgement:
    """The last fenced JSON block; a criterion id must match its number (JDG-B2)."""
    blocks = _FENCE.findall(text or "")
    if not blocks:
        raise Unparsed("no judgement block")
    try:
        data = json.loads(blocks[-1])
    except ValueError as exc:
        raise Unparsed("judgement block is not JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("criteria"), list):
        raise Unparsed("judgement block has no criteria list")
    ids = {i: c.id for i, c in enumerate(gate.criteria, 1)}
    findings = []
    for row in data["criteria"]:
        if not isinstance(row, dict) or not isinstance(row.get("n"), int):
            raise Unparsed("criterion without a number")
        n = row["n"]
        status = str(row.get("status", "")).upper()
        if status not in STATUSES:
            raise Unparsed(f"criterion {n} has status {status!r}")
        rid = row.get("id")
        if rid not in (None, "", "-") and n in ids and ids[n] and rid != ids[n]:
            raise Unparsed(f"criterion {n} id {rid!r} does not match {ids[n]!r}")
        findings.append(CriterionFinding(
            n=n, status=status, id=rid or None, evidence=str(row.get("evidence") or ""),  # type: ignore[arg-type]
            place=str(row.get("place") or ""), fix=str(row.get("fix") or ""),
            defect_in=row.get("defect_in") or None, no_change=bool(row.get("no_change"))))
    conf = data.get("confidence")
    return Judgement(criteria=tuple(findings), gap=bool(data.get("gap")),
                     confidence=float(conf) if isinstance(conf, int | float) else 0.0,
                     summary=str(data.get("summary") or "")[:300],
                     coverage=dict(data["coverage"]) if isinstance(data.get("coverage"), dict) else {})


@dataclass(kw_only=True)
class Outcome:
    verdict: Verdict
    blockers: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    gap: bool = False
    confidence: float = 0.0
    confidence_source: str = "judge"
    back_to: str | None = None
    reason: str = ""
    statuses: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {"verdict": str(self.verdict), "blockers": self.blockers, "notes": self.notes, "gap": self.gap,
                "confidence": self.confidence, "confidence_source": self.confidence_source,
                "back_to": self.back_to, "reason": self.reason, "statuses": self.statuses}


def derive(judgement: Judgement | None, gate: GateSpec, check: CheckResult | None,
           back_units: Mapping[str, str] | None = None) -> Outcome:
    """JDG §2.2. ``back_units``: artifact key -> producing unit, for the allowed back targets on this path."""
    if judgement is None:
        return Outcome(verdict=Verdict.ESCALATE, gap=True, confidence=0.0, confidence_source="engine_placeholder",
                       reason="unparsed")
    by_n = {f.n: f for f in judgement.criteria}
    na_reasons = {f.criterion for f in (check.findings if check else []) if f.status == "n_a" and f.message}
    failing: list[tuple[Criterion, CriterionFinding, str]] = []
    escalate = judgement.gap
    out = Outcome(verdict=Verdict.PROCEED, gap=judgement.gap, confidence=judgement.confidence)
    for i, c in enumerate(gate.criteria, 1):
        f = by_n.get(i)
        status = f.status if f else "UNMET"
        if f and status == "MET" and not f.evidence.strip():
            status = "PARTIAL"
        if f and status == "N/A" and not f.evidence.strip() and c.id not in na_reasons:
            status = "UNMET"
        out.statuses.append({"n": i, "id": c.id, "status": status})
        if status in ("MET", "N/A"):
            continue
        if c.severity != "blocker":
            out.notes.append(f"{c.id or i}: {c.text} ({status})")
            continue
        if status == "UNVERIFIABLE":
            escalate = True
        failing.append((c, f or CriterionFinding(n=i, status="UNMET"), status))
    out.blockers = [{"criterion": c.id or str(f.n), "place": f.place, "problem": f"{status}: {f.evidence}".strip(),
                     "fix": f.fix, **({"no_change": True} if f.no_change else {}),
                     **({"defect_in": f.defect_in} if f.defect_in else {})} for c, f, status in failing]
    if escalate:
        out.verdict, out.reason = Verdict.ESCALATE, "unresolved_gap"
        return out
    if not failing:
        return out
    back_units = back_units or {}
    targets = [back_units.get(f.defect_in or "") for _, f, _ in failing]
    if all(targets):
        out.verdict, out.back_to, out.reason = Verdict.BACK, _earliest(targets, list(back_units.values())), "defect_in"
        return out
    if all(f.no_change and c.no_change_policy == "escalate" for c, f, _ in failing):
        out.verdict, out.reason = Verdict.ESCALATE, "no_change"
        return out
    out.verdict, out.reason = Verdict.RETRY, "blockers"
    return out


def _earliest(targets: list[str | None], order: list[str]) -> str:
    return min((t for t in targets if t), key=lambda t: order.index(t) if t in order else len(order))
