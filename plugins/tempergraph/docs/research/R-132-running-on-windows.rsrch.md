# R-132 Running the engine on Windows

## Problem statement

Release 1 targets macOS and Linux ([ADR-0090](../adr/0090-first-release-is-simple-trusted-workflows-on-one-machine.adr.md) S3). Release 2 lists Windows ([R-130](R-130-release-two-readiness-and-gaps.rsrch.md) G2), and the owner asked on 2026-11-20 for research on it. The questions: which Windows failure modes the engine must answer, what the Claude Code CLI needs there, what in tempergraph's design and code is POSIX-only today, and what each needs on Windows.

## Sources consulted

| # | Source | Type | Where |
|---|---|---|---|
| S2 | Claude Code setup: Windows 10 1809+ or Server 2019+; native or in WSL; Git for Windows optional, it provides Git Bash for the Bash and Monitor tools; without it shell commands run through the PowerShell tool; in WSL `claude` is installed and launched inside the WSL terminal | Vendor documentation (fetched 2026-11-20) | [code.claude.com/docs/en/setup](https://code.claude.com/docs/en/setup) |
| S3 | Microsoft, "Maximum path length limitation": `MAX_PATH` is 260; since Windows 10 1607 long paths need both `LongPathsEnabled = 1` under `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem` and a `longPathAware` application manifest | Vendor documentation | [learn.microsoft.com](https://learn.microsoft.com/windows/win32/fileio/maximum-file-path-limitation) |
| S4 | Git for Windows, "Git cannot create a file or directory with a long path": `core.longpaths` | Vendor documentation | [gitforwindows.org](https://gitforwindows.org/git-cannot-create-a-file-or-directory-with-a-long-path.html) |
| S5 | Job objects with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, as used by build tools (rustc's bootstrap, uv) to end a whole process tree with the parent | Open-source code | [rust bootstrap job.rs](https://doc.rust-lang.org/stable/nightly-rustc/src/bootstrap/utils/job.rs.html), [uv-windows job.rs](https://docs.rs/crate/uv-windows/0.0.45/source/src/job.rs) |
| S6 | Engine code on `main`: `executors/launcher.py` (process group on POSIX; on Windows `CREATE_NEW_PROCESS_GROUP`, `taskkill /T` on a hard stop, "the job-object form is the next step"), `durability/lock.py` (`fcntl` or `msvcrt.locking`), `install/shim.py` (a `/bin/sh` shim, `bin/python`), `chmod` calls guarded by `os.name`, `shell_timing` (`$SHELL`) | Code | `plugins/tempergraph/engine/src/tempergraph/` |
| S7 | This design: EXI-B5 (children end with the engine), SEC-B5, SEC-B6 (argv constants, prompt on stdin), LOS-B7, LOS-B8, LOS-B9 (owner-only modes), UPD-B11, UPD-B12, UPD-B13, UPD-B18, UPD-B19 (shim, `PATH` block), TCK (OS adapters), WTR (worktree names), CHK (command resolution), ARC `slow-host` | Design set | [specs](../specs/overview.spec.md) |

## Key findings

### F1 Known Windows failure modes, and the rules that answer them `inferred`

On Windows a session's process tree outlives the engine unless a job object ties it to the engine. A command line is capped near 32,000 characters. Appends from several processes to one file lose lines unless each append takes a short byte lock, and threads writing one log corrupt its lines unless each record is locked. A timeout that ends only the first process leaves its children holding its pipes, and a hard kill gives exit 1 with no output. CRLF checkouts break byte comparison of text files. A running program that loads a compiled library locks the file, so pip cannot replace it. A saturated host times attempts out. Each is answered by a rule tempergraph already has or must keep: job objects, prompt on stdin, locked appends, locked log records, whole-tree kills, digests instead of byte comparison, an updater that loads no compiled library.

### F2 Claude Code runs natively on Windows, and its shell differs `confirmed`

Native Windows is supported from Windows 10 1809. With Git for Windows the Bash tool uses Git Bash; without it shell commands go through the PowerShell tool (S2). A workflow's `shell` capability and its declared command prefixes ([CHK-B11](../specs/check-contract-and-command-runs.spec.md)) therefore meet a different shell per machine. In WSL, Claude Code is a Linux program, and the engine should run inside WSL too.

### F3 What is POSIX-only in tempergraph today `confirmed`

| Part | Today | Windows need |
|---|---|---|
| Session lifetime (EXI-B5) | Process group; Windows uses a new process group and `taskkill /T` on a hard stop | A job object with kill-on-close, so a crashed engine still ends its sessions (F1, S5) |
| Run lock | `msvcrt.locking` on one byte | Works; locks are mandatory on Windows, so readers of the lock file must not expect to read it |
| Owner-only files (LOS-B7, LOS-B8, LOS-B9) | `chmod 0700/0600`, skipped off POSIX | The user profile's default ACL is owner-only; a state root outside the profile needs an explicit ACL (`icacls`), or a warning |
| Shim (UPD-B11, UPD-B12, UPD-B13) | `/bin/sh` script calling `<env>/bin/python` | A `tempergraph.cmd` calling `<env>\Scripts\python.exe`; `PATH` set in the user's environment registry key, not a shell profile |
| Atomic replace | `os.replace` | Works on NTFS but fails with `PermissionError` while another process (often antivirus) holds the target; needs a short retry |
| Host-speed probe (ARC `slow-host`) | `$SHELL -lc true` | `powershell -NoProfile -Command exit` against `-Command exit` with the profile |
| Paths | POSIX assumptions in tests | 260-character limit unless long paths are on (S3, S4); worktrees beside the repository add depth; CPython declares `longPathAware`, but git needs `core.longpaths` |
| Line endings | — | `core.autocrlf` changes text files; every engine comparison of file content must use digests over normalized newlines |
| Schedules (TCK) | Portable loop and host adapter in release 2 | The portable loop works; the Task Scheduler adapter is release 3 with the OS adapters |
| Console | — | UTF-8 must be forced for the engine's own output (`PYTHONUTF8=1` in the shim) |

### F4 Unknowns that need a probe `uncertain`

- Whether `claude -p` on native Windows streams the same `stream-json` events and honours `--tools`, `--disallowedTools` and `--permission-mode` exactly as on POSIX (the judge's restriction rests on them, [ECC](../specs/executor-claude-code.spec.md)).
- Whether a session's own children (Git Bash, PowerShell, MCP servers) join the engine's job object when Claude Code starts them, or break away.
- How `--bare` judge sessions find Git Bash.

## Conclusions

1. Windows support is a set of bounded changes, most of them answers to known failure modes (F1): job objects, a `.cmd` shim, ACLs, replace retries, digests over normalized newlines, a PowerShell speed probe, long-path checks and UTF-8 output.
2. Native Windows is the target; WSL is Linux and needs nothing new.
3. Three facts about the CLI on Windows need live probes before any judge runs there, because judge isolation rests on them.
4. Until those probes pass, preflight on Windows should refuse judge sessions it cannot prove restricted, by OVR-B17.

## Open questions

| Question | Who answers | Default until answered |
|---|---|---|
| Is native Windows a release 2 target, or WSL only? | Owner | Native, with WSL working as Linux |
| Must preflight require long paths on (registry and `core.longpaths`), or only warn? | Owner | Warn, and refuse a worktree whose deepest tracked path would pass 260 characters |
| Is there a Windows machine for the probes? | Owner | Probes P-WIN-1 to P-WIN-3 stay pending, never faked |
