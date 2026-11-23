"""`audit prompts <workflow>`: one row per model-facing file (PRA-B11). The `changed` column reads the recorded prompt
digests of the unit and role that use the file from the history facts: the number of changes, the version of the last
one and the gate's first-pass yield before and after it; `not recorded` when no run recorded a digest for it, never
zero (CON-B14, CON-B1, CON-B15)."""

from __future__ import annotations

from typing import Any

from tempergraph.audit.history import HistoryFacts
from tempergraph.audit.report import AuditReport
from tempergraph.contracts import TextRef, WorkflowSpec
from tempergraph.model.prompt_lint import names as read_names
from tempergraph.model.text import TextUnreadable, load_text


def _files(spec: WorkflowSpec) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}

    def add(file: str, unit: str | None, role: str, text: str) -> None:
        row = rows.setdefault(file, {"file": file, "used_by": [], "text": text})
        if unit is not None:
            row["used_by"].append(f"{unit}:{role}")

    for unit in spec.order:
        u = spec.units.get(unit)
        if u is None:
            continue
        st = u.step
        if st is not None and st.prompt != "default":
            file = st.prompt.path if isinstance(st.prompt, TextRef) else f"inline:{unit}"
            try:
                add(file, unit, "step", load_text(spec, st.prompt))
            except TextUnreadable:
                add(file, unit, "step", "")
        j = u.gate.judge
        if j is not None:
            if j.file and spec.package_root is not None:
                try:
                    add(j.file, unit, "judge", load_text(spec, TextRef(path=j.file)))
                except TextUnreadable:
                    add(j.file, unit, "judge", "")
            else:
                add(f"inline:{unit}:judge", unit, "judge", f"{j.stance}\n{j.brief}")
    root = spec.package_root
    if root is not None:
        for p in sorted([*root.glob("skills/*/SKILL.md"), *root.glob("agents/*.md")]):
            add(p.relative_to(root).as_posix(), None, "", p.read_text(encoding="utf-8"))
    return rows


def _yield(facts: HistoryFacts, unit: str, runs: set[str]) -> float | None:
    visits = [v for v in facts.visits if v.unit == unit and v.run in runs and v.tokens]
    return round(sum(1 for v in visits if v.first_pass) / len(visits), 3) if visits else None


def changed_cell(facts: HistoryFacts | None, used_by: list[str]) -> dict[str, Any] | str:
    """PRA-B11: what history says about a file's changes, `not recorded` without a recorded digest."""
    if facts is None:
        return "not recorded"
    count, recorded = 0, False
    last: tuple[str, str, float | None, float | None] | None = None  # (when, version, yield before, yield after)
    for key in dict.fromkeys(used_by):
        unit, _, role = key.partition(":")
        first: dict[str, tuple[str, str]] = {}  # the digest a run started with
        for ts, run, u, r, digest in sorted(facts.digests):
            if u == unit and r == role:
                first.setdefault(run, (ts, digest))
        seq = sorted((ts, run, digest) for run, (ts, digest) in first.items())
        recorded = recorded or bool(seq)
        for i in range(1, len(seq)):
            if seq[i][2] == seq[i - 1][2]:
                continue
            count += 1
            ts, run, _ = seq[i]
            if last is None or ts >= last[0]:
                version = next((v.version for v in facts.visits if v.run == run), "")
                last = (ts, version, _yield(facts, unit, {s[1] for s in seq[:i]}),
                        _yield(facts, unit, {s[1] for s in seq[i:]}))
    if not recorded:
        return "not recorded"
    return {"changes": count, "version": (last[1] or None) if last else None,
            "first_pass_before": last[2] if last else None, "first_pass_after": last[3] if last else None}


def prompt_rows(spec: WorkflowSpec, report: AuditReport, facts: HistoryFacts | None = None) -> list[dict[str, Any]]:
    out = []
    for file, row in _files(spec).items():
        text = row.pop("text")
        n = read_names(text)
        found = [f for f in report.findings if f.location.get("file") == file or
                 (file.startswith("inline:") and f.location.get("file") is None and f.unit in
                  {u.split(":")[0] for u in row["used_by"]})]
        unresolved = sum(1 for f in found if f.rule in ("prompt-lint:lint-ref-missing", "ref-resolves-elsewhere"))
        stale = sum(1 for f in found if f.rule == "tool-name-stale")
        counts = {s: sum(1 for f in found if f.severity == s and f.ignored is None)
                  for s in ("error", "warning", "info")}
        out.append({"file": file, "used_by": row["used_by"], "chars": len(text),
                    "names": {"found": len(n.skills) + len(n.agents) + len(n.files) + len(n.tools),
                              "unresolved": unresolved, "stale": stale},
                    "findings": counts, "changed": changed_cell(facts, row["used_by"])})
    return out
