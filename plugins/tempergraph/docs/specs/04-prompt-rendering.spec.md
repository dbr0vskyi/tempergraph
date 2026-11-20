---
title: Prompt rendering and output contract
type: component
status: review
prefix: PRM
adrs: [0005, 0016, 0076, 0077]
---

# Prompt rendering and output contract

## 1. Overview

One renderer builds every step prompt, for every executor, so what a step is told and must emit is identical whether it runs on Claude Code or Antigravity. The step is shown its criteria as the target and never asked to grade itself. Its output is a claim; the judge assesses it and the engine decides (contract C4).

## 2. Contract

```python
def render_step(unit: UnitSpec, state: RunState, attempt: AttemptContext, executor: str) -> RenderedPrompt: ...
class RenderedPrompt: text: str; missing_fields: list[str]; sections: list[str]
```

`executor` selects only the tool names written in the tools block (from that executor's `tool_map`); no other text differs between executors.

### 2.1 Sections, in the order appended

| Section | Present when |
|---|---|
| The step's template, rendered by the grammar of [CON §2.2](01-contracts.spec.md) | Always |
| Item and event sections (item id, index, count; event value cut at 4000 chars) | A mapped item; a delivered event |
| Commands you may run | The step declares command prefixes, or `self_check` |
| Check your work before you end: the `self-check` command and what it reports ([CHK §2.5](75-check-contract-and-command-runs.spec.md)) | The step declares `self_check` |
| Tools for this step | The step declares tools |
| Artifact contract (one line per declared key and its kind) | The step produces keys |
| How this output will be judged (criterion texts only) | The gate has criteria |
| Blocked line, and the upstream line | Blocked always; upstream only when a listed back target has run or a route skipped it on this path ([ADR-0076](../adr/0076-claims-may-target-a-route-skipped-back-target.adr.md)) |
| Notes from the previous judgement | Unmet warnings of the last pass |
| Reason for this visit, and who sent it | The run was sent back to this unit |
| Rejection reason (for a check FAIL, each failing finding's criterion, place and fix, then the evidence); what the previous attempt reported (≤ 3000 chars, head and tail); paths changed since it began (≤ 20) | A retry; after a timeout, infra failure or cut-off only the paths |
| Human feedback | A person gave feedback at the last gate; shown once |

Everything after the template is appended verbatim, never format-processed.

### 2.2 The tools block

Built from the declaration alone: the declared tools by their executor names; stay in the working directory; prefer file tools over the shell when both are declared; run git without a leading change of directory; run only the listed commands; and, when `shell` is not declared, that there is no shell. It never says an undeclared tool is unavailable, because enforcement is opt-in.

### 2.3 Output contract

| Last non-blank line | Meaning |
|---|---|
| `ARTIFACT <key>: <value>` one per declared key | Normal end; a key with no line falls back to the raw output |
| `BLOCKED: <what a person must decide or provide>` | Only a person can unblock; the judge is skipped |
| `UPSTREAM <unit>: <defect>` | A defect in an earlier unit's output this step cannot work around; offered only when that unit is a listed target that has run or that a route skipped on this path |

A claim to a target not listed, or not on this path, is read as blocked. A line `ARTIFACT <key>: <text>` for a `value` key sets that value ([VAL §2.1](76-step-values-and-template-keys.spec.md)).

## 3. Behaviours

**PRM-B1 Same prompt on every executor.** Given a step declaring `read` and `shell`, when it is rendered for each executor, then the prompts differ only in the tool names inside the tools block.

| Executor | Tools block names |
|---|---|
| claude | `Read`, `Bash` |
| agent-sdk | `Read`, `Bash` |
| messages-api | `read_file`, `run_command` |
| antigravity | `view_file`, `run_command` |

**PRM-B2 No self-assessment.** Given a gate with three criteria, when the step prompt is rendered, then it lists the three texts as the target and asks for no status, verdict, confidence or report on them; check methods and severities are not shown.

**PRM-B3 Absent when unused.** Given a step with no tools, no retry and no visit reason, when rendered, then the prompt is the rendered template plus only the sections its declaration requires.

**PRM-B4 Braces in appended text.** Given human feedback containing `{not_a_field}`, when it is appended, then it appears literally and rendering does not fail.

**PRM-B5 Retry told, not resumed.** Given a judged RETRY, when the next attempt is rendered, then it carries the blockers (criterion, place, problem, fix), the previous report labelled a claim, and the changed paths; the session is fresh on its executor.

## 4. Error conditions

| Condition | Result |
|---|---|
| A field without a value at run time | Visible marker, recorded on the step record |
| A template file unreadable at run time | The attempt fails with infra cause `prompt_not_delivered`, outside the retry budget |
| A rendered prompt above the executor's stdin cap (for `messages-api`, the bound model's context window less the tool definitions) | Step fails before launch with a finding; the author must split the step |

## 5. Design notes

- The engine pastes no earlier artifact into a step prompt: judges, checks and routes read artifacts; a step reads what its template names. This keeps context small on every executor.
- Instruction files differ per executor (`CLAUDE.md` against `AGENTS.md` or `GEMINI.md`); the engine adds nothing to them. A workflow that needs the same rules on several executors ships them through its authoring surface ([ADR-0016](../adr/0016-portable-authoring-surface.adr.md)); the `messages-api` executor hosts none (`hosts_authoring_surface = false`), so rules a step needs there go into its template.
- The engine's text names no workflow, step or path, and every sentence is true when tools are not enforced.

## 6. Acceptance criteria

- [ ] PRM-AC-1 Golden tests render every section combination of §2.1 for all four executors.
- [ ] PRM-AC-2 Two renders for different executors differ only inside the tools block.
- [ ] PRM-AC-3 No rendered step prompt contains a check method, a severity or a request for self-grading.
- [ ] PRM-AC-4 Every appended section respects its stated size bound.

## Open questions

None.

## References

