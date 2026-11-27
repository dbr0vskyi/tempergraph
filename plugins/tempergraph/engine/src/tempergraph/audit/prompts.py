"""`audit prompts <workflow>`: one row per model-facing file (PRA-B11). The `changed` column reads the recorded prompt
digests of the unit and role that use the file from the history facts: the number of changes, the version of the last
one and the gate's first-pass yield before and after it; `not recorded` when no run recorded a digest for it, never
zero (CON-B14, CON-B1, CON-B15)."""

from __future__ import annotations

from typing import Any

from tempergraph.audit.history import HistoryFacts
from tempergraph.audit.report import AuditReport
from tempergraph.audit.text_health import measure, model_facing, named_files, rendered_size, repeated
from tempergraph.contracts import WorkflowSpec
from tempergraph.model.prompt_lint import names as read_names


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


def _criteria_chars(spec: WorkflowSpec, unit: str) -> int:
    u = spec.units.get(unit)
    return sum(len(c.text) for c in u.gate.criteria) if u is not None else 0


def prompt_rows(spec: WorkflowSpec, report: AuditReport, facts: HistoryFacts | None = None,
                repeat_files: int = 3) -> list[dict[str, Any]]:
    """PRA-B11, PRA-B12: one row per model-facing file, its names, findings, history and how its text is built."""
    out = []
    files = model_facing(spec)
    shared: dict[str, int] = {}
    for _, where in repeated(files, repeat_files):
        for f in where:
            shared[f] = shared.get(f, 0) + 1
    for file, tf in files.items():
        text, used_by = tf.text, tf.used_by
        row = {"used_by": used_by}
        n = read_names(text)
        found = [f for f in report.findings if f.location.get("file") == file or
                 (file.startswith("inline:") and f.location.get("file") is None and f.unit in
                  {u.split(":")[0] for u in row["used_by"]})]
        unresolved = sum(1 for f in found if f.rule in ("prompt-lint:lint-ref-missing", "ref-resolves-elsewhere"))
        stale = sum(1 for f in found if f.rule == "tool-name-stale")
        counts = {s: sum(1 for f in found if f.severity == s and f.ignored is None)
                  for s in ("error", "warning", "info")}
        size: dict[str, Any] = {"chars": len(text), "rendered": None, "must_read": None}
        step_unit = next((u.split(":")[0] for u in used_by if u.endswith(":step")), None)
        if step_unit is not None:
            size["rendered"] = rendered_size(spec, step_unit, text)
            named = named_files(text, files)
            size["must_read"] = ((size["rendered"] or len(text) + _criteria_chars(spec, step_unit))
                                 + sum(len(files[f].text) for f in named if f != file))
            size["must_read_files"] = named
        out.append({"file": file, "role": tf.role, "used_by": used_by, "chars": len(text), "size": size,
                    "structure": measure(text).as_json() | {"repeated_sentences": shared.get(file, 0)},
                    "names": {"found": len(n.skills) + len(n.agents) + len(n.files) + len(n.tools),
                              "unresolved": unresolved, "stale": stale},
                    "findings": counts, "changed": changed_cell(facts, used_by)})
    return out
