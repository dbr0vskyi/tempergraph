# Tool host

## Purpose

The tool host executes the client tools of the [Messages API executor](executor-messages-api.spec.md) inside its worker process ([ADR `engine-owned-tool-loop-for-the-messages-api`](../adr/engine-owned-tool-loop-for-the-messages-api.adr.md)). It offers one tool per capability name ([CON-B11](contracts.spec.md)) except `subagent` and the two web capabilities, which are server tools. It is deliberately small: every path stays in the workspace, every command is a declared prefix run as a list, and every output is capped. Its scope is fixed; a step that needs more runs on another executor. Search and list are pure Python so the host needs no external binary and behaves the same on every platform; besides check functions it is the only place where a command runs on the operator's machine for a model, so its command rules are those of [SEC](security.spec.md). The Messages API worker and every step and judge on that executor depend on it.

## Depends on

- `security.spec.md`: commands see no executor credentials (SEC-B13)

## Behaviours

### THS-B5 Tools offered

WHEN the host lists its tools THE host SHALL give each a name, a description that states its size caps so the model can page, and an input schema, in the fixed order `read_file`, `search_files`, `list_files`, `edit_file`, `write_file`, `run_command`, then each `mcp__<s>__<t>` with the server's own schema.

- GIVEN the same capabilities twice WHEN the tools are listed THEN both lists are in the same order

### THS-B12 Reading tools' inputs and caps

WHEN the host offers its reading tools THE host SHALL give `read_file` the inputs `path` and optional `offset` and `limit` in lines, answered with numbered lines, at most 2000 lines and 256 KB per call; `search_files` the inputs `pattern` (a regex) and optional `path` and `glob`, at most 200 matches with each line cut at 300 characters; and `list_files` the inputs `glob` and optional `path`, at most 1000 sorted paths.

- GIVEN a file of 3000 lines WHEN `read_file` is called without `limit` THEN 2000 numbered lines are returned
- GIVEN a search with 250 matches WHEN it returns THEN 200 matches are listed

### THS-B13 Writing tools' inputs and caps

WHEN the host offers its writing tools THE host SHALL give `edit_file` the inputs `path`, `old`, `new` and optional `all`; `write_file` the inputs `path` and `content`, at most 1 MB; and `run_command` the input `argv`, a list of strings.

- GIVEN content of 2 MB WHEN `write_file` is called THEN nothing is written and the outcome names the cap

### THS-B6 Strict schemas

WHEN a tool input fails its schema, including an unknown field THE host SHALL run nothing and return `ok = false` with `error_kind = invalid_input`.

- GIVEN `read_file` called with an extra field `mode` WHEN validated THEN nothing is read and the outcome is `invalid_input`

### THS-B7 Path confinement

WHEN a tool resolves a path THE host SHALL resolve it against the workdir with symlinks followed and accept it only inside the workdir, refuse a write tool any path inside `.git`, the engine's state root or a deny root, and answer a refused path with `denied` and a fixed message naming the rule, never the resolved absolute path.

- GIVEN a refused path WHEN the outcome is returned THEN its message names the rule and not the absolute path

### THS-B1 Path outside refused

WHEN `read_file` is called with `../etc/passwd`, or with a symlink in the workdir pointing outside it THE host SHALL deny the call and read nothing.

- GIVEN `src/a.py` WHEN read or written THEN both are allowed
- GIVEN `.git/config` WHEN read or written THEN the read is allowed and the write denied
- GIVEN `../x` or a link to outside WHEN read or written THEN both are denied

### THS-B8 Read-only offer

WHEN a host is built THE host SHALL offer only the tools whose capability was passed in, a judge host being built with read-only capabilities and catalogued MCP views only, and answer a call to any other name with `denied`.

- GIVEN a judge host with `read` and `list` WHEN `write_file` is called THEN it is denied and nothing is written

### THS-B2 Exact edit

WHEN `edit_file` runs on a file where `old` occurs other than exactly once and `all` is not set THE host SHALL leave the file unchanged and return `ok = false` naming the count.

- GIVEN a file where `old` occurs twice WHEN `edit_file` runs without `all` THEN the file is unchanged and the outcome names 2

### THS-B9 Outputs capped

WHEN the host returns an outcome THE host SHALL return UTF-8 with invalid bytes replaced, cut to 64 KB with a marker giving the size cut, and a one-line note instead of the content of a binary file.

- GIVEN a 100 KB text file read whole WHEN returned THEN the content is cut at 64 KB with a marker

### THS-B10 Command rules

WHEN `run_command` runs THE host SHALL run `argv` only when its leading items equal a declared prefix split on spaces and no item holds `;`, `&`, `|`, `` ` ``, `$(`, `>`, `<` or a newline, as a list and never through a shell, in the workdir with any path item confined as in THS-B7.

- GIVEN a declared prefix and an item that names a path outside the workdir WHEN called THEN nothing runs and the outcome is a denial

### THS-B14 Command environment and limits

WHEN `run_command` runs a command THE host SHALL give it the worker's environment minus the executor's credential variables ([SEC-B13](security.spec.md)), at most 600 s (operator-configurable) and 64 KB of combined output, and kill its process group on expiry with `error_kind = timeout`.

- GIVEN a command running past its limit WHEN the limit passes THEN its process group is killed and the outcome is `timeout`

### THS-B15 Command result

WHEN a command ends THE host SHALL return its exit code, then its standard output and standard error, a non-zero exit being `ok = false` and not a denial.

- GIVEN a command that exits 1 WHEN returned THEN the outcome is `ok = false` and not denied

### THS-B3 Declared prefix only

WHEN `run_command` is called with declared prefixes `pytest` and `git status` THE host SHALL run only matching argv.

- GIVEN `["pytest", "-q"]` or `["git", "status", "--short"]` WHEN called THEN it runs
- GIVEN `["git", "push"]` WHEN called THEN it is denied
- GIVEN `["pytest", "-q;rm"]` WHEN called THEN it is denied for the metacharacter

### THS-B11 MCP client

WHEN a step or judge declares an MCP tool THE host SHALL start each declared local (stdio) server from the engine's MCP file as a child of the worker, list its tools once, offer only the declared ones (for a judge, through the catalog's view classification), forward calls, support no remote server in this release, and when a server fails to start offer none of its tools and record a note on `session_started`.

- GIVEN a declared server that fails to start WHEN the session starts THEN its tools are not offered and `session_started` carries a note

### THS-B4 Never raises

WHEN a tool is called with any input, including invalid JSON types, an unreadable file or a server that crashed THE host SHALL return an outcome and let the loop continue, a missing or unreadable file being `ok = false` with `error_kind` `not_found` or `io`.

- GIVEN a missing file WHEN `read_file` is called THEN the outcome is `not_found` and nothing raises

## Acceptance criteria

- THS-AC1 (THS-B1, THS-B3, THS-B7, THS-B10): The scenarios of THS-B1 and THS-B3 pass on POSIX and Windows
- THS-AC2 (THS-B4, THS-B6, THS-B9, THS-B12, THS-B13): Fuzzed inputs never raise from a call, and every outcome is capped
- THS-AC3 (THS-B10): No code path runs a command through a shell, by a source scan
- THS-AC4 (THS-B8, THS-B5): A judge host offers no write, edit or command tool for any view set, and the order of tools is fixed
- THS-AC5 (THS-B2, THS-B11): An inexact edit changes nothing, and a server that fails to start offers no tool
- THS-AC6 (THS-B14, THS-B15): A command past its limit has its process group killed with `timeout`, and a command that exits 1 returns `ok = false`, not a denial

## Open questions

- Offer remote MCP servers through the host, with the same catalog classification? Deferred with remote MCP in steps ([ADR `scope-of-planned-work`](../adr/scope-of-planned-work.adr.md)). Owner: engine owner.
