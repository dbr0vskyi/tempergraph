"""Launcher-owned workspace paths: excluded from guard fingerprint and changed_paths (EXI-B30, GRD-AC7).

Tests:
- GRD-AC7 / EXI-B30: a launcher-owned path that changes during a judge session does not discard the guard.
- EXI-B30: a changed path that is NOT launcher-owned still discards the guard (unchanged behaviour).
- EXI-B30: filter_owned_changed_paths removes owned prefixes and keeps unowned ones (CHK-B10).
- EXI-B30: _filter_owned strips only matching status lines from a fingerprint.
"""

from __future__ import annotations

from dataclasses import replace

from tempergraph.contracts import Capabilities, ToolCall, ViewSet
from tempergraph.git import Fingerprint
from tempergraph.run.guard import _filter_owned, filter_owned_changed_paths, guard

# ---------------------------------------------------------------------------
# Helpers

def _caps(**kw: object) -> Capabilities:
    base = Capabilities(name="test", binds_aliases=frozenset({"medium"}),
                        reports_actions=True, restricts_judge_tools=True, prompt_off_argv=True)
    return replace(base, **kw)


def _fingerprint(head: str = "abc", status: str = "") -> Fingerprint:
    return Fingerprint(head=head, status=status)


VIEWS = ViewSet(tools=("Read",))
CALLS = [ToolCall(name="Read", ok=True)]


# ---------------------------------------------------------------------------
# GRD-AC7, EXI-B30: guard ignores launcher-owned path changes

def test_guard_ignores_owned_path_change() -> None:
    """GRD-AC7 / EXI-B30: a launcher-owned path that appears after the session does not discard the guard."""
    before = _fingerprint(head="abc", status="")
    # simulate the launcher creating .codemie/ during the judge session
    after = _fingerprint(head="abc", status="?? .codemie/session.json")
    caps = _caps(launcher_owned_paths=(".codemie/",))
    result = guard(VIEWS, CALLS, before, after, workspace_mode="worktree",
                   step_session_id="s-step", judge_session_id="s-judge",
                   reports_actions=caps.reports_actions,
                   launcher_owned_paths=caps.launcher_owned_paths)
    assert result.status == "clean"


def test_guard_discards_non_owned_path_change() -> None:
    """EXI-B30: an unowned path change still discards the judge in worktree mode."""
    before = _fingerprint(head="abc", status="")
    after = _fingerprint(head="abc", status="?? src/surprise.py")
    caps = _caps(launcher_owned_paths=(".codemie/",))
    result = guard(VIEWS, CALLS, before, after, workspace_mode="worktree",
                   step_session_id="s-step", judge_session_id="s-judge",
                   reports_actions=caps.reports_actions,
                   launcher_owned_paths=caps.launcher_owned_paths)
    assert result.status == "discarded"


def test_guard_no_owned_paths_behaviour_unchanged() -> None:
    """EXI-B30: when launcher_owned_paths is empty the guard works as before."""
    before = _fingerprint(head="abc", status="")
    after = _fingerprint(head="abc", status="?? .codemie/session.json")
    result = guard(VIEWS, CALLS, before, after, workspace_mode="worktree",
                   step_session_id="s-step", judge_session_id="s-judge")
    assert result.status == "discarded"


# ---------------------------------------------------------------------------
# _filter_owned: strips matching lines from status

def test_filter_owned_strips_matching_lines() -> None:
    fp = _fingerprint(status="?? .codemie/x\n?? src/a.py")
    filtered = _filter_owned(fp, [".codemie/"])
    assert ".codemie/" not in filtered.status
    assert "src/a.py" in filtered.status


def test_filter_owned_does_not_touch_manifest_fingerprints() -> None:
    fp = Fingerprint(head="", status="digest", manifest=True)
    assert _filter_owned(fp, [".codemie/"]) is fp


def test_filter_owned_empty_owned_returns_same() -> None:
    fp = _fingerprint(status="?? anything")
    assert _filter_owned(fp, []) is fp


# ---------------------------------------------------------------------------
# filter_owned_changed_paths: removes owned prefixes (CHK-B10)

def test_filter_owned_changed_paths_removes_owned() -> None:
    paths = (".codemie/session.json", "src/a.py", ".codemie/cache")
    result = filter_owned_changed_paths(paths, [".codemie/"])
    assert result == ("src/a.py",)


def test_filter_owned_changed_paths_empty_owned_unchanged() -> None:
    paths = (".codemie/session.json", "src/a.py")
    assert filter_owned_changed_paths(paths, []) == paths
