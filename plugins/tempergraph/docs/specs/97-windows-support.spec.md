---
title: Windows support
type: component
status: review
prefix: WIN
adrs: [0128]
---

# Windows support

## 1. Overview

From release 2 the engine runs natively on Windows 10 1809 or later and Windows Server 2019 or later, where Claude Code itself runs ([R-132](../research/R-132-running-on-windows.rsrch.md) F2). In WSL the engine is a Linux program and nothing here applies. This spec lists each place where Windows needs its own rule; every other spec's behaviour is unchanged ([ADR-0128](../adr/0128-windows-is-supported-natively-with-job-objects-and-probes-before-judges.adr.md)).

Judges run on Windows only after the three probes of §2.4 pass: judge isolation rests on CLI facts nobody has checked there yet, so until then preflight refuses a judge session on Windows (contract C15).

## 2. Contract

### 2.1 Platform rules

| Part | Rule on Windows | Owner spec |
|---|---|---|
| Session lifetime | Every session starts suspended inside a job object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, then resumes; the engine holds the job handle, so the session tree ends when the engine ends, however it ends. A timeout or `stop --now` terminates the job. A graceful stop sends `CTRL_BREAK_EVENT` to the session's process group first | [EXI-B5](10-executor-interface.spec.md), [RCT](32-run-control.spec.md) |
| Run lock | `msvcrt.locking` on one byte of the lock file; readers never read the lock file's bytes | [DUR](09-durability-and-resume.spec.md) |
| Owner-only files | The state root and the home folder get an ACL granting the current user only (inheritance off) when created outside the user profile; inside it, the profile's ACL stands. A failed ACL is a warning, recorded | [LOS §2.1](33-local-observability-store.spec.md) |
| Atomic replace | `os.replace` retried up to 5 times over 1 s on `PermissionError` (a scanner holding the file); then the error | [LOS](33-local-observability-store.spec.md) |
| Shim | `%USERPROFILE%\.tempergraph\bin\tempergraph.cmd` calls `<env>\Scripts\python.exe -X utf8 -m tempergraph`; the `PATH` entry goes into the user's environment (`HKCU\Environment`), and the install prints that a new terminal is needed | [UPD §2.2, §2.7](60-engine-update.spec.md) |
| Interpreter resolution | `Scripts\python.exe` in place of `bin/python` in every virtual-environment lookup | [WSP-B3](13-workspace-and-concurrency.spec.md) |
| Text comparison | Every engine comparison of file content (digests, stamps, diagram currency, prompt digests) normalizes `\r\n` to `\n` first | [VER](61-version-metadata.spec.md), [LIF](18-lifecycle-and-evals.spec.md) |
| Long paths | Preflight warns when `LongPathsEnabled` is not 1 or git's `core.longpaths` is not true, and refuses a worktree whose deepest tracked path would exceed 259 characters | [WTR](82-worktree-mode.spec.md) |
| Host-speed probe | `powershell -NoProfile -Command exit` against `powershell -Command exit` | [ARC](56-audit-rule-catalog.spec.md) `slow-host` |
| Shell of a step | The executor records which shell the CLI used (Git Bash or PowerShell, [ECC](11-executor-claude-code.spec.md)); a declared command prefix is resolved the same on both, and a workflow may declare `shell: bash` to refuse a machine without Git Bash at preflight | [CHK §2.2](75-check-contract-and-command-runs.spec.md) |
| Schedules | The portable loop and the host adapter work; the Task Scheduler adapter is release 3 with the other OS adapters | [TCK](84-schedule-ticks-and-unattended-fires.spec.md) |

### 2.2 Supported platforms

| Platform | Release 2 |
|---|---|
| macOS, Linux | as release 1 |
| Windows 10 1809+, Server 2019+, native | this spec |
| WSL 2 | as Linux, with the engine and `claude` both inside WSL |
| Windows with the engine native and `claude` in WSL, or the reverse | refused at preflight: one process tree cannot span both |

### 2.3 Preflight on Windows

Preflight adds `platform: {os, version, long_paths, core_longpaths, git_bash}` to its record and refuses any judge session until the probes of §2.4 are recorded as passed for the pinned CLI version.

### 2.4 Probes

| Probe | What it checks | Pass |
|---|---|---|
| P-WIN-1 | `claude -p` streams the same `stream-json` event kinds as on POSIX for a step and a judge fixture | Identical kinds and fields, modulo paths |
| P-WIN-2 | `--tools`, `--disallowedTools` and `--permission-mode dontAsk` restrict a judge session on Windows as ECC-B3 says, with and without Git Bash | No write and no shell tool runs in either case |
| P-WIN-3 | Children the CLI starts (Git Bash, PowerShell, MCP servers) stay inside the engine's job object | Killing the engine ends every child (process list after 5 s) |

## 3. Behaviours

**WIN-B1 Sessions end with the engine.** Given a running step on Windows whose session started a long shell command, when the engine process is killed from Task Manager, then within 5 s no process of that session remains.

**WIN-B2 A scanner holding a file.** Given a run whose `exit.json` is held open by another process for 300 ms, when the engine replaces it, then the replace succeeds on a retry and no error is recorded.

**WIN-B3 Judges wait for the probes.** Given a Windows machine with no P-WIN-2 result for the installed CLI, when a run reaches a judged gate, then preflight has already refused the run with exit 2, naming the probe and its command.

## 4. Error conditions

| Condition | Result |
|---|---|
| Job object cannot be created or assigned | Preflight refusal, exit 2: a session that could outlive the engine is never started |
| Shim's environment missing | Exit 127 with the reinstall command, as on POSIX |
| A path over the limit without long paths | Refusal naming the path and the two settings that fix it |

## 5. Design notes

- Refusing judges until the probes pass follows contract C15: a capability not shown is a refusal, never a silent downgrade.

## 6. Acceptance criteria

- [ ] WIN-AC-1 The engine's offline suite passes on a Windows runner, with Windows-only tests for every row of §2.1 that has code.
- [ ] WIN-AC-2 WIN-B1 to WIN-B3 hold on a Windows machine with scripted executors that start child processes.
- [ ] WIN-AC-3 Live: P-WIN-1 to P-WIN-3 recorded on the owner's or a test Windows machine, never faked.

## Open questions

| Question | Owner | Default |
|---|---|---|
| Native Windows, or WSL only? | Owner | Native, with WSL as Linux |
| Refuse or warn without long paths? | Owner | Warn; refuse only a path over the limit |

## References

[EXI](10-executor-interface.spec.md) · [ECC](11-executor-claude-code.spec.md) · [LOS](33-local-observability-store.spec.md) · [UPD](60-engine-update.spec.md) · [R-132](../research/R-132-running-on-windows.rsrch.md)
