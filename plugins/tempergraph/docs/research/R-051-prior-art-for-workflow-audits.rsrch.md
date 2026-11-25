# R-051 Prior art for auditing workflow definitions

## Problem statement

[R-050](R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) found what the audit must look for. This note asks how comparable tools that audit a pipeline or agent definition are shaped, so the audit's interface follows practice that works instead of inventing one: how they split checks that need only the files from checks that need a remote service, how they keep noise down, how they let a team accept a finding, and what they return to CI. It is short on purpose; it informs [AUD](../specs/workflow-audit.spec.md) and [ADR-0050](../adr/0050-advisory-read-only-audit-verb-in-three-layers.adr.md) to [ADR-0053](../adr/0053-history-findings-need-a-minimum-sample.adr.md).

## Sources consulted

| Source | Type | Where |
|---|---|---|
| zizmor usage documentation | Official docs of a static auditor for GitHub Actions workflows | https://docs.zizmor.sh/usage/ |
| zizmor audit catalog | Official docs | https://docs.zizmor.sh/audits/ |
| Introducing MCP-Scan (2025-04-11) | Vendor post of a scanner for MCP server configurations | https://invariantlabs.ai/blog/introducing-mcp-scan |
| dbt-project-evaluator README | Official README of a rule package that audits a dbt project's DAG | https://github.com/dbt-labs/dbt-project-evaluator |
| Troubleshooter skill | Spec: the engine's read-only diagnostic skill | [SHL-B12](../specs/plugin-shell.spec.md) |
| Workflow model and validation | Spec: what is refused before a run | [WFM](../specs/workflow-model.spec.md) |

The zizmor pages were read in part verbatim and in part through a summary of their later sections; facts from the summarized part are marked `supported`.

## Key findings

| # | Finding | Confidence |
|---|---|---|
| P1 | zizmor runs **offline** by default and **online** when a token is given; some audits (impostor commits, known-vulnerable actions, ref confusion, stale refs) are online-only and each audit's page says whether it works offline. A switch runs online collection without the online audits. | supported (docs) |
| P2 | zizmor keeps noise down with **personas**: `regular` (default, "high-signal, low-noise"), `pedantic` (adds code smells), `auditor` (everything, including likely false positives). Each finding carries a **severity** and a **confidence**, with `--min-severity` and `--min-confidence` filters. | supported (docs) |
| P3 | zizmor outputs plain text, JSON, **SARIF** and GitHub annotations. Its exit code reports the highest finding's severity (11 to 14) and can be switched off; SARIF output does not use those codes. | supported (docs) |
| P4 | zizmor findings are accepted by an **inline ignore comment** naming the rule, with an optional explanation, or by a config file listing locations; a switch disables every ignore. | supported (docs, partly from summary) |
| P5 | Some zizmor audits are **configurable** (allow and deny lists, policies), and a few offer automatic fixes that edit files in place. | supported (docs) |
| P6 | MCP-Scan checks MCP **tool descriptions** for poisoning and prompt injection, detects **changes after approval** ("rug pulls") by hashing tool descriptions, and looks for **cross-server references** where one server's description shadows another's tool. It connects to servers only when run and sends descriptions to a remote service. | supported (vendor post) |
| P7 | dbt-project-evaluator groups its rules by area: modeling, testing, documentation, structure, performance, governance. Exceptions and thresholds are documented on its rules pages, which were not read. | supported (README); exceptions `uncertain` |
| P8 | The engine's own troubleshooter is read-only by contract and enforced by narrow command rules; the symptom picks one reference to read; it ranks hypotheses with evidence for and against and names reads it could not run. | supported (spec) |
| P9 | The engine's validation refuses before spend and is the same function for the catalog, start, resume, pre-start check and upgrade check. | supported (spec) |

## Conclusions

1. **Split by what a check needs, and say so per rule.** zizmor's offline and online split (P1) maps onto the definition layer and the host and history layers of R-050. Each audit rule declares which layer it needs, and a missing layer is reported as skipped, never as clean.
2. **Default to a quiet view.** A default that shows only high-confidence findings at warning or above, with a switch for everything (P2), answers R-050 N1.
3. **Every finding has a stable rule id, a severity and a confidence** (P2), so CI and people can filter, and a later change of wording does not break an ignore.
4. **Accepting a finding needs a reason and stays visible** (P4): a listed ignore with a reason, counted in the summary, and a switch that shows ignored findings again.
5. **Offer machine output CI already reads** (P3): JSON with a schema version and SARIF. The exit code is opt-in (`--fail-on`), since an advisory tool that fails every pipeline is turned off.
6. **No automatic fixes** in the first release (P5). The improvement loop already owns changing a workflow under measurement ([SIL](../specs/self-improvement.spec.md), [PRP](../specs/improvement-proposals.spec.md)), and a fix that widens a tool grant needs a person.
7. **Tool sets drift.** MCP-Scan's pinning (P6) suggests recording the set of tool names an executor exposes when a workflow is stamped, and reporting a change. tempergraph sees tool names, not descriptions, and sends nothing to a remote service, so it pins names only.
8. **Keep the troubleshooter's discipline** (P8): read-only, evidence with each finding, and name what could not be read.

## Open questions

| Question | Owner |
|---|---|
| Should a later release pin MCP tool descriptions too, as MCP-Scan does, given that the engine would have to start each server to read them? | Owner |
| Is SARIF worth its upkeep for a workflow package, whose "locations" are spec fields and prompt files rather than source lines? | First CI user |

## References

[R-050](R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) · [AUD](../specs/workflow-audit.spec.md)
