"""Review text reaches the run's local evidence and no other record (FBK-B15, FBK-AC7; task AC 5)."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from tempergraph.improve import child
from tempergraph.improve.record import read_findings
from tempergraph.store.layout import run_dir, state_root_path

from .conftest import SRC
from .test_carry import BRANCH, World, git, world  # noqa: F401  (the `world` fixture)
from .test_cli import cli
from .test_outcome_escape_finding import make_run, process, three_runs
from .test_pr_later import REPO, comment, commit, pr_host, segment, state
from .test_pr_later import review as pr_review

CANARY = "CANARY-7f3a91c2-do-not-leak"


def test_review_text_is_in_the_local_evidence_and_nowhere_else(tmp_path: Path) -> None:  # FBK-AC7, task AC 5
    root = state(tmp_path)
    host = three_runs(root, 3)  # three escapes file an issue through the host
    for i in (1, 2, 3):
        host.reviews[(REPO, i)] = [pr_review(text=f"{CANARY} review {i}")]
        host.review_comments[(REPO, i)] = [comment(text=f"{CANARY} comment {i}")]
        host.commits[(REPO, i)] = [commit("bbbbbbb2", ["a.py"])]
    out = process(root, host)
    assert "filed" in {r["op"] for r in out["results"]}  # the escape was read, found and filed
    assert all(read_findings(root, "demo", f"T-{i}") for i in (1, 2, 3))

    evidence = run_dir(root, "demo", "T-1") / "evidence" / "pull_request.jsonl"
    assert CANARY in evidence.read_text(encoding="utf-8")

    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "pull_request.jsonl"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert CANARY not in text, f"review text reached {path.relative_to(root)}"
    assert CANARY not in json.dumps(host.issues, default=str)
    for name in ("issue_comments", "comments", "thread", "labels", "pulls"):
        held = getattr(host, name, [])
        if callable(held):  # a read method of the host (BND-B12), not data it holds
            continue
        assert CANARY not in json.dumps(held, default=str), name
    assert CANARY not in json.dumps(out, default=str)
    assert child.loop_log(root, "demo", "T-0").exists()


def test_a_run_with_a_single_escape_leaks_nothing_either(tmp_path: Path) -> None:  # FBK-AC7, task AC 5
    root = state(tmp_path)
    make_run(root, "T-1", {"draft": ["a.py"]}, request="R1")
    host: Any = pr_host()
    host.reviews[(REPO, 1)] = [pr_review(text=CANARY)]
    host.review_comments[(REPO, 1)] = [comment(text=CANARY)]
    process(root, host)
    hits = [p for p in root.rglob("*") if p.is_file() and CANARY in p.read_text(encoding="utf-8", errors="ignore")]
    assert [p.name for p in hits] == ["pull_request.jsonl"]


def test_a_carried_thread_never_carries_the_pull_request_evidence(world: World) -> None:  # noqa: F811  FBK-AC7, task AC 5
    a = world.paused_on_a()
    root = state_root_path(a)
    segment(root, "t1", 1)
    host: Any = pr_host()
    host.reviews[(REPO, 1)] = [pr_review(text=CANARY)]
    host.review_comments[(REPO, 1)] = [comment(text=CANARY)]
    process(root, host)
    evidence = run_dir(root, "demo", "t1") / "evidence" / "pull_request.jsonl"
    assert CANARY in evidence.read_text(encoding="utf-8")  # the read wrote the canary into the local evidence

    code, _, err = cli(a, None, "carry", "push", "demo", "t1")
    assert code == 0, err
    assert not any(p.endswith("evidence/pull_request.jsonl") for p in world.state_paths())
    assert git(world.remote, "grep", "-c", "-e", CANARY, BRANCH, check=False) == ""


def test_the_filing_and_code_host_modules_import_no_pr_later() -> None:  # FBK-AC7, task AC 5
    for name in ("filing.py", "codehost.py"):
        tree = ast.parse((SRC / "improve" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "pr_later" not in (node.module or "") and all(a.name != "pr_later" for a in node.names), name
            elif isinstance(node, ast.Import):
                assert all("pr_later" not in a.name for a in node.names), name
