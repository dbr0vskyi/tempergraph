"""`audit prompts <workflow>`: one row per model-facing file (PRA-B11). The `changed` column needs history
(release 2) and reads "not recorded", never zero (CON-B14, CON-B1, CON-B15)."""

from __future__ import annotations

from typing import Any

from tempergraph.audit.report import AuditReport
from tempergraph.contracts import TextRef, WorkflowSpec
from tempergraph.model.prompt_lint import names
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


def prompt_rows(spec: WorkflowSpec, report: AuditReport) -> list[dict[str, Any]]:
    out = []
    for file, row in _files(spec).items():
        text = row.pop("text")
        n = names(text)
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
                    "findings": counts, "changed": "not recorded (history is release 3)"})
    return out
