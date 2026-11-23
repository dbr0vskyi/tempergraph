"""`AuditFinding` and `AuditReport` (AUD (moved), AUD-B12, AUD-B13, AUD-B14): ordering, the quiet default view,
ignores, the summary, `--fail-on`, and the text, JSON and SARIF forms."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from tempergraph.audit.catalog import BY_ID, CONFIDENCE_RANK, SEVERITY_RANK, known
from tempergraph.constants import SCHEMA

SARIF_LEVEL = {"error": "error", "warning": "warning", "info": "note"}


@dataclass(kw_only=True)
class AuditFinding:
    rule: str  # catalog id, or `validate:<code>` and `<owner>:<code>` for owned rules
    layer: str
    severity: str
    confidence: str
    cause: str = ""
    unit: str | None = None
    item: str | None = None
    session: str | None = None  # `step` or `judge`
    statement: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    remedy: str = ""
    widening: bool = False
    location: dict[str, Any] = field(default_factory=dict)  # {file, field?, line?}
    owner: str = "audit"
    ignored: dict[str, Any] | None = None

    @property
    def key(self) -> tuple[str, str | None, str | None]:
        return self.rule, self.unit, self.item

    def shown(self) -> bool:
        """The default view (AUD-B7, AUD-B12): error or warning, high or medium confidence, not ignored."""
        return (self.ignored is None and self.severity in ("error", "warning")
                and self.confidence in ("high", "medium"))

    def to_json(self) -> dict[str, Any]:
        return {"rule": self.rule, "layer": self.layer, "severity": self.severity, "confidence": self.confidence,
                "cause": self.cause, "unit": self.unit, "item": self.item, "session": self.session,
                "statement": self.statement, "evidence": self.evidence, "remedy": self.remedy,
                "widening": self.widening, "location": self.location, "owner": self.owner,
                "ignored": self.ignored}


@dataclass(frozen=True, kw_only=True)
class Ignore:
    rule: str
    reason: str
    unit: str | None = None
    until: dt.date | None = None

    def lapsed(self, today: dt.date) -> bool:
        return self.until is not None and today > self.until

    def matches(self, f: AuditFinding) -> bool:
        return f.rule == self.rule and (self.unit is None or self.unit == f.unit)


def parse_ignores(raw: Any) -> tuple[list[Ignore], list[str]]:
    """`audit.ignore` of `tempergraph.json` (AUD-B14): the ignores, and the problems that validation
    refuses (AUD-AC7: a missing reason; a bad date or shape)."""
    out: list[Ignore] = []
    problems: list[str] = []
    if raw is None:
        return out, problems
    if not isinstance(raw, list):
        return out, ["audit.ignore must be a list of {rule, unit?, reason, until?}"]
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or not isinstance(item.get("rule"), str) or not item["rule"]:
            problems.append(f"audit.ignore[{i}] needs a rule id")
            continue
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"audit.ignore[{i}] ({item['rule']}) needs a one-sentence reason")
            continue
        until = None
        if item.get("until") is not None:
            try:
                until = dt.date.fromisoformat(str(item["until"]))
            except ValueError:
                problems.append(f"audit.ignore[{i}] until {item['until']!r} is not a date (YYYY-MM-DD)")
                continue
        unit = item.get("unit")
        out.append(Ignore(rule=item["rule"], reason=reason.strip(), unit=str(unit) if unit else None, until=until))
    return out, problems


def apply_ignores(findings: list[AuditFinding], ignores: list[Ignore], today: dt.date) -> list[AuditFinding]:
    """Mark ignored findings; an ignore never hides a validation error; an unknown rule id is itself an
    `info` finding. Returns the extra findings the ignores raise."""
    extra: list[AuditFinding] = []
    for ig in ignores:
        if not known(ig.rule):
            extra.append(AuditFinding(
                rule="ignore-rule-unknown", layer="definition", severity="info", confidence="high",
                statement=f"audit.ignore names rule {ig.rule!r}, which the catalog does not know",
                remedy=BY_ID["ignore-rule-unknown"].remedy, evidence={"rule": ig.rule},
                location={"file": "tempergraph.json", "field": "audit.ignore"}))
            continue
        if ig.lapsed(today):
            continue  # AUD-AC7: a lapsed `until` shows the finding again
        for f in findings:
            if f.ignored is None and ig.matches(f) and not (f.rule.startswith("validate:") and f.severity == "error"):
                f.ignored = {"reason": ig.reason, **({"until": ig.until.isoformat()} if ig.until else {})}
    return extra


def order(findings: list[AuditFinding], unit_order: tuple[str, ...]) -> list[AuditFinding]:
    """Validation errors lead (AUD-B2); then severity, confidence, the rule's rank, unit order (AUD-B12, AUD-B13)."""
    pos = {u: i for i, u in enumerate(unit_order)}

    def key(f: AuditFinding) -> tuple[Any, ...]:
        base = f.rule.partition(":")[2] if ":" in f.rule else f.rule
        rule = BY_ID.get(f.rule) or BY_ID.get(_OWNED_AS.get(f.rule.partition(":")[0], ""), None)
        rank = rule.rank if rule is not None else (9, 999)
        lead = 0 if (f.rule.startswith("validate:") and f.severity == "error") else 1
        return (lead, SEVERITY_RANK.get(f.severity, 3), CONFIDENCE_RANK.get(f.confidence, 3), rank,
                pos.get(f.unit or "", len(pos)), base, f.item or "")

    return sorted(findings, key=key)


# An owned finding sorts at its catalog row.
_OWNED_AS = {"prompt-lint": "prompt-lint", "readiness": "judge-not-ready", "validate": "template-grammar",
             "executor-compat": "executor-outside-tested-range", "cost-lens": "cost-lens-rules",
             "SIL": "engine-fault-open"}


@dataclass(kw_only=True)
class AuditReport:
    workflow: str
    version: str
    engine_version: str
    layers_run: list[str] = field(default_factory=list)
    layers_skipped: list[dict[str, Any]] = field(default_factory=list)
    rules_skipped: list[dict[str, Any]] = field(default_factory=list)
    findings: list[AuditFinding] = field(default_factory=list)
    hot_spots: list[dict[str, Any]] = field(default_factory=list)  # history only: one per unit with findings
    owned: list[dict[str, Any]] = field(default_factory=list)
    runs: int = 0
    unreadable_runs: int = 0  # run logs left out as unreadable (AUD-B12, AUD-B15)
    surface: Any = None  # the session surface the tool rules read, shared with `audit tools`; never serialized
    window_days: int = 30
    show_all: bool = False

    def visible(self) -> list[AuditFinding]:
        return list(self.findings) if self.show_all else [f for f in self.findings if f.shown()]

    def summary(self) -> dict[str, Any]:
        live = [f for f in self.findings if f.ignored is None]
        counts = {s: sum(1 for f in live if f.severity == s) for s in ("error", "warning", "info")}
        shown = [f for f in self.findings if f.shown()]
        return {"shown": len(shown), "by_severity": counts, "info": counts["info"],
                "low_confidence": sum(1 for f in live if f.confidence == "low" and f.severity != "info"),
                "ignored": sum(1 for f in self.findings if f.ignored is not None),
                "rules_skipped": len(self.rules_skipped),
                "highest_weight_cause": (f"{shown[0].rule} on {shown[0].unit or 'the workflow'}: "
                                         f"{shown[0].statement}") if shown else None}

    def exit_code(self, fail_on: str) -> int:
        """AUD-AC5: 6 exactly when a non-ignored finding is at or above the level, else 0."""
        if fail_on == "never":
            return 0
        top = SEVERITY_RANK[fail_on]
        return 6 if any(f.ignored is None and SEVERITY_RANK.get(f.severity, 3) <= top for f in self.findings) else 0

    def to_json(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA["audit_report"], "workflow": self.workflow, "version": self.version,
                "engine_version": self.engine_version, "layers_run": self.layers_run,
                "layers_skipped": self.layers_skipped, "rules_skipped": self.rules_skipped,
                "window_days": self.window_days, "runs": self.runs, "unreadable_runs": self.unreadable_runs,
                "findings": [f.to_json() for f in self.visible()], "hot_spots": self.hot_spots,
                "owned": self.owned, "summary": self.summary()}

    def to_text(self) -> str:
        s = self.summary()
        lines = [f"audit {self.workflow} {self.version} (engine {self.engine_version})",
                 f"layers: {', '.join(self.layers_run) or 'none'}"
                 + "".join(f"; {d['layer']} skipped: {d['reason']}" for d in self.layers_skipped),
                 f"{self.runs} runs read, {self.unreadable_runs} runs unreadable (last {self.window_days} days)", ""]
        for h in self.hot_spots:
            lines.append(f"hot spot {h['unit']}: {h['findings']} findings, leading {h['leading_rule']}")
        if self.hot_spots:
            lines.append("")
        for f in self.visible():
            mark = " [ignored]" if f.ignored else ""
            lines.append(f"{f.rule}  {f.severity}/{f.confidence}  {f.unit or '-'}{mark}")
            lines.append(f"  {f.statement}")
            if f.evidence:
                lines.append("  evidence: " + ", ".join(f"{k}={v}" for k, v in f.evidence.items()))
            if f.remedy:
                lines.append(f"  remedy: {f.remedy}" + (" [widens]" if f.widening else ""))
            if f.location:
                where = f.location.get("file", "")
                if f.location.get("line"):
                    where += f":{f.location['line']}"
                if f.location.get("field"):
                    where += f" ({f.location['field']})"
                lines.append(f"  at: {where}")
            lines.append("")
        for o in self.owned:
            lines.append(f"owned: {o['owner']}: {o['count']} findings")
        lines.append(f"{s['shown']} shown, {s['info']} info, {s['ignored']} ignored, {s['rules_skipped']} rules skipped")
        if s["highest_weight_cause"]:
            lines.append(f"highest-weight cause: {s['highest_weight_cause']}")
        return "\n".join(lines) + "\n"

    def to_sarif(self) -> dict[str, Any]:
        """SARIF 2.1.0: one result per visible finding, at its package file and line where known (AUD-B9)."""
        ids = sorted({f.rule for f in self.visible()})
        rules = []
        for rid in ids:
            r = BY_ID.get(rid)
            rules.append({"id": rid, "shortDescription": {"text": rid},
                          **({"help": {"text": r.remedy}} if r is not None and r.remedy else {})})
        results = []
        for f in self.visible():
            res: dict[str, Any] = {"ruleId": f.rule, "level": SARIF_LEVEL.get(f.severity, "note"),
                                   "message": {"text": f.statement}}
            if f.widening:
                res["properties"] = {"widening": True}
            if f.location.get("file"):
                phys: dict[str, Any] = {"artifactLocation": {"uri": f.location["file"]}}
                if f.location.get("line"):
                    phys["region"] = {"startLine": int(f.location["line"])}
                res["locations"] = [{"physicalLocation": phys}]
            if f.ignored is not None:
                res["suppressions"] = [{"kind": "inSource", "justification": f.ignored["reason"]}]
            results.append(res)
        return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
                "runs": [{"tool": {"driver": {"name": "tempergraph-audit", "version": self.engine_version,
                                              "rules": rules}},
                          "results": results}]}


def render(report: AuditReport, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(report.to_json(), indent=2, ensure_ascii=False) + "\n"
    if fmt == "sarif":
        return json.dumps(report.to_sarif(), indent=2, ensure_ascii=False) + "\n"
    return report.to_text()
