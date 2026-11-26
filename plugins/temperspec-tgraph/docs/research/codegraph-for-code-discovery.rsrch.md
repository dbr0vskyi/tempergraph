# Would codegraph improve temperspec's code discovery, and how would an unattended run use it?

## Problem statement

The discovery proposal in `spec-decision-and-discovery-formats.rsrch.md` has triage list the uncertainties of a task and close the ones routed `code` through a generated code map: definitions, references, imports and test reach, built with Python's own parser and written as plain files that reading sessions search with the tools they already have. It leaves two questions open: whether an unattended `claude -p` step can use language-server style queries, and whether tree-sitter may become an optional engine dependency. The owner wants code discovery to use a code graph or a syntax tree where possible.

codegraph (`github.com/colbymchenry/codegraph`) is a tool that builds such a graph with tree-sitter and serves it to coding agents over MCP. This note answers whether temperspec should use it, what it would take, and where in temperspec's stages it would help. The engine knows no workflow (ADR `the-engine-names-no-workflow`), so any engine change it needs must be a general capability.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| codegraph repository at `73c6cff6` (v1.6.4, 2026-11-20): README, TELEMETRY.md, LICENSE, package.json, `src/mcp/daemon.ts`, `src/directory.ts` | code, docs | `github.com/colbymchenry/codegraph` |
| codegraph 1.6.4 from npm, run on this repository at `de9502d8` | measured | `npm i @colbymchenry/codegraph@1.6.4` |
| Six headless `claude -p` sessions, Claude Code 2.1.332, Sonnet, with and without codegraph | measured | this note, F7 |
| The discovery proposal | doc | `plugins/temperspec-tgraph/docs/research/spec-decision-and-discovery-formats.rsrch.md` (F8, F9, conclusion 12) |
| Step MCP tools in the engine | spec, code | `executor-claude-code.spec.md` ECC-B18, ECC-B19; `engine/src/tempergraph/executors/mcpconfig.py`; `executors/preflight.py:175-182`; `executors/claude.py:111-131` |
| temperspec units and their tools | code | `plugins/temperspec-tgraph/workflow/temperspec/__init__.py:94`, `:172-224`; `routing.py:498-523` |

## Key findings

### F1 What codegraph is `confirmed`

A local code-intelligence index for coding agents. A Rust kernel with tree-sitter grammars (a portable WebAssembly path for the rest) extracts definitions and edges (calls, imports, extends, implements, framework routes) for more than 20 languages, Python among them, and resolves references to their definitions through imports. Everything goes into one SQLite database, `.codegraph/codegraph.db`, with full-text search (README "How It Works"). It is reached three ways:

- an MCP server (`codegraph serve --mcp`) that lists one tool, `codegraph_explore`, by default: a question in, the relevant symbols' verbatim source, the call paths between them and a "blast radius" out. Seven narrower tools (`node`, `search`, `callers`, `callees`, `impact`, `files`, `status`) are switched on with `CODEGRAPH_MCP_TOOLS`;
- a CLI with the same queries and `--json` output, plus `affected` (test files reached from changed files through imports) and `cycles` (circular imports, exit 1 when any);
- a Node library (`CodeGraph.open`, `getCallers`, `getImpactRadius`, `buildContext`), which needs Node 22.5 or later.

A file watcher keeps the index in step with edits while a server runs; a server that connects reconciles changed files first.

### F2 Dependencies, size, licence, telemetry `confirmed`

- Runtime: a self-contained bundle with its own Node, installed by a shell script or npm. Nothing is compiled on the machine. Linux, macOS and Windows on x64 and arm64.
- Size: the npm install is 302 MB, of which 300 MB is the platform package. The index of this repository (679 files) is 66 MB, against the 45 KB outline the discovery proposal measured for the engine's source.
- Licence: MIT, compatible with this repository's Apache-2.0; nothing would be vendored in any case.
- Telemetry: on by default (anonymous usage counts; the installer shows a default-on toggle). `CODEGRAPH_TELEMETRY=0`, `DO_NOT_TRACK=1` or `--no-telemetry` on the server entry turn it off. The MCP server also checks GitHub once a day for a newer release unless `CODEGRAPH_NO_UPDATE_CHECK=1` or `DO_NOT_TRACK=1`.
- No API key, no network service; the index stays on the machine.

### F3 Maturity `supported`

First commit 2026-01-18; 1,971 commits, 37 release tags, v1.6.4 on 2026-11-20, 281 commits in the last 30 days, 988 test files. One maintainer wrote about 90% of the commits (1,773 of 1,971 under two spellings of the same name). Releases since July 2026 carry npm provenance and signed build attestations. An upgrade can require a full re-index (`codegraph status` reports an index built by an older version). It is young, fast-moving and single-maintainer: useful, but not something a run should be unable to work without.

### F4 On this repository it indexes fast and resolves what a name-only map gets wrong `supported`

`codegraph init --local-only` indexed 679 files (655 Python) into 16,203 nodes and 57,350 edges in 8.9 seconds wall clock. Queries answer in 0.2 to 0.6 seconds.

- `callers render_step` listed exactly the three files that use it (`render/prompt.py`, `run/nodes.py:624`, `tests/test_prompt.py`), each caller named down to the test function, matching `grep`.
- `callers load` split the 18 definitions of `load` and gave each its own callers. For `executors/binding.py:81` it found `binding_mod.load(...)` in `executors/claude.py:388` and `bindings.load(...)` in `improve/calibration.py:402`, both reached through an aliased module import (`from tempergraph.executors import binding as binding_mod`). This is the case the discovery proposal measured as its main limit (F8 there: one name in eight is defined more than once, so a name-only index points to the wrong definition). Checked on this one name only.
- `impact render_step --depth 2` gave 15 symbols across 6 files, test functions included.
- `cycles` found one group: five files of the temperspec package (`workflow/temperspec/__init__.py`, `checks.py`, `review.py`, `routing.py`, `summary.py`).
- `affected render/prompt.py` is coarse for Python: 1 test file at depth 1, 2 at depth 2, and 155 of the engine's 227 test files at the default depth 5, because most tests import through package `__init__` hubs. Which tests pin a symbol is better read from `callers` and `impact`, which name test functions.

### F5 An unattended `claude -p` session can use it today, through the engine's existing step MCP tools `confirmed`

A headless session launched with `--strict-mcp-config --mcp-config <file naming only codegraph> --tools Read,Grep,Glob --allowedTools Read,Grep,Glob,mcp__codegraph__codegraph_explore --permission-mode dontAsk` connected the server and called `codegraph_explore` (F7). This is the launch shape the engine already builds: a step that declares `mcp:<server>/<tool>` gets `--strict-mcp-config` and a private config listing that server as the operator's own MCP configuration defines it (ECC-B18, ECC-B19, `executors/claude.py:127-131`). So temperspec could offer `mcp:codegraph/codegraph_explore` to a reading step with no engine change, on a machine where the operator has defined a `codegraph` server.

Two limits of the current engine:

- A step that declares an MCP server the operator has not defined is refused at preflight (`mcp-server-undefined`, `executors/preflight.py:175-182`). Declaring codegraph would make every temperspec run fail on a machine without it. The engine has no way to declare a tool as optional.
- The server must be defined in the operator's user or local scope; a repository's `.mcp.json` does not count (SEC-B3). A package cannot ship the server definition, by design.

This answers half of the proposal's first open question: unattended runs can use structural code queries, through MCP. Whether Claude Code offers language-server queries of its own to a headless step is still open.

### F6 Running it under the engine raises three practical points `supported`

- **Parallel sessions.** With `CODEGRAPH_NO_DAEMON=1`, only one server may serve a project: of three servers started together on one index, two exited with "writer lock held" and one session in F7 lost its tool that way (status `failed`). Without that variable, extra servers hand off to a shared background daemon, all three connected, and the daemon stays alive 5 minutes after its last client (`CODEGRAPH_DAEMON_IDLE_TIMEOUT_MS`, `src/mcp/daemon.ts:69-80`). temperspec reads in parallel (`read_component` and `read_gap` are maps of up to 3 concurrent sessions), so the daemon mode is the one that works, and it leaves a process behind each run for a few minutes.
- **Index location.** The server finds the nearest `.codegraph/` above its working folder (`src/directory.ts:365`). A run's working folder with no index gets "use built-in tools instead", not an error; one under a checkout that has an index gets that checkout's index, which may describe another branch until the watcher catches up. A fresh index costs about 9 seconds here, and a script unit (temperspec's `prepare`) could build it; reading sessions have no shell.
- **Commits.** temperspec's `commit_step` stages everything (`git add -A`, `routing.py:519`). `codegraph init` writes `.codegraph/.gitignore` so that the folder ignores itself, so the 66 MB index is not committed.

### F7 On one reach question here it did not save cost or change the answer `supported`

Question (a realistic temperspec reach): where the retry block of a step prompt and its path limit are defined, which source functions call the rendering function directly or through one call, and which test files pin the block. Sonnet, `Read,Grep,Glob` in both arms, codegraph added in one.

| Arm | Runs | Cost (USD) | Turns | Tool calls |
|---|---|---|---|---|
| with codegraph, server connected | 2 | 0.236, 0.185 | 12, 9 | 1 `codegraph_explore`, 6 Grep, 1 Read (second run) |
| with codegraph, server failed (F6) | 1 | 0.155 | 15 | 10 Grep, 4 Read |
| without | 3 | 0.264, 0.158, 0.162 | 16, 14, 13 | 8 Grep, 4-5 Read |

All six answers named the same definitions (`render/prompt.py:19`, `:144`), the same direct caller (`run/nodes.py:624`) and the same three test files. Turns fell by a few; cost did not fall measurably. Six runs on one question cannot show a small effect, and say nothing about larger or non-Python repositories.

codegraph's own benchmark points the same way: on 7 repositories with Opus, cost fell 57-78% where the file-reading agent needed 28-43 tool calls (VS Code, Excalidraw, Tokio, Alamofire), 13% on Django and nothing on Gin, where it needed 14 and 7 (README "Benchmark Results"). It also reports that its answers leave about 80% more retrieved text in the context window by the end of a session (67k against 18k tokens on VS Code). temperspec's sessions are short and stateless, so that cost is small for it, but a reading session that calls `explore` several times carries large verbatim payloads.

### F8 Against the discovery proposal's code map `inferred`

| | Proposal's map (`ast`, plain files) | codegraph |
|---|---|---|
| Languages | Python; text search for the rest | 20+ with full extraction |
| Same-name definitions | Name only; about 1 in 8 names ambiguous | Resolved through imports (F4) |
| Calls through dispatch, callbacks, framework routes | No | Partly (its stated cross-file coverage for Python: 100% of files on psf/requests; Django routes 74%) |
| How a session reads it | `Read` and `Grep` on files it already may use | An MCP tool, or a script exporting CLI `--json` to files |
| Dependency | None | A 300 MB binary the operator installs and keeps current |
| Freshness | Rebuilt by the script that writes it | Watcher, or a rebuild in a script |
| Deterministic, testable offline | Yes | Its output is deterministic, but the engine's suite cannot assume it is installed |
| Size | Tens of KB | Tens of MB |

The two are not alternatives on the same rung. The proposal's map is a floor that every run has. codegraph is a higher rung (the tree-sitter rung of the proposal's F9 ladder, with resolution added) that some operators will have, and it answers the proposal's second open question without making tree-sitter an engine dependency: the operator installs it, the engine only offers it.

### F9 Where in temperspec's stages it would help `inferred`

| Stage | Helps with | Weight |
|---|---|---|
| setup, `read_component` | Unfamiliar or non-Python repositories: what each component defines and uses; `cycles` as a finding | High where the repository is not Python |
| triage | Little: triage lists what is not known; it should not answer | Low |
| `read_gap` (code-routed uncertainties) | "Where is it, what uses it, what does it use, which tests pin it": the proposal's four questions, answered by `callers`, `callees`, `impact` | Medium to high; the main use |
| discovery, `## Reach` in the hand-off | The same four answers, written once | Medium |
| plan | The reading list and which test functions to run | Medium; `affected` too coarse for Python (F4) |
| code | Little: the plan names the files | Low |
| independent review | Blast radius of the diff against the plan's reach | Medium |

## Conclusions

1. **Do not make codegraph a dependency of the engine or of temperspec.** It is young and single-maintainer (F3), large (F2) and on by default in telemetry, and a run must work without it. The proposal's plain-file map stays the floor every run has (its conclusion 12), built by the language's own parser.
2. **Offer it as an optional tool where the operator has it.** temperspec's reading steps (`read_component`, `read_gap`, discovery, plan, independent review) would declare `mcp:codegraph/codegraph_explore` as optional, and their prompts would treat its answers as leads to confirm in the file, the rule reading sessions already follow for findings.
3. **That needs one general engine capability: an optional step tool.** A step may mark a declared tool optional; it is offered when the executor and the operator's configuration can supply it, and left out with a recorded note when not, instead of the preflight refusal `mcp-server-undefined` (F5). The engine already appends the tools a session got to its prompt, so the session knows whether it has the tool. Stated without any workflow, with an engine fixture that declares an optional MCP tool against a configuration that has the server and one that does not.
4. **The operator's server definition should switch off telemetry and the update check and leave the daemon on**: `"args": ["serve", "--mcp", "--no-telemetry"]`, `CODEGRAPH_NO_UPDATE_CHECK=1`, no `CODEGRAPH_NO_DAEMON` (F2, F6). This goes in temperspec's guide, not in the engine.
5. **Index freshness is the package's job.** `prepare` can run `codegraph index` when the CLI is present and the working folder has no index, and skip it otherwise; it is a script, so no session needs a shell (F6). Whether to rebuild per run or trust the watcher is a measurement, not a guess.
6. **Keep it only if it measurably helps.** F7 shows no saving on one Python reach question here; codegraph's own figures show savings that grow with how much searching a question needs. Measure with the package's trial on a non-Python repository and on a wide reach question here, counting cost, turns and missed callers, before recommending it in the guide.
7. **Two cheap uses need no session at all**: `codegraph cycles` as an optional finding in setup (it found a five-file import cycle in temperspec's own package, F4), and `callers --json` / `impact --json` in a script that writes the reach of the symbols triage names into the hand-off, the same plain-file shape the proposal uses.
8. **Build order, after the proposal's step (b)**: the optional step tool (3), then the optional declaration on `read_gap` alone with the guide entry (2, 4), then the trial (6), then the other reading steps. Conclusions 5 and 7 follow if the trial keeps it.

## Open questions

- Whether Claude Code offers a headless step language-server queries of its own (definitions, references, types). Until answered: structural queries come from the plain-file map or an optional MCP tool.
- Whether codegraph's daemon, which outlives a session by 5 minutes, conflicts with any engine rule that every process a session starts ends with it. Not read in the engine's specs for this note. Until answered: the operator's definition may set `CODEGRAPH_DAEMON_IDLE_TIMEOUT_MS` low.
- How much codegraph saves on a large or non-Python repository driven by temperspec's own prompts. codegraph's benchmark uses its own questions and instructions that steer the agent to the tool. Until answered: conclusion 6.
- How often codegraph's resolution is wrong on Python in this repository. Checked on two names (F4). Until answered: its answers are leads, confirmed in the file.
