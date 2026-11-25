"""`GitFacts.base_head`: the commit the run's base branch points to now (CHK-B22, CHK-AC13)."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from tempergraph.contracts import CallableRef, CheckFinding, CheckResult, Criterion, GateSpec
from tempergraph.run import selfcheck
from tempergraph.run.check_worker import _context_from, context_doc
from tempergraph.run.checks import CheckContext, GitFacts, git_facts


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _commit(cwd: Path, name: str) -> str:
    (cwd / name).write_text(name + "\n")
    _git(cwd, "add", name)
    _git(cwd, "commit", "-q", "-m", name)
    return _git(cwd, "rev-parse", "HEAD")


def _run_branch(repo: Path, tmp_path: Path) -> tuple[Path, str]:
    """A worktree on a run branch started at `main`'s commit; returns it and that commit."""
    base = _git(repo, "rev-parse", "HEAD")
    work = tmp_path / "work"
    _git(repo, "worktree", "add", "-q", "-b", "tg/run", str(work), base)
    return work, base


def base_head_check(ctx: CheckContext) -> CheckResult:
    """A check that says the base head it was given."""
    head = ctx.git.base_head if ctx.git is not None else "none"
    return CheckResult(result="PASS", evidence=f"base_head={head}",
                       findings=[CheckFinding(status="pass", criterion="c1", place="-", message=f"base_head={head}")])


def test_base_head_is_the_commit_the_base_branch_points_to_now(repo: Path, tmp_path: Path) -> None:
    # CHK-AC13, AC 4
    work, base = _run_branch(repo, tmp_path)
    moved = _commit(repo, "b.txt")
    facts = git_facts(work, base, "main")
    assert facts is not None and facts.base == base and facts.base_head == moved != base
    assert git_facts(work, base, "").base_head == ""  # type: ignore[union-attr]  # a run in place
    assert git_facts(work, base).base_head == ""  # type: ignore[union-attr]
    assert git_facts(work, base, "no-such-branch").base_head == ""  # type: ignore[union-attr]
    assert git_facts(work, base, "--output=x").base_head == ""  # type: ignore[union-attr]  # an unsafe name


def test_the_earlier_calls_keep_their_result(repo: Path, tmp_path: Path) -> None:
    # CHK-AC13, AC 4
    work, base = _run_branch(repo, tmp_path)
    plain = git_facts(work)
    based = git_facts(work, base)
    assert plain is not None and based is not None
    assert plain.base == "" and plain.base_head == "" and plain.branch == "tg/run"
    assert based.base == base and based.base_head == "" and based.branch == "tg/run"


def test_a_remote_tracking_branch_is_read_with_no_fetch(repo: Path, tmp_path: Path) -> None:
    # CHK-AC13, AC 4
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "origin", "main")
    work, base = _run_branch(repo, tmp_path)
    moved = _commit(repo, "b.txt")
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "checkout", "-q", "-b", "other")
    _git(repo, "branch", "-q", "-D", "main")
    facts = git_facts(work, base, "main")
    assert facts is not None and facts.base_head == moved  # origin/main, the remote-tracking branch
    second = tmp_path / "second"
    subprocess.run(["git", "clone", "-q", "-b", "main", str(remote), str(second)], check=True)
    _git(second, "config", "user.email", "t@example.invalid")
    _git(second, "config", "user.name", "T")
    _commit(second, "c.txt")
    _git(second, "push", "-q", "origin", "main")
    again = git_facts(work, base, "main")
    assert again is not None and again.base_head == moved  # nothing was fetched


def test_the_check_worker_document_carries_base_head(repo: Path) -> None:
    # CHK-AC13, AC 4
    head = _git(repo, "rev-parse", "HEAD")
    ctx = CheckContext(unit="u", workdir=repo, request={}, git=GitFacts(base=head, base_head="abc123"))
    gate = GateSpec(criteria=(Criterion(text="-"),), check=CallableRef(module=__name__, qualname="base_head_check"))
    doc = context_doc(gate, ctx)
    assert doc["context"]["git"]["base_head"] == "abc123"
    back = _context_from(json.loads(json.dumps(doc)))
    assert back.git is not None and back.git.base_head == "abc123" and back.git.base == head


def test_the_check_worker_document_carries_visit_session(repo: Path) -> None:
    # AC 7, VSR-AC1
    gate = GateSpec(criteria=(Criterion(text="-"),), check=CallableRef(module=__name__, qualname="base_head_check"))
    calls = ({"name": "Read", "capability": "read", "target": "a.md", "ok": True},
             {"name": "Read", "capability": "read", "target": "b.md", "ok": False})
    ctx = CheckContext(unit="u", workdir=repo, request={}, visit_session=calls)
    back = _context_from(json.loads(json.dumps(context_doc(gate, ctx))))
    assert back.visit_session == calls
    none = _context_from(json.loads(json.dumps(context_doc(gate, CheckContext(unit="u", workdir=repo, request={})))))
    assert none.visit_session is None


def test_the_preview_reads_the_head_again_when_it_runs(repo: Path, tmp_path: Path) -> None:
    # CHK-AC13, AC 4
    work, base = _run_branch(repo, tmp_path)
    gate = GateSpec(criteria=(Criterion(text="-"),), check=CallableRef(module=__name__, qualname="base_head_check"))
    state_root = tmp_path / "state"

    def preview(base_branch: str | None) -> str:
        ctx = CheckContext(unit="u", workdir=work, request={}, git=GitFacts(base=base))
        kwargs = {} if base_branch is None else {"base_branch": base_branch}
        ticket = selfcheck.issue(state_root, gate, ctx, thread="t", limit=3, **kwargs)
        out = io.StringIO()
        assert selfcheck.run(state_root, ticket, out) == 0
        return out.getvalue()

    first = _git(repo, "rev-parse", "HEAD")
    assert f"base_head={first}" in preview("main")
    moved = _commit(repo, "b.txt")  # after the ticket's context was written
    ctx = CheckContext(unit="u", workdir=work, request={}, git=GitFacts(base=base))
    ticket = selfcheck.issue(state_root, gate, ctx, thread="t", limit=3, base_branch="main")
    later = _commit(repo, "c.txt")
    out = io.StringIO()
    assert selfcheck.run(state_root, ticket, out) == 0
    assert f"base_head={later}" in out.getvalue() and f"base_head={moved}" not in out.getvalue()
    assert json.loads(selfcheck.ticket_path(state_root, ticket).read_text())["base_branch"] == "main"
    assert "base_head=\n" in preview(None)  # a ticket issued with no base branch: the empty string
    ticket2 = selfcheck.issue(state_root, gate, ctx, thread="t", limit=3)
    assert json.loads(selfcheck.ticket_path(state_root, ticket2).read_text())["base_branch"] == ""
