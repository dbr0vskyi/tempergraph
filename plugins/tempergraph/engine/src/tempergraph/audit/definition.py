"""The `definition` layer (AUD §1): rules that read the workflow package only (ARC §2.3 to §2.8, PRA §2.3).
Pure over the spec and the package files; no host, no history, no model (contract C13)."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from tempergraph.audit.catalog import PARAMS, rule
from tempergraph.audit.report import AuditFinding
from tempergraph.contracts import Criterion, JudgeSpec, TextRef, UnitSpec, WorkflowSpec
from tempergraph.model.prompt_lint import TICKED
from tempergraph.model.text import TextUnreadable, load_text

P = {k: v.default for k, v in PARAMS.items()}
FACT_CRITERION = re.compile(
    r"\b(file|folder|directory|path)\b[^.]{0,60}\b(exists?|is present|is created)\b|\b(exists?)\b[^.]{0,30}\b(file|"
    r"folder|directory)\b|\b(command|tests?|build|lint|type check)\b[^.]{0,40}\b(pass(es)?|succeeds?|exits? (0|zero)|"
    r"returns? 0)\b|\b(git|commit|branch|tag|pushed|merged)\b[^.]{0,40}\b(exists?|is clean|has|contains|points)\b",
    re.I)
FORBIDS = {  # PRA prompt-tool-conflict: text that forbids a declared capability
    "shell": re.compile(r"\b(do not|don't|never|must not)\s+(run|use|execute)\s+(any\s+)?(commands?|the shell|bash|"
                        r"a terminal|the terminal|scripts?)\b", re.I),
    "edit": re.compile(r"\b(do not|don't|never|must not)\s+(edit|modify|change)\s+(any\s+)?(files?|the code)\b", re.I),
    "write": re.compile(r"\b(do not|don't|never|must not)\s+(write|create)\s+(any\s+)?(new\s+)?files?\b", re.I),
    "web_fetch": re.compile(r"\b(do not|don't|never|must not)\s+(fetch|browse|open)\s+(any\s+)?(web ?pages?|urls?|"
                            r"the web)\b", re.I),
    "web_search": re.compile(r"\b(do not|don't|never|must not)\s+search\s+the web\b", re.I),
}
WHOLE = re.compile(r"\b(write|produce|draft|generate)\s+(the\s+)?(whole|entire|complete|full)\b|\bcomplete (plan|"
                   r"document|spec|report)\b|\bin (one|a single) (answer|response|go)\b", re.I)
IN_PARTS = re.compile(r"\b(in parts|part by part|section by section|one (part|section) at a time|skeleton|"
                      r"outline first|one edit per)\b", re.I)
STANDARD_FRONTMATTER = frozenset({"name", "description", "license", "compatibility", "metadata", "allowed-tools"})
SMALL = {"small", "haiku"}
LARGE = {"large", "opus"}

Add = Callable[..., None]


class Definition:
    def __init__(self, spec: WorkflowSpec, decl_file: str, surfaces: dict[str, Any]) -> None:
        self.spec = spec
        self.decl = decl_file  # the package file that declares the units, for locations
        self.surfaces = surfaces
        self.found: list[AuditFinding] = []

    def add(self, rule_id: str, unit: str | None, statement: str, *, item: str | None = None,
            session: str | None = None, evidence: dict[str, Any] | None = None, field: str | None = None,
            file: str | None = None, line: int | None = None) -> None:
        r = rule(rule_id)
        loc: dict[str, Any] = {"file": file or self.decl}
        if field:
            loc["field"] = field
        if line:
            loc["line"] = line
        self.found.append(AuditFinding(rule=r.id, layer=r.layer, severity=r.severity, confidence=r.confidence,
                                       cause=r.cause, unit=unit, item=item, session=session, statement=statement,
                                       evidence=evidence or {}, remedy=r.remedy, location=loc))

    # -- helpers ------------------------------------------------------------------------------------
    def units(self) -> Iterator[tuple[str, UnitSpec]]:
        for name in self.spec.order:
            u = self.spec.units.get(name)
            if u is not None:
                yield name, u

    def template(self, u: UnitSpec) -> tuple[str, str] | None:
        st = u.step
        if st is None or st.prompt == "default":
            return None
        where = st.prompt.path if isinstance(st.prompt, TextRef) else ""
        try:
            return where, load_text(self.spec, st.prompt)
        except TextUnreadable:
            return None

    @staticmethod
    def gated(u: UnitSpec) -> bool:
        return u.gate.check is not None or u.gate.judge is not None

    @staticmethod
    def cid(c: Criterion) -> str:
        return c.id or c.text[:40]

    # -- C1 ---------------------------------------------------------------------------------------------
    def c1(self) -> None:
        for name, u in self.units():
            crit = u.gate.criteria
            blockers = [c for c in crit if c.severity == "blocker"]
            files = [k for k, v in (u.step.produces if u.step else {}).items() if v == "file"]
            tpl = self.template(u)
            size = len(tpl[1]) if tpl else 0
            why = []
            if len(blockers) > P["oversized_blockers"]:
                why.append(f"{len(blockers)} blocker criteria (over {int(P['oversized_blockers'])})")
            if len(files) > P["oversized_file_artifacts"]:
                why.append(f"{len(files)} file artifacts (over {int(P['oversized_file_artifacts'])})")
            if size > P["oversized_template_chars"]:
                why.append(f"a {size}-character template (over {int(P['oversized_template_chars'])})")
            if why:
                self.add("oversized-step", name, f"{name} does too much for one gate: " + "; ".join(why),
                         evidence={"blockers": len(blockers), "file_artifacts": len(files), "template_chars": size})
            for c in blockers:
                if c.no_change_policy == "retry":
                    self.add("no-change-blocker-retries", name, f"blocker {self.cid(c)!r} retries on no change",
                             item=self.cid(c), field=f"units.{name}.gate.criteria[{self.cid(c)}].no_change_policy")
                if c.unverified_system:
                    self.add("unverified-blocker", name, f"blocker {self.cid(c)!r} names unverified system "
                             f"{c.unverified_system!r}, so it is always UNVERIFIABLE", item=self.cid(c),
                             evidence={"system": c.unverified_system})
            if u.gate.check is None:
                for c in crit:
                    if not c.mechanical and c.verified_by in (None, "judge") and FACT_CRITERION.search(c.text):
                        self.add("single-criterion-gate-judge-only", name, f"criterion {self.cid(c)!r} names a "
                                 "fact a check could compute, and the gate has no check", item=self.cid(c))

    # -- C3 ---------------------------------------------------------------------------------------------
    def c3(self) -> None:
        total_s = 0.0
        tries = P["infra_tries"]
        for name, u in self.units():
            t: float | None = None
            if u.step is not None and u.kind == "step":
                st = u.step
                t = float(st.timeout_s or P["engine_step_timeout_s"])
                if st.timeout_s is None:
                    self.add("default-step-timeout", name, f"{name} sets no timeout_s, so the engine's "
                             f"{int(P['engine_step_timeout_s'])} s applies", session="step",
                             field=f"units.{name}.step.timeout_s")
                if st.idle_s is not None and st.idle_s >= t:
                    self.add("idle-limit-inert", name, f"idle_s {st.idle_s} is not below the wall limit {int(t)} s",
                             session="step", evidence={"idle_s": st.idle_s, "timeout_s": int(t)},
                             field=f"units.{name}.step.idle_s")
                if t > P["no_idle_above_s"] and st.idle_s is None:
                    self.add("no-idle-limit", name, f"a {int(t)} s limit with no idle limit", session="step",
                             field=f"units.{name}.step.idle_s")
            elif u.script is not None:
                t = float(u.script.timeout_s)
            j = u.gate.judge
            if j is not None and j.timeout_s is None:
                self.add("default-judge-timeout", name, f"the judge of {name} sets no timeout_s", session="judge",
                         field=f"units.{name}.gate.judge.timeout_s")
            if t is None:
                continue
            attempts = u.gate.retry_budget + 1 if self.gated(u) else 1
            hold = t * attempts + t * tries
            total_s += hold
            if hold > P["unit_hold_h"] * 3600:
                self.add("hold-time-exposure", name, f"{name} can hold the run for {hold / 3600:g} h "
                         f"({int(t)} s x {attempts} attempts + {int(t)} s x {int(tries)} infra tries)",
                         evidence={"timeout_s": int(t), "retry_budget": u.gate.retry_budget,
                                   "infra_tries": int(tries), "hold_h": round(hold / 3600, 2)})
        if total_s > P["workflow_hold_h"] * 3600:
            self.add("hold-time-exposure", None, f"the units in order can hold a run for {total_s / 3600:g} h "
                     f"(over {int(P['workflow_hold_h'])} h)", item="order",
                     evidence={"hold_h": round(total_s / 3600, 2)})

    # -- C5 ---------------------------------------------------------------------------------------------
    def c5(self) -> None:
        gates = [(n, u) for n, u in self.units() if self.gated(u) or u.gate.approval]
        for name, u in gates:
            if self.gated(u) and u.gate.retry_budget == 0 and u.gate.on_budget_spent == "ask":
                self.add("every-retry-asks", name, f"{name} has retry_budget 0 and on_budget_spent ask, so every "
                         "RETRY pauses for a person", field=f"units.{name}.gate.retry_budget")
        approvals = [n for n, u in gates if u.gate.approval]
        if gates and len(approvals) > P["approval_share"] * len(gates):
            self.add("approval-on-most-gates", None, f"approval is set on {len(approvals)} of {len(gates)} gates",
                     evidence={"approvals": len(approvals), "gates": len(gates), "units": approvals})

    # -- C6 ---------------------------------------------------------------------------------------------
    @staticmethod
    def _tier(model: object) -> str:
        if model is None:
            return ""
        first = model if isinstance(model, str) else (list(model)[0] if model else "")  # type: ignore[call-overload]
        return str(first).rsplit(":", 1)[-1].lower()

    def c6(self) -> None:
        tiers: list[str] = []
        for name, u in self.units():
            j: JudgeSpec | None = u.gate.judge
            if u.step is not None:
                tiers.append(self._tier(u.step.model or self.spec.model_profile.get(name)))
            if j is not None:
                tiers.append(self._tier(j.model))
                spans = len(j.references) + len(j.subject)
                if self._tier(j.model) in SMALL and spans > 1:
                    self.add("small-judge-cross-file", name, f"the judge of {name} is on a small model and reads "
                             f"{spans} artifacts", session="judge", evidence={"artifacts": spans, "model": j.model},
                             field=f"units.{name}.gate.judge.model")
        if tiers and all(t in LARGE for t in tiers):
            self.add("large-everywhere", None, "every step and judge resolves to the large tier",
                     evidence={"sessions": len(tiers)})
        if self.spec.run_cost_cap_usd is None and self.spec.improvement_mode == "stable":
            self.add("no-run-cost-cap", None, "a stable workflow with no run_cost_cap_usd", field="run_cost_cap_usd")

    # -- PRA definition rules --------------------------------------------------------------------------
    def prompts(self) -> None:
        root = self.spec.package_root
        produced_by: dict[str, str] = {}
        for name, u in self.units():
            for key in (u.step.produces if u.step else {}):
                produced_by.setdefault(key, name)
        for name, u in self.units():
            st = u.step
            tpl = self.template(u)
            if st is not None and tpl is not None:
                where, text = tpl
                file = where or self.decl
                for cap, pat in FORBIDS.items():
                    if cap in st.tools and (m := pat.search(text)):
                        self.add("prompt-tool-conflict", name, f"the template says {m.group(0)!r} but the step "
                                 f"declares {cap!r}", session="step", item=cap, file=file,
                                 line=text.count("\n", 0, m.start()) + 1)
                for key in st.produces:
                    if key not in text:
                        self.add("artifact-not-asked", name, f"produced artifact {key!r} is never named in the "
                                 "template", session="step", item=key, file=file)
                files = [k for k, v in st.produces.items() if v == "file"]
                if len(files) == 1 and (m := WHOLE.search(text)) and not IN_PARTS.search(text):
                    self.add("one-shot-long-output", name, f"the template asks for {m.group(0)!r} in one answer",
                             session="step", file=file, line=text.count("\n", 0, m.start()) + 1)
            j = u.gate.judge
            if j is not None:
                reach = set(j.references) | set(j.subject) | set(st.produces if st else ())
                for c in u.gate.criteria:
                    for tok in dict.fromkeys(TICKED.findall(c.text)):
                        if tok in produced_by and tok not in reach:
                            self.add("criterion-not-in-reach", name, f"criterion {self.cid(c)!r} names artifact "
                                     f"{tok!r} (made by {produced_by[tok]}), which the judge does not read",
                                     session="judge", item=f"{self.cid(c)}:{tok}")
        self._frontmatter(root)

    def _frontmatter(self, root: Path | None) -> None:
        if root is None:
            return
        executors = {(u.step.executor if u.step else None) or self.spec.default_executor
                     for _, u in self.units()}
        portable = bool(self.surfaces) or any(e not in ("claude", "agent-sdk") for e in executors)
        if not portable:
            return
        for p in sorted((root / "skills").glob("*/SKILL.md")):
            keys = frontmatter_keys(p.read_text(encoding="utf-8"))
            extra = sorted(keys - STANDARD_FRONTMATTER)
            if extra:
                self.add("skill-frontmatter-nonstandard", None, f"{p.parent.name} uses frontmatter beyond the "
                         f"Agent Skills standard: {', '.join(extra)}", item=p.parent.name,
                         file=p.relative_to(root).as_posix(), evidence={"fields": extra})

    # -- outcome (ARC §2.8) --------------------------------------------------------------------------------
    def outcome(self) -> None:
        from tempergraph.run.outcome_trust import coverage, trust

        o = self.spec.outcome
        if o is None:
            return
        rows = [("outcome", c) for c in o.final] + [(u, c) for u, io in o.intermediate.items() for c in io.criteria]
        from tempergraph.improve.calibration import accepted_for

        accepted = accepted_for(self.spec)
        for unit, c in rows:
            t = trust(c, unit, self.spec.package_root, accepted)
            if c.severity == "blocker" and t in ("unverified", "uncalibrated"):
                self.add("outcome-unverified-blocker", unit, f"blocker {self.cid(c)!r} is at {t} trust",
                         item=self.cid(c), file="outcome.json", evidence={"trust": t, "verified_by": c.verified_by})
        for cov in coverage(o, self.spec):
            if not cov.covered:
                self.add("outcome-uncovered", "outcome", f"final criterion {cov.criterion!r} is not covered: "
                         f"{cov.trust} at the outcome gate, no trusted serving criterion on "
                         f"{', '.join(cov.missing_units) or 'any unit'}", item=cov.criterion, file="outcome.json",
                         evidence={"trust": cov.trust, "missing_units": cov.missing_units})

    def run(self) -> list[AuditFinding]:
        for part in (self.c1, self.c3, self.c5, self.c6, self.prompts, self.outcome):
            part()
        return self.found


def frontmatter_keys(text: str) -> set[str]:
    if not text.startswith("---"):
        return set()
    end = text.find("\n---", 3)
    if end < 0:
        return set()
    return {m.group(1) for m in re.finditer(r"^([A-Za-z0-9_-]+)\s*:", text[3:end], re.M)}
