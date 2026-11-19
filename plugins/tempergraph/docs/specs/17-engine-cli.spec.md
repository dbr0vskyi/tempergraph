---
title: Engine CLI
type: component
status: review
prefix: CLI
adrs: [0015, 0021]
---

# Engine CLI

## 1. Overview

The `tempergraph` command line is the engine's public interface for people, skills and CI. Its verbs are plain words; its exit codes are the caller contract ([CON §2.9](01-contracts.spec.md)). Input resolution and every read-only verb call no model and create nothing (contract C13). A shim picks the engine's interpreter and exits 127 if none has the engine.

## 2. Contract

| Verb | Does | Writes | Spends |
|---|---|---|---|
| `run <workflow> <request…> [options]` | Resolve, preflight, start | yes | yes |
| `run --check …` | Resolve and preflight only; prints one status | no | no |
| `resume <workflow> <thread> [--decision …] [--feedback …] [--input k=v]` | Resume per thread state | yes | yes |
| `status [selector] [--detail]` | Status document | no | no |
| `wait <selector> [--timeout s]` | Block until an outcome | no | no |
| `list` | The catalog (versioned JSON or a table) | no | no |
| `graph <workflow> [--format mermaid|svg|md] [--overlay <thread>]` | Diagram from the model | no | no |
| `report [window] [--by unit|executor|version]` | Cost and friction reports | no | no |
| `validate <workflow>` | Validation, view deferrals, prompt-tool check | no | no |
| `audit <workflow> [--layer …] [--target <path>] [--window <days>] [--all] [--format text\|json\|sarif] [--fail-on …]`, `audit tools <workflow>` | Advisory audit of a workflow's definition, host and run history; exit 6 only with `--fail-on` ([AUD](55-workflow-audit.spec.md)) | no | no |
| `executors [--probe]` | Registered executors, capabilities, CLI versions, probe facts | no | no |
| `batch <workflow> <targets…> [-k N]` | Many child runs | yes | yes |
| `worktree list|prune` | Engine worktrees | prune only | no |
| `update [--dry-run]` | Install or upgrade the engine; reconcile the manifest | yes | no |
| `upgrade-check <workflow> [--stamp]` | Compatibility against the changelog | stamp only | no |
| `facts <selector> [--json]` | Read-only facts about a run for other tools (state, branch, artifacts by key, pending gates, cost figures, alias, label, origin) | no | no |
| `stats [--month YYYY-MM] [--json]` | Per-user monthly run rows ([OBS §2.4](15-observability-and-cost.spec.md)) | no | no |
| `hooks add|list|remove|test` | Run lifecycle hooks (§2.2) | add and remove only | no |

### 2.1 Run options that touch executors

| Option | Effect |
|---|---|
| `--executor <name>` / `--step-executor <step>=<name>` | Override the executor for all steps or one |
| `--judge-executor <name>` | Override the judge executor (still must declare `restricts_judge_tools`) |
| `--model <alias>` / `--step-model <step>=<alias>` / `--judge-model <alias>` | Alias overrides on their layers |
| `--timeout`, `--judge-timeout`, `--idle` | Limit overrides |
| `--enforce-tools` | Opt in to hard tool enforcement on executors that declare it |
| `--strict-permissions` | Enforce declared tools on every step and refuse a step whose executor cannot ([EXI-B12](10-executor-interface.spec.md)) |
| `--alias <name>`, `--label <text>` | Run alias and label ([DUR §2.2](09-durability-and-resume.spec.md)) |
| `--arm <switch>=<arm>` | Operator pick of a switch arm ([CMP](03-compiler-and-flow.spec.md)) |
| `--run-cost-cap <usd>` | Overrides `run_cost_cap_usd` for this run ([BUD](08-budgets-and-failures.spec.md)) |
| `--audit-rate <0..1>`, `--audit-executor <name>` | Sampled audit judge ([JDG-B7](05-judge-and-verdict.spec.md)) |
| `--worktree` / `--in-place` | Workspace mode |
| `--approve <step>` | Approval pause after that step passes |
| `--auto-reopen N` | Automatic re-open, 1–10 |
| `--as-agent` | Marks resumes made by an automated caller ([HUM](07-gate-and-human.spec.md)) |
| `--dry-run` | Self-improvement files nothing; every step still runs |

Option values select constants or are checked numbers; typed text never reaches a launch ([SEC](14-security.spec.md)).

### 2.2 Lifecycle hooks

A hook is an operator-registered command run on a run event (`started`, `paused`, `finished`, `failed`). `hooks add <event> -- <argv…>` stores the argv list in the operator's config under the state root; the engine runs it as a detached child with a hand-off ticket naming a facts file, never with run text on argv ([SEC §2.1](14-security.spec.md)). A hook's failure is recorded and never changes the run or its exit code (contract C2). `hooks test <event>` runs it once against a fixture facts file. The engine ships no hook; a tracker integration is a separate plugin that registers one.

## 3. Behaviours

**CLI-B1 Check before spend.** Given a request, when `run --check` runs, then it returns `ok`, `needs` (questions with choices), `error` or `broken`, exits accordingly and creates nothing; the full start refuses in exactly the cases the check does.

**CLI-B2 Reserved verbs.** Given a request whose first word is a verb name (for example `update`), when an older shim passes it to `run`, then it is refused, never treated as workflow input.

**CLI-B3 Executors verb.** Given `executors --probe`, when it runs, then it lists each executor's capabilities, its CLI version, and each probe fact with its recorded state (`confirmed`, `refuted`, `not run`), and calls no model.

| Executor | `restricts_judge_tools` | Version | Facts not run |
|---|---|---|---|
| claude | true | from `claude --version` | P-CC-1 … P-CC-6 |
| agent-sdk | true | SDK package version plus its CLI's | P-AS-1 … P-AS-3 |
| messages-api | true (by construction) | client library version and API version header | none (contract tests) |
| antigravity | false | from `agy --version` | P-AG-1 … P-AG-8 |

**CLI-B4 Background-friendly.** Given a caller that starts `run` in the background, when the run pauses, then the process exits 3 so the caller learns of the pause by its exit, with no polling.

**CLI-B5 Facts are read-only.** Given a live run, when `facts` runs, then it reads the status document and the run log only, creates nothing and calls no model (contract C13), and its JSON carries `schema_version`.

## 4. Error conditions

| Condition | Exit |
|---|---|
| Unknown verb, workflow or option | 2 |
| Engine not installed (shim) | 127 |
| Unhandled exception after an engine-error record | 1 |

## 5. Design notes

- Exit codes rather than prose are the stable contract, so a skill or CI job can tell waiting from stopped from budget spent ([ADR-0015](../adr/0015-exit-codes-as-caller-contract.adr.md)).
- The `executors` verb makes the honest-maturity rule visible: a capability resting on an unrun probe is shown as projected.
- Tables of verbs, options and exit codes in the docs are generated from the argument definitions and constants, with a drift test.

## 6. Acceptance criteria

- [ ] CLI-AC-1 Every read-only verb leaves the state root unchanged (hash test) and starts no process except the probes of `executors --probe`, which are read-only.
- [ ] CLI-AC-2 `run --check` and `run` agree on every refusal in a corpus of requests.
- [ ] CLI-AC-3 Verb words are reserved and refused as input.
- [ ] CLI-AC-4 Exit codes match [CON §2.9](01-contracts.spec.md) by a generated-table drift test.

## Open questions

None.

## References

