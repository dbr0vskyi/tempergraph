# ADR-0080 A person may grant a step tools, commands or judge read views for a run, by a recorded flag

| | |
|---|---|
| Status | proposed |
| Date | 2026-11-20 |
| Authors | Claude (design session for the owner) |
| Supersedes | — |

## Context

The owner asked what happens when a run fails or pauses because a step cannot reach a tool, a skill, an MCP server or a command. Tool access is a common cause of a stopped run: a refused call is an undeclared tool, a needed command, or a call that had a permitted form ([R-050](../research/R-050-why-runs-fail-stall-repeat-or-overspend.rsrch.md) C4, [TSA-B7](../specs/tool-surface-audit.spec.md)). Fixed by hand, such a run needs a person to add a rule and copy settings. Before this record, declared tools were not a setting ([ADR-0071](0071-overrides-never-change-what-verifies-the-work.adr.md)), so the only remedy was to edit the package and start again. A refused call also spent a retry: a new attempt hits the same refusal.

## Decision

We will let a person widen a run's tools with the settings keys `tools.add`, `commands.add` and, for a judge, `views.add`, spelled `--grant` and `--allow-command` on `run`, `resume` and `rerun` ([RST-B28, RST-B29, RST-B30](../specs/run-settings-and-overrides.spec.md)). A grant passes every check a declaration passes. It comes only from flags or the workflow's own profiles, never from a settings file or an agent caller. It is recorded as widening and kept on the thread. A judge, a council member and the chair may only gain read-only views from the catalog. A failed or blocked attempt that met a denial or a missing declared tool escalates with cause `tool_access`, spends no retry, and its pause payload offers the exact grant. Every grant is tracked in the run log, the intervention row and the ledger, with whether it was used; a used grant is a `grant_missing` finding the improvement loop clusters across runs and machines and answers with a `tools` proposal that declares it, and the audit reports a grant used on two runs, so the declaration is fixed in the package.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Recorded per-run grants by a person (chosen) | A blocked run continues in minutes; the workflow owner learns from the record | One more widening path to guard |
| Edit the package and start again | Declarations stay the only source | A run paused for days on one MCP tool is lost; every earlier unit runs again |
| Grants in settings files too | Set once per machine | Widens every run unseen; the audit's definition layer would no longer describe what runs get |
| Let the agent widen its own tools | No person needed | Breaks enforcement and the judge's independence |

## Decision rationale

| Criterion | Per-run grant | Edit package | File grants | Agent widens |
|---|---|---|---|---|
| A paused run continues | yes | no | yes | yes |
| A person decides each widening | yes | yes | once, then never | no |
| Judge stays write-free and independent | yes | yes | yes | no |
| The package converges on what runs need | yes, via the audit | yes | no | no |

## Assumptions

| # | Assumption | Where it matters |
|---|---|---|
| A1 | A grant widens a step's reach, not what verifies the step: the gate, the criteria and the judge are unchanged, so ADR-0071's promise holds. | RST |
| A2 | A denial in a failed attempt is the likeliest cause of the failure, so escalating is better than spending a retry that meets the same refusal. A denial in a passing attempt is only recorded. | BUD-B1, BUD-B11 |

## Consequences

- Positive: "the step needs the tracker tool" is one resume command, offered in the pause payload.
- Negative: ADR-0071's list gains an exception; RST gains a section of rules.
- Risk: grants become a habit instead of a declaration. Mitigation: the `granted-at-run` audit finding and an improvement proposal.
