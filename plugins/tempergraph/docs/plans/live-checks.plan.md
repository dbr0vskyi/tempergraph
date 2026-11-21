# Live checks for release 1

The one list of everything release 1 still has to confirm on the owner's machine against a signed-in Claude Code (first-release plan T11.2). The offline suite covers the same code on stand-ins. A live result is written into the results table only from a run on the machine. It is never inferred, and a failure is kept as a finding. When a row passes, the spec row it names moves from `not run` to its result and the CLI version, in the same pull request.

## 1. Before you start

- A clone of this repository on a machine with Python 3.11 or newer, Claude Code signed in (`claude --version` prints a version), and `gh` signed in for row L-17.
- From `plugins/tempergraph/engine/`: `python -m pip install -e '.[dev]'`, then `python -m pytest` passes offline. It must pass before any live row, so that a live failure is about the live side.
- Run the live rows from a plain terminal, not from inside a Claude Code session. The probes strip `CLAUDECODE*` variables, but a nested session can still inherit settings. Rows L-12 to L-14 are the exception: they must run inside a Claude Code session.
- Spend: rows L-1 to L-11 cost well under 1 USD on the `haiku` alias (each session is capped at 0.20 USD), and L-11 is capped at 2 USD for the run. Rows L-16 and L-18 state their caps. Set `TEMPERGRAPH_LIVE_MODEL` to try another alias.

## 2. Automated rows: one command

```
cd plugins/tempergraph/engine
TEMPERGRAPH_LIVE=1 python -m pytest tests/live -v -rA -o addopts="" 2>&1 | tee live-report.txt
```

Paste `live-report.txt` (or its summary and the printed lines) into the thread. It holds no secret: the probes print tool lists, result subtypes, session ids and file paths.

| Row | Check | Test | A pass looks like | Then update |
|---|---|---|---|---|
| L-0 | CLI version | `test_version` | prints `claude --version` | the version column of every row below |
| L-1 | P-CC-1 `--bare` isolates user config, sign-in still works | `test_p_cc_1_bare_isolates_user_config` | `success`; no MCP servers or plugins in `system/init` | ECC §2.7 |
| L-2 | P-CC-2 judge tools are exactly `Read`, `Grep`, `Glob` | `test_p_cc_2_judge_tools_are_exact` | `init.tools == [Glob, Grep, Read]` | ECC §2.7 (`restricts_judge_tools`) |
| L-3 | P-CC-3 the stream shape at `--max-budget-usd` | `test_p_cc_3_budget_end_shape` | result subtype `error_max_budget_usd` | ECC §2.7; `BUDGET_SUBTYPE` in `executors/claude.py` if it differs |
| L-4 | P-CC-5 prompt on stdin with `-p` | `test_p_cc_5_prompt_on_stdin` | `success` and the reply holds `stdin-ok` | ECC §2.7 |
| L-5 | P-CC-6 `dontAsk` refuses an unlisted call without a prompt | `test_p_cc_6_dont_ask_refuses` | no `out.txt`; the session ends by itself; the denial count is printed | ECC §2.7 |
| L-6 | P-CC-7 a native transcript and its path | `test_p_cc_7_transcript_location` | prints a path or `none kept`; both are results | ECC §2.7, EVT §2.4 |
| L-7 | P-CC-8, P-CC-9 a workflow plugin's skill and agent under `--plugin-dir` | `test_p_cc_8_and_9_plugin_dir_skill` | `system/init` names `hello` and `helper`; a `Skill` call is recorded | ECC §2.7, PKG §2.6 |
| L-8 | P-WTR-1 no worktree tools in a step | `test_p_wtr_1_no_worktree_tools` | neither `EnterWorktree` nor `ExitWorktree` in `init.tools` | WTR §5, R-090 |
| L-9 | SRV-AC-6 the session reviewer has no tools | `test_srv_reviewer_has_no_tools` | `init.tools == []` and `success` | SRV §6 |
| L-10, L-11 | M1: a two-step run end to end on `claude`, then the loop child inline: digests from real `raw.jsonl` and a session review | `test_m1_two_step_run_and_session_review` | every session `ok`; exit 0, or 3 when a judge asks; every digest `capture: full`; `loop.jsonl` has `review_planned` and `review_done` or `review_failed` | first-release plan T11.2; SRV §6 |

The M1 test runs in a scratch repository that pytest removes afterwards, so its printed lines are the record. To review one of your own runs on the machine, run `tempergraph improve review <workflow>/<task> --dry-run` and then without `--dry-run` (it spends up to the SRV §2.7 cap, 5 USD in dev mode).

## 3. Manual rows

| Row | Check | How | A pass looks like | Then update |
|---|---|---|---|---|
| L-12 | P-SUP-1 `CLAUDE_CODE_SESSION_ID` in the Bash tool environment | In a Claude Code session (CLI, then desktop, then the IDE), ask Claude to run `echo $CLAUDE_CODE_SESSION_ID`, then compare it with the session id that `/status` shows | non-empty and equal on each surface | PRV §6 |
| L-13 | P-SUP-2 `UserPromptSubmit` gets the prompt text | Add a `UserPromptSubmit` hook to a scratch project that writes its stdin to a file, then send one prompt | the file's JSON has a `prompt` field with your text | PRV §6 |
| L-14 | P-SUP-3 the hook payloads SCO reads | With the SCO hooks of T7.6 registered, use one session normally, then read `~/.tempergraph/supervision/` | each hook wrote one line with the fields SCO §2.1 lists | SCO §5 |
| L-15 | P-SUP-4 Agent SDK children carry Claude Code markers | From a small Agent SDK script, run a Bash tool call that prints `env` | the `CLAUDE_CODE_*` markers appear | PRV §6 |
| L-16 | 8.2.5 a real install from the plugin | `claude plugin marketplace add <path to this clone>`, install `tempergraph`, then follow the install skill: `<plugin>/bin/tempergraph install --check --json`, `install --json`, `<shim> executors --probe` | the shim runs; the probe says `claude` is installed, signed in and at a tested version | UPD §2.7, T8 plan |
| L-17 | Filing through `gh` | In a scratch GitHub repository you own, set it as `issue_repository` of a scratch workflow, make a run fail one gate twice (dev mode), let the loop child run (`TEMPERGRAPH_LOOP=inline`) | one issue in that repository with the fingerprint marker; a second run comments on it instead of opening a second issue | SIL §6 |
| L-18 | Judge scoring with a signed-in `claude` | `tempergraph evals score <workflow> <gate> --cap 2` on a workflow with at least the JCL minimum of reviewed cases, then `tempergraph evals bar <workflow>` | the score row is written and the bar shows the gate's state with real figures | JCL §6 |
| L-19 | A paired trial | `tempergraph improve backlog <workflow>`, `improve propose <workflow> <cluster>`, then `improve trial <proposal> --cap 5` | the trial ends in one of PRP's end states; child runs carry `origin: trial`; then `improve open <proposal>` opens a draft pull request. At autonomy `trial` in stable mode the loop does this on its own and opens the draft only on `shown_better` | PRP §6 |
| L-20 | 6.3.5 MCP and plugin listing before spend | Run a workflow that declares an MCP tool on a machine without that server | today: `missing_at_start` at run time. Record what `claude mcp list --json` prints, so 6.3.5 can be built on it | T6 plan 6.3.5 |
| L-21 | GRD-AC-5 recorded stream fixtures | Run any two-step workflow, then copy `sessions/*/raw.jsonl` of one step and one judge from `.tempergraph/runs/...` into a new issue or the thread. Scrub first: the files hold your prompt and outputs | two recorded streams the T5 tests can replay | T5 plan 5.4.2 |
| L-22 | P-CC-4 subagent model precedence | In a step that calls an agent with its own `model`, set `subagent_model` and read which model the agent's turns report in `raw.jsonl` | either answer is a result; record which wins | ECC §2.7 |
| L-23 | P-MOD-1 to P-MOD-4 the monitor mod | `claude plugin test plugins/tempergraph-monitor`, then install the mod and start a run in another terminal | the tests pass; the mod draws the run and updates while it runs, in the terminal and on desktop | monitor R-001, T10 plan |
| L-24 | SHL-AC-2, AUT-AC-1, AUT-AC-8, LSK-AC-1 skill rubric scenarios | For each scenario in SHL §6, AUT §6 and LSK §6, start a fresh Claude Code session with the plugin installed and act it out | each rubric line holds (for example, the run skill asks before guessing and never answers a pause) | T9 plan 9.1.4, 9.2.7, 9.3.3 |
| L-25 | T11.1 the example workflows on a real `claude` | `tempergraph workflows register plugins/release-notes-tgraph` and `plugins/doc-refresh-tgraph`; in a repository with a tag and merged changes, `tempergraph run release-notes <tag>`; in a repository with a Markdown guide, `tempergraph run doc-refresh "docs/guide.md: the install section"`, then answer the approval | release-notes finishes or pauses with a judge's question; doc-refresh writes `outline.md` with no session, routes on `size`, and after `proceed` the finalizer says `written` | first-release plan 11.1.6 |
| L-26 | The live checks of each workflow package in the repository | For every folder under `plugins/` that holds a `tempergraph.json`, run the rows of its `docs/plans/live-checks.plan.md`, when it has one | every row of every such file passes; a package's results are written in its own file | PKG, SCF §2.5, [ADR-0129](../adr/0129-the-engine-names-no-workflow-and-takes-requests-as-general-capabilities.adr.md) |

## 4. Results

| Row | Date | CLI version | Result | Notes |
|---|---|---|---|---|
| L-0 to L-26 | | | not run | |
