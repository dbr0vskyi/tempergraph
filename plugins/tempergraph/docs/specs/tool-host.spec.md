# Tool host

## Purpose

The tool host executes the client tools of the [Messages API executor](executor-messages-api.spec.md) inside its worker process ([ADR `engine-owned-tool-loop-for-the-messages-api`](../adr/engine-owned-tool-loop-for-the-messages-api.adr.md)). It offers one tool per capability name ([CON-B11](contracts.spec.md)) except `subagent` and the two web capabilities, which are server tools. It is deliberately small: every path stays in the workspace, every command is a declared prefix run as a list, and every output is capped. Its scope is fixed; a step that needs more runs on another executor. Search and list are pure Python so the host needs no external binary and behaves the same on every platform; besides check functions it is the only place where a command runs on the operator's machine for a model, so its command rules are those of [SEC](security.spec.md). The Messages API worker and every step and judge on that executor depend on it.

## Depends on

- `security.spec.md`: commands see no executor credentials (SEC-B13)

## Behaviours

### THS-B5 Tools offered

WHEN the host lists its tools THE host SHALL give each a name, a description stating its size caps so the model can page, and an input schema, in a fixed order: `read_file` (`path`, optional `offset` and `limit` in lines; numbered lines, at most 2000 lines and 256 KB per call), `search_files` (`pattern` as a regex, optional `path` and `glob`; at most 200 matches, each line cut at 300 characters), `list_files` (`glob`, optional `path`; sorted paths, at most 1000), `edit_file` (`path`, `old`, `new`, optional `all`), `write_file` (`path`, `content`; at most 1 MB), `run_command` (`argv`, a list of strings) and `mcp__<s>__<t>` with the server's schema.

- GIVEN the same capabilities twice WHEN the tools are listed THEN both lists are in the same order

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

WHEN `run_command` runs THE host SHALL run `argv` only when its leading items equal a declared prefix split on spaces and no item holds `;`, `&`, `|`, `` ` ``, `$(`, `>`, `<` or a newline, as a list and never through a shell, in the workdir with any path item confined as in THS-B7, with the worker's environment minus the executor's credential variables ([SEC-B13](security.spec.md)), for at most 600 s (operator-configurable) with 64 KB of combined output, killing the process group on expiry with `error_kind = timeout`, and return the exit code then standard output and standard error, a non-zero exit being `ok = false` and not a denial.

- GIVEN a command that exits 1 WHEN returned THEN the outcome is `ok = false` and not denied
- GIVEN a command running past its limit WHEN the limit passes THEN its process group is killed and the outcome is `timeout`

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
- THS-AC2 (THS-B4, THS-B6, THS-B9): Fuzzed inputs never raise from a call, and every outcome is capped
- THS-AC3 (THS-B10): No code path runs a command through a shell, by a source scan
- THS-AC4 (THS-B8, THS-B5): A judge host offers no write, edit or command tool for any view set, and the order of tools is fixed
- THS-AC5 (THS-B2, THS-B11): An inexact edit changes nothing, and a server that fails to start offers no tool

## Open questions

- Offer remote MCP servers through the host, with the same catalog classification? Deferred with remote MCP in steps ([ADR `scope-of-planned-work`](../adr/scope-of-planned-work.adr.md)). Owner: engine owner.
