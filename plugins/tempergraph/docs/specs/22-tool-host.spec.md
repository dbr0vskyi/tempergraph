---
title: Tool host
type: component
status: review
prefix: THS
adrs: [0014, 0020]
---

# Tool host

## 1. Overview

The tool host executes the client tools of the [Messages API executor](20-executor-messages-api.spec.md) inside its worker process ([ADR-0020](../adr/0020-engine-owned-tool-loop-for-the-messages-api.adr.md)). It offers one tool per capability name of [CON §2.5](01-contracts.spec.md) except `subagent` and the two web capabilities, which are server tools. It is deliberately small: every path stays in the workspace, every command is a declared prefix run as a list, and every output is capped. Its scope is fixed; a step that needs more runs on another executor.

## 2. Contract

```python
class ToolHost:
    def __init__(self, workdir: Path, tools: list[ToolCapability], commands: list[str],
                 mcp: list[McpView], deny_roots: list[Path]): ...
    def definitions(self) -> list[dict]: ...               # name, description, input_schema; fixed order
    def call(self, name: str, input: dict) -> ToolOutcome: ...   # never raises
class ToolOutcome: ok: bool; content: str; error_kind: str | None; denied: bool
```

### 2.1 Tools

| Tool | Input | Does |
|---|---|---|
| `read_file` | `path`, optional `offset`, `limit` (lines) | Returns numbered lines; at most 2000 lines and 256 KB per call |
| `search_files` | `pattern` (regex), optional `path`, `glob` | Pure-Python search; at most 200 matches, each line cut at 300 chars |
| `list_files` | `glob`, optional `path` | Paths sorted, at most 1000 |
| `edit_file` | `path`, `old`, `new`, optional `all` | Replaces `old`; fails unless it occurs exactly once (or `all` is set) |
| `write_file` | `path`, `content` | Creates or overwrites; at most 1 MB |
| `run_command` | `argv` (list of strings) | Runs a declared prefix (§2.5) |
| `mcp__<s>__<t>` | the server's schema | Forwards to the MCP client (§2.6) |

Schemas use `strict: true` and reject unknown fields, so a malformed input fails validation and returns `is_error` without running.

### 2.2 Path confinement

A path is resolved against `workdir`, symlinks followed, and accepted only if the result is inside `workdir`. Write tools additionally refuse any path inside `.git`, the engine's state root and each `deny_roots` entry. A refused path returns `denied = true` and a fixed message naming the rule, never the resolved absolute path.

### 2.3 Read-only offer

`definitions()` returns only the tools whose capability was passed in. A judge host is built with read-only capabilities and catalogued MCP views only; a call to any other name returns `denied`.

### 2.4 Outputs

Every outcome is UTF-8 with invalid bytes replaced, cut to 64 KB with a marker giving the size cut. Binary files return a one-line note instead of content.

### 2.5 Commands

| Rule | Detail |
|---|---|
| Prefix | The leading items of `argv` equal a declared prefix split on spaces |
| No shell | Run as a list, never through a shell; no item may contain `;`, `&`, `|`, `` ` ``, `$(`, `>`, `<` or a newline |
| Directory | `cwd` is `workdir`; an item naming a path is confined as in §2.2 |
| Environment | The worker's environment minus the executor's credential variables |
| Limits | 600 s per call (operator-configurable), output 64 KB combined, process group killed on expiry |
| Result | Exit code, then stdout and stderr, each cut; a non-zero exit is `ok = false`, not a denial |

### 2.6 MCP client

The host starts each declared local (stdio) MCP server from the engine's MCP file, lists its tools once, offers only the declared ones (for a judge, through the catalog's view classification), and forwards calls. Remote MCP servers are not supported in the first release. Servers are children of the worker and end with it.

## 3. Behaviours

**THS-B1 Path outside refused.** Given `workdir = /w`, when `read_file` is called with `../etc/passwd` or with a symlink in `/w` pointing to `/etc`, then the call is denied and nothing is read.

| Path | Read | Write |
|---|---|---|
| `src/a.py` | allow | allow |
| `.git/config` | allow | deny |
| `../x` | deny | deny |
| link to outside | deny | deny |

**THS-B2 Exact edit.** Given a file where `old` occurs twice and `all` is not set, when `edit_file` runs, then the file is unchanged and the outcome is `ok = false` naming the count.

**THS-B3 Declared prefix only.** Given declared prefixes `pytest` and `git status`, when `run_command` is called, then only matching argv runs.

| `argv` | Outcome |
|---|---|
| `["pytest", "-q"]` | runs |
| `["git", "status", "--short"]` | runs |
| `["git", "push"]` | denied |
| `["pytest", "-q;rm"]` | denied (metacharacter) |

**THS-B4 Never raises.** Given any input, including invalid JSON types, an unreadable file or a server that crashed, when `call` returns, then it returns a `ToolOutcome` and the loop continues.

## 4. Error conditions

| Type | Handling |
|---|---|
| Input fails its schema | `ok = false`, `error_kind = invalid_input` |
| File missing or unreadable | `ok = false`, `error_kind = not_found` or `io` |
| Command times out | Group killed; `ok = false`, `error_kind = timeout` |
| MCP server fails to start | The tool is not offered; a `session_started` note records it |

## 5. Design notes

- Search and list are pure Python so the host needs no external binary and behaves the same on every platform.
- The host is the only place in the engine, besides check functions, where a command runs on the operator's machine for a model; its rules are the rules of [SEC](14-security.spec.md) for declared commands.
- The size caps keep tool results from filling the context window and are written into each tool's description so the model can page.

## 6. Acceptance criteria

- [ ] THS-AC-1 The tables of THS-B1 and THS-B3 pass on POSIX and Windows.
- [ ] THS-AC-2 Fuzzed inputs never raise from `call`.
- [ ] THS-AC-3 No code path runs a command through a shell (source scan).
- [ ] THS-AC-4 A judge host's `definitions()` contains no write, edit or command tool for any view set.

## Open questions

| Question | Owner |
|---|---|
| Offer remote MCP servers through the host, with the same catalog classification? Deferred with remote MCP in steps ([ADR-0021](../adr/0021-scope-of-planned-work.adr.md)). | Engine owner |

## References

[EMA](20-executor-messages-api.spec.md) · [CON](01-contracts.spec.md) · [SEC](14-security.spec.md) · [R-004](../research/R-004-anthropic-messages-api-executor.rsrch.md)
