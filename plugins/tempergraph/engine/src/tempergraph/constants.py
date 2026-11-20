"""Engine-wide constants: exit codes, schema versions, release, reserved words.

The exit-code table is the caller contract of CON §2.9; ``tests/test_contract_tables.py`` checks it
against the table in ``docs/specs/01-contracts.spec.md`` (CON-AC-6, CLI-AC-4).
"""

from __future__ import annotations

from enum import IntEnum

ENGINE_VERSION = "0.0.1"
RELEASE = 1  # the release this engine builds (ADR-0090)
WORKFLOW_API = 1  # the declaration interface level (PKG §2.2, VER §2.2)
LOADS_WORKFLOW_API_FROM = 1
STORE_LAYOUT = 1  # LOS §2.1 layout version


class ExitCode(IntEnum):
    """CON §2.9 ``ExitCode``."""

    FINISHED = 0
    INTERNAL = 1
    USAGE = 2  # usage or preflight refusal, nothing spent or created
    PAUSED = 3  # paused for a person
    STOPPED = 4
    BUDGET_OR_INFRA = 5  # budget spent or infra failure
    ADVISORY = 6  # an advisory verb found issues at the level asked for
    NOT_INSTALLED = 127  # engine not installed (shim)


# Schema versions of persisted documents (CON §2.10).
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
}

# Verb words are reserved and refused as run input (CLI-B2, CLI-AC-3).
RESERVED_VERBS = frozenset(
    {
        "run", "resume", "rerun", "config", "status", "events", "logs", "wait", "attention", "list",
        "graph", "report", "validate", "audit", "executors", "batch", "orchestrate", "schedule", "stop",
        "worktree", "update", "install", "workflows", "upgrade", "upgrade-check", "facts", "stats",
        "store", "hooks", "improve", "label", "labels", "evals", "supervision", "author", "blueprint",
        "literals", "scaffold", "outcome", "self-check",
    }
)

# Executor names are constants, registered in this order (EXI §2.1).
EXECUTOR_NAMES = ("claude", "agent-sdk", "messages-api", "antigravity")
SHIPPED_EXECUTORS = ("claude",)  # ADR-0091: release 1 and 2 ship claude only

MISSING_MARKER = "⟨missing:{name}⟩"  # CON §2.2
