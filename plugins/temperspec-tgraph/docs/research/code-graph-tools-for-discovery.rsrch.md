# Which code graph tool, if any, should temperspec's code discovery use, and how would an unattended run use it?

## Problem statement

The discovery proposal in `spec-decision-and-discovery-formats.rsrch.md` has triage list the uncertainties of a task and close the ones routed `code` through a generated code map: definitions, references, imports and test reach, built with Python's own parser and written as plain files that reading sessions search with the tools they already have. It leaves two questions open: whether an unattended `claude -p` step can use language-server style queries, and whether tree-sitter may become an optional engine dependency. The owner wants code discovery to use a code graph or a syntax tree where possible.

codegraph (`github.com/colbymchenry/codegraph`) is a tool that builds such a graph with tree-sitter and serves it to coding agents over MCP. F1 to F9 assess it; F10 to F13 compare the alternatives the owner asked about: graphify, Serena (language servers over MCP), CodeGraphContext and code-graph-rag. This note answers whether temperspec should use any of them, what it would take, and where in temperspec's stages it would help. The engine knows no workflow (ADR `the-engine-names-no-workflow`), so any engine change it needs must be a general capability.

## Sources consulted

| Source | Type | Where |
|---|---|---|
| codegraph repository at `73c6cff6` (v1.6.4, 2026-11-20): README, TELEMETRY.md, LICENSE, package.json, `src/mcp/daemon.ts`, `src/directory.ts` | code, docs | `github.com/colbymchenry/codegraph` |
| codegraph 1.6.4 from npm, run on this repository at `de9502d8` | measured | `npm i @colbymchenry/codegraph@1.6.4` |
| Six headless `claude -p` sessions, Claude Code 2.1.332, Sonnet, with and without codegraph | measured | this note, F7 |
| The discovery proposal | doc | `plugins/temperspec-tgraph/docs/research/spec-decision-and-discovery-formats.rsrch.md` (F8, F9, conclusion 12) |
| Step MCP tools in the engine | spec, code | `executor-claude-code.spec.md` ECC-B18, ECC-B19; `engine/src/tempergraph/executors/mcpconfig.py`; `executors/preflight.py:175-182`; `executors/claude.py:111-131` |
| graphify repository at v0.9.120 (2026-11-25): README, BENCHMARKS.md, LICENSE, NOTICE, pyproject.toml | code, docs | `github.com/Graphify-Labs/graphify` |
| graphify 0.9.120 from PyPI (`graphifyy`), run on this repository | measured | `pip install "graphifyy[mcp]==0.9.120"` |
| Serena repository (2026-11-24): README, LICENSE, `serena_config.template.yml`, `serena tools list` | code, docs | `github.com/oraios/serena` |
| Serena from PyPI (`serena-agent`), run on this repository | measured | `pip install serena-agent` |
| CodeGraphContext v0.6.13 and code-graph-rag v0.7.129: README, LICENSE, pyproject.toml | docs | `github.com/CodeGraphContext/CodeGraphContext`, `github.com/vitali87/code-graph-rag` |
| Eight more headless sessions with graphify, Serena or codegraph, three of them told to use the tool | measured | this note, F13 |
| How a step's MCP config is built | code | `engine/src/tempergraph/executors/mcpconfig.py` `build_config` |
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

### F10 graphify: the same graph as a plain JSON file, from a Python package `supported`

graphify parses about 40 languages with tree-sitter (25 grammar packages pinned in `pyproject.toml`) and writes the graph to `graphify-out/graph.json`, a plain file, plus a report. Docs, PDFs and media can join the graph through an optional model pass; `GRAPHIFY_BACKEND=none` turns every model call off, and code is parsed locally either way. A local stdio MCP server, `graphify-mcp <graph.json>`, offers `query_graph`, `affected`, `shortest_path`, `get_node`, `get_neighbors` and five more. The README leads with a hosted MCP endpoint (Graphify Cloud), where the graph lives on the vendor's servers; only the local server fits a run.

- Licence: Apache-2.0, with earlier contributions still under MIT (NOTICE). No telemetry. Every query is logged locally to `~/.cache/graphify-queries.log` unless `GRAPHIFY_QUERY_LOG_DISABLE=1`.
- Install: 175 MB virtual environment, Python 3.11.5 or later, nothing compiled.
- Measured here: `graphify update . --no-cluster` read 2,240 files (code, docs and config) in 32 seconds into 23,570 nodes and 67,539 edges; `graph.json` is 31 MB and `graphify-out/` 88 MB. `affected render_step` gave the same callers and test functions as codegraph and `grep`, plus the plan and report headings that name the function, so code and documents sit in one graph. `affected load` refused the ambiguous name and listed its 19 definitions (exit code 3, by design); given the id of `executors/binding.py`'s `load`, it gave the same three callers codegraph found through the aliased imports. 89% of edges are marked `EXTRACTED`, 11% `INFERRED`.
- `graphify-out/` is not ignored by git. temperspec's `commit_step` stages everything (`git add -A`), so an index built inside a run's working folder would be committed, 88 MB of it, unless the folder is ignored first.
- Maturity: first commit 2026-04-04, 3,242 commits, 266 tags, still at 0.9.x. The top author wrote about 42% of commits under two spellings and there are several regular contributors. A company sells a hosted version on top of it.

### F11 Serena: real language servers over MCP, with editing and shell tools in the same server `supported`

Serena (Oraios AI) is an MCP server that drives language servers (more than 40 languages; a paid JetBrains backend as an alternative) and offers symbol-level tools: `find_symbol`, `find_referencing_symbols`, `find_declaration`, `find_implementations`, `get_symbols_overview`, diagnostics. It does not build a stored graph; each question is answered by the language server.

- It answers the proposal's first open question: an unattended `claude -p` session can get language-server queries today, as MCP tools. Serena connected in every headless session here.
- Licence: the application is GPL-3.0-or-later; its language-server client library, SolidLSP, is MIT. Run as a separate program the operator installs, the GPL does not reach the engine. Vendoring it, or making it a dependency, would bring that question in. Its `analytics` module counts tokens locally; no outbound telemetry was found in it.
- The same server offers editing and shell tools: `serena tools list` shows `execute_shell_command`, `create_text_file`, `replace_symbol_body`, `rename_symbol`, `replace_in_files` and more. A step's private MCP config names the operator's server directly (`build_config(..., direct=True)`), with no filtering proxy, unlike a judge's. So a reading session is offered all 21 of Serena's tools, and only `--allowedTools` stops the unlisted ones. In the runs here, one call to an unlisted tool was denied under `--permission-mode dontAsk`.
- Defaults that do not fit a run: since 2.x it exposes a single `serena_repl` tool unless started with `--agent-interface tools`. It also starts a web dashboard unless `--enable-web-dashboard false`. Language servers are downloaded on first use.
- Install: 103 MB virtual environment plus the language servers. Maturity: since 2025-03, 3,658 commits, two main maintainers.

### F12 CodeGraphContext and code-graph-rag put a database or a model between the session and the code `supported`

Surveyed, not run. CodeGraphContext (MIT, v0.6.13) indexes code into a graph database (FalkorDB Lite by default, or KuzuDB, Neo4j and others) and serves it over MCP and a CLI. code-graph-rag (MIT, v0.7.129) stores the graph in SQLite by default (Memgraph or Neo4j optional), and its query path turns a natural-language question into a Cypher query with a model (README: "User Query -> AI Model (Cypher Gen) -> Cypher Query"). Each adds a database engine, a model call or both, and answers the same four questions as codegraph and graphify. Nothing in their documents shows an advantage for temperspec over those two.

### F13 A session uses the tool only when the prompt names it, and none of the tools saved cost on the question here `supported`

The same reach question as F7, Sonnet, `Read,Grep,Glob` plus the tool's read-only MCP tools.

| Tool | Prompt names the tool | Runs | Tool calls of the code tool | Turns | Cost (USD) | All six reach items found |
|---|---|---|---|---|---|---|
| none (F7) | | 3 | | 13-16 | 0.158-0.264 | yes |
| codegraph (F7) | no | 2 | 1, 0 | 12, 9 | 0.236, 0.185 | yes |
| codegraph | yes | 1 | 1 | 9 | 0.199 | yes |
| graphify | no | 2 | 0, 0 | 16, 17 | 0.287, 0.266 | yes |
| graphify | yes | 1 | 3 | 17 | 0.174 | yes |
| Serena, `tools` interface | no | 1 | 1 | 22 | 0.329 | yes |
| Serena, `tools` interface | yes | 1 | 0 (it called an unlisted tool, denied) | 17 | 0.293 | yes |

Two earlier Serena runs were left out: they were offered only `serena_repl` (F11), so they measured nothing. With no instruction, a session falls back to `Grep` and `Read` almost every time, even when the tool is connected. Every arm found the same definitions, callers and test files. On this repository and this question, no tool lowered cost or turns beyond the spread between runs.

## Conclusions

1. **Make no code graph tool a dependency of the engine or of temperspec.** Every candidate is young and fast-moving (F3, F10, F11), and each brings tens to hundreds of MB. One has telemetry on by default (F2), and one is GPL (F11). The proposal's plain-file map stays the floor every run has (its conclusion 12), built by the language's own parser. The alternatives do not change this.
2. **Offer such a tool as optional, where the operator has it, and name it in the prompt.** temperspec's reading steps (`read_component`, `read_gap`, discovery, plan, independent review) would declare the tool's read-only MCP tools as optional. When the tool was offered, the prompt would say to use it for definitions and references and to confirm each answer in the file. Without that line the tool goes almost unused (F13). The rule to confirm in the file is the one reading sessions already follow for findings.
3. **That needs one general engine capability: an optional step tool.** A step may mark a declared tool optional. It is offered when the executor and the operator's configuration can supply it, and left out with a recorded note when not, instead of the preflight refusal `mcp-server-undefined` (F5). The engine already appends the tools a session got to its prompt, so a prompt can say "if you have a code index tool" and stay true either way. Stated without any workflow, with an engine fixture that declares an optional MCP tool against a configuration that has the server and one that does not.
4. **A second general capability is worth weighing: route a step's MCP servers through the filtering proxy that judges already use.** A step is offered every tool of the operator's server today, editing and shell tools included, and only `--allowedTools` holds them back (F11). Showing only the declared tools would also keep a session's tool list short.
5. **Choose the tool by how it is used, not one tool for everything** (F8, F10, F11):
   - For a session that queries during reading: codegraph (one `explore` call answers a reach question; 20+ languages; MCP-first). Serena when exact language-server answers matter more than speed, started with `--agent-interface tools` and given only its read tools.
   - For a script that writes the plain-file map in more languages than Python: graphify's `graph.json` (Python, Apache-2.0, no telemetry, plain JSON, docs linked to code). It can only feed a script: at 31 MB here, no session should read it whole. This is how tree-sitter could reach the map without becoming an engine dependency: an optional extra that the map script uses when installed.
   - Not CodeGraphContext or code-graph-rag (F12).
6. **The operator's setup belongs in temperspec's guide, not in the engine.** For codegraph: `--no-telemetry`, `CODEGRAPH_NO_UPDATE_CHECK=1` and the shared daemon (F2, F6). For graphify: `GRAPHIFY_BACKEND=none`, `GRAPHIFY_QUERY_LOG_DISABLE=1`, the local server only, and `graphify-out/` ignored before any run (F10). For Serena: `--agent-interface tools` and the dashboard off (F11).
7. **Index freshness is the package's job.** `prepare` can build or update the index when the tool is present and skip it otherwise. It is a script, so no session needs a shell (F6).
8. **Keep a tool only if it measurably helps.** No tool saved anything on one Python reach question here (F7, F13). codegraph's own figures show savings that grow with how much searching a question needs. Measure with the package's trial, with the prompt line of conclusion 2, on a non-Python repository and on a wide reach question here, counting cost, turns and missed callers, before recommending any tool in the guide.
9. **Two cheap uses need no session at all.** `codegraph cycles` can be an optional finding in setup (it found a five-file import cycle in temperspec's own package, F4). `callers --json` or `impact --json` (codegraph), or `affected` (graphify), can run in a script that writes the reach of the symbols triage names into the hand-off, in the plain-file shape the proposal uses.
10. **Build order, after the proposal's step (b):** the optional step tool (3), then the optional declaration and prompt line on `read_gap` alone with the guide entry (2, 6), then the trial (8), then the other reading steps. Conclusions 4, 5 (graphify as a map backend), 7 and 9 follow if the trial keeps a tool.

## Open questions

- Whether Claude Code offers a headless step language-server queries of its own, without an MCP server (definitions, references, types). Serena shows that they can be had through MCP (F11). Until answered: structural queries come from the plain-file map or an optional MCP tool.
- Whether codegraph's daemon, which outlives a session by 5 minutes, conflicts with any engine rule that every process a session starts ends with it. Not read in the engine's specs for this note. Until answered: the operator's definition may set `CODEGRAPH_DAEMON_IDLE_TIMEOUT_MS` low.
- How much codegraph saves on a large or non-Python repository driven by temperspec's own prompts. codegraph's benchmark uses its own questions and instructions that steer the agent to the tool. Until answered: conclusion 6.
- How often codegraph's or graphify's resolution is wrong on Python in this repository. Each was checked on two names (F4, F10). Until answered: their answers are leads, confirmed in the file.
- Whether a step offered tools it may not use (F11) can reach them in another permission mode than `dontAsk`, for example `acceptEdits` in the engine's worktree. Not tested. Until answered: conclusion 4.
