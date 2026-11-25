"""Engine-wide constants: exit codes, schema versions, release, reserved words.

The exit-code table is the caller contract of CON-B12, CON-B13; ``tests/test_contract_tables.py`` checks it
against the table in ``docs/specs/contracts.spec.md`` (CON-AC6, CLI-AC4).
"""

from __future__ import annotations

from enum import IntEnum

ENGINE_VERSION = "0.2.0"
RELEASE = 2  # the release this engine builds (ADR `first-release-is-simple-trusted-workflows-on-one-machine`, ADR `release-two-adds-upgrade-ladders-judge-risk-and-complexity-routing`)
WORKFLOW_API = 1  # the declaration interface level (PKG-B13, VER-B8)
LOADS_WORKFLOW_API_FROM = 1
STORE_LAYOUT = 1  # LOS-B7, LOS-B8, LOS-B9 layout version


class ExitCode(IntEnum):
    """CON-B12, CON-B13 ``ExitCode``."""

    FINISHED = 0
    INTERNAL = 1
    USAGE = 2  # usage or preflight refusal, nothing spent or created
    PAUSED = 3  # paused for a person
    STOPPED = 4
    BUDGET_OR_INFRA = 5  # budget spent or infra failure
    ADVISORY = 6  # an advisory verb found issues at the level asked for
    NOT_INSTALLED = 127  # engine not installed (shim)


# Schema versions of persisted documents (CON-B14, CON-B1, CON-B15).
SCHEMA = {
    "run_log": 1,
    "status": 1,
    "findings": 1,
    "ledger": 1,
    "catalog": 1,
    "diagram_model": 1,
    "detail": 1,
    "activity": 1,
    "store_manifest": 1,
    "settings": 1,
    "lineage": 1,
    "package_manifest": 1,
    "outcome": 1,
    "facts": 1,
    "bindings": 1,
    "audit_report": 1,
    "proposal": 1,
    "trial": 1,
    "labels": 1,
    "stamp": 1,
    "registry": 1,
    "engine_pointers": 1,
}

# Verb words are reserved and refused as run input (CLI-B2, CLI-AC3).
RESERVED_VERBS = frozenset(
    {
        "run", "resume", "rerun", "config", "status", "events", "logs", "wait", "attention", "list",
        "graph", "report", "validate", "audit", "executors", "batch", "orchestrate", "schedule", "stop",
        "worktree", "update", "install", "workflows", "upgrade", "upgrade-check", "facts", "stats",
        "store", "hooks", "improve", "label", "labels", "evals", "supervision", "author", "blueprint",
        "literals", "scaffold", "outcome", "self-check",
    }
)

# Executor names are constants, registered in this order (EXI-B16, EXI-B17).
EXECUTOR_NAMES = ("claude", "agent-sdk", "messages-api", "antigravity")
SHIPPED_EXECUTORS = ("claude",)  # ADR `first-release-ships-the-claude-executor-only`: release 1 and 2 ship claude only

MISSING_MARKER = "⟨missing:{name}⟩"  # CON-B8
