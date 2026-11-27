# Windows support

## Purpose

The engine is to run natively on Windows 10 1809 or later and Windows Server 2019 or later, where Claude Code itself runs ([research `running-on-windows`](../research/running-on-windows.rsrch.md) F2). In WSL the engine is a Linux program and nothing here applies. This spec lists each place where Windows needs its own rule; every other spec's behaviour is unchanged ([ADR `windows-is-supported-natively-with-job-objects`](../adr/windows-is-supported-natively-with-job-objects.adr.md)). Judges run on Windows only after three probes pass: judge isolation rests on CLI facts nobody has checked there yet, so until then preflight refuses a judge session on Windows (OVR-B17). Operators on Windows and the executor, durability, store and install specs depend on it; design notes are in [research `rationale-carried-from-the-engine-specs`](../research/rationale-carried-from-the-engine-specs.rsrch.md).

## Depends on

- `audit-rule-catalog.spec.md`: audit rule catalog
- `check-contract-and-command-runs.spec.md`: command resolution (CHK-B11)
- `durability-and-resume.spec.md`: durability and resume
- `engine-update.spec.md`: engine environments and the switch (UPD-B11); first-install launcher (UPD-B18)
- `executor-claude-code.spec.md`: claude code executor
- `executor-interface.spec.md`: lifetime (EXI-B5)
- `lifecycle-and-evals.spec.md`: lifecycle and evals
- `local-observability-store.spec.md`: state root top level (LOS-B7)
- `observability-and-cost.spec.md`: observability and cost
- `run-control.spec.md`: run control
- `schedule-ticks-and-unattended-fires.spec.md`: schedule ticks and unattended fires
- `version-metadata.spec.md`: version metadata of the engine and of workflows
- `workspace-and-concurrency.spec.md`: interpreter in a worktree (WSP-B3)
- `worktree-mode.spec.md`: worktree mode

## Behaviours

### WIN-B1 Sessions end with the engine

WHEN a session starts on Windows THE engine SHALL start it suspended inside a job object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, then resume it, holding the job handle so the session tree ends when the engine ends however it ends; terminate the job on a timeout or `stop --now`; send `CTRL_BREAK_EVENT` to the session's process group first on a graceful stop ([EXI-B5](executor-interface.spec.md), [RCT](run-control.spec.md)); and refuse at preflight with exit 2 when the job object cannot be created or assigned, never starting a session that could outlive the engine.

- GIVEN a running step whose session started a long shell command WHEN the engine process is killed from Task Manager THEN within 5 s no process of that session remains

### WIN-B2 A scanner holding a file

WHEN an atomic replace fails on Windows with `PermissionError` THE engine SHALL retry `os.replace` up to 5 times over 1 s before raising the error ([LOS](local-observability-store.spec.md)).

- GIVEN `exit.json` held open by another process for 300 ms WHEN the engine replaces it THEN the replace succeeds on a retry and no error is recorded

### WIN-B3 Judges wait for the probes

WHEN preflight runs on Windows THE engine SHALL add `platform: {os, version, long_paths, core_longpaths, git_bash}` to its record and refuse with exit 2 any run that would start a judge session until P-WIN-1 (`claude -p` streams the same `stream-json` event kinds and fields as on POSIX, modulo paths), P-WIN-2 (`--tools`, `--disallowedTools` and `--permission-mode dontAsk` restrict a judge session as [ECC](executor-claude-code.spec.md) says, with and without Git Bash, no write and no shell tool running) and P-WIN-3 (children the CLI starts, such as Git Bash, PowerShell and MCP servers, stay inside the job object, killing the engine ending every child within 5 s) are recorded as passed for the pinned CLI version, naming the probe and its command.

- GIVEN no P-WIN-2 result for the installed CLI WHEN a run with a judged gate starts THEN preflight refuses it with exit 2 naming P-WIN-2

### WIN-B4 Locks, owner-only files and appends

WHEN the engine locks, creates or appends to its files on Windows THE engine SHALL take the run lock with `msvcrt.locking` on one byte of the lock file, readers never reading its bytes ([DUR](durability-and-resume.spec.md)); give the state root and the home store an ACL granting the current user only, inheritance off, when created outside the user profile, the profile's ACL standing inside it, a failed ACL being a recorded warning ([LOS-B7](local-observability-store.spec.md)); and take every append to a shared file (ledger, outbox, run log) under that byte lock ([OBS](observability-and-cost.spec.md)).

- GIVEN a state root created under `D:\work` WHEN its ACL is read THEN only the current user is granted access

### WIN-B5 Shim and interpreter

WHEN the engine is installed on Windows THE install SHALL write `%USERPROFILE%\.tempergraph\bin\tempergraph.cmd`, calling `<env>\Scripts\python.exe -X utf8 -m tempergraph`, put the `PATH` entry in the user's environment (`HKCU\Environment`) and print that a new terminal is needed ([UPD-B11](engine-update.spec.md), [UPD-B18](engine-update.spec.md)); every virtual-environment lookup SHALL use `Scripts\python.exe` in place of `bin/python` ([WSP-B3](workspace-and-concurrency.spec.md)); and a shim whose environment is missing SHALL exit 127 with the reinstall command, as on POSIX.

- GIVEN a shim whose environment folder was deleted WHEN `tempergraph status` runs THEN it exits 127 naming the reinstall command

### WIN-B6 Text and paths

WHEN the engine compares file content or prepares a worktree on Windows THE engine SHALL normalize `\r\n` to `\n` before every comparison of digests, stamps, diagram currency and prompt digests ([VER](version-metadata.spec.md), [LIF](lifecycle-and-evals.spec.md)); warn at preflight when `LongPathsEnabled` is not 1 or git's `core.longpaths` is not true; and refuse a worktree whose deepest tracked path would exceed 259 characters, naming the path and the two settings that fix it ([WTR](worktree-mode.spec.md)).

- GIVEN a prompt checked out with CRLF line endings WHEN its digest is compared with the stamp THEN it matches

### WIN-B7 Shells, probes and schedules

WHEN steps, audits and schedules run on Windows THE engine SHALL record which shell the CLI used for a step (Git Bash or PowerShell, [ECC](executor-claude-code.spec.md)), resolve a declared command prefix the same on both, and refuse at preflight a machine without Git Bash for a workflow that declares `shell: bash` ([CHK-B11](check-contract-and-command-runs.spec.md)); measure the host-speed probe of the `slow-host` audit rule ([ARC](audit-rule-catalog.spec.md)) as `powershell -NoProfile -Command exit` against `powershell -Command exit`; and run the portable schedule loop and the host adapter, the Task Scheduler adapter coming with the other OS adapters ([TCK](schedule-ticks-and-unattended-fires.spec.md)).

- GIVEN a workflow with `shell: bash` on a machine without Git Bash WHEN preflight runs THEN it is refused

### WIN-B8 Supported platforms

WHEN preflight reads the platform THE engine SHALL support macOS and Linux as before, native Windows 10 1809 or later and Server 2019 or later by this spec, and WSL 2 as Linux with the engine and `claude` both inside WSL, and refuse the engine native with `claude` in WSL, or the reverse, because one process tree cannot span both.

- GIVEN a native engine whose `claude` resolves to a WSL path WHEN preflight runs THEN it is refused

## Acceptance criteria

- WIN-AC1 (WIN-B2, WIN-B4, WIN-B5, WIN-B6, WIN-B7, WIN-B8): The engine's offline suite passes on a Windows runner, with Windows-only tests for every rule that has code
- WIN-AC2 (WIN-B1, WIN-B2, WIN-B3): WIN-B1 to WIN-B3 hold on a Windows machine with scripted executors that start child processes
- WIN-AC3 (WIN-B3): Live: P-WIN-1 to P-WIN-3 recorded on the owner's or a test Windows machine, never faked

## Open questions

- Refuse or warn without long paths? Until answered: warn; refuse only a path over the limit. Owner: owner.
- Not built yet: native Windows is release 3 work (third-release plan R3-T9, after EC-4); only the byte-lock run lock exists; the probes have not run. Owner: engine owner.
