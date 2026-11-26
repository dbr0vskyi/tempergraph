"""A declared artifact's path and a gate's pattern stay out of what the loop keeps (SRV-B45, SRV-AC44, SRV-AC1; task
AC 8). The canary sits in both; the digest, the findings, `loop.jsonl` and an issue body hold counts, enums and cause
codes only. Nothing here names a workflow package."""

from __future__ import annotations

import json
from pathlib import Path

from tempergraph.constants import ExitCode
from tempergraph.executors.standins import standin
from tempergraph.improve import filing
from tempergraph.improve.codehost import MemoryCodeHost
from tempergraph.improve.filing import Candidate, Outbox, decide
from tempergraph.improve.record import read_findings
from tempergraph.store.layout import run_dir, state_root_path

from .test_judge_changed_paths import judge_digest, judge_run
from .test_judge_read_share import build_unit, flow_of, opened, writer
from .test_run import go

CANARY = "zebra-canary-77"


def test_a_canary_in_an_artifact_path_and_a_gate_pattern_reaches_nothing_the_loop_keeps(repo: Path,
                                                                                        tmp_path: Path) -> None:  # SRV-AC44, SRV-AC1, AC 8
    notes = f"{CANARY}-notes.md"
    spec = flow_of({"build": build_unit(f"{CANARY}-out/**", produces={"notes": "file"})})
    steps = [writer(notes, f"{CANARY}-out/a.md", "other.md", artifact=f"notes: {notes}")]
    ex = standin("claude", steps=steps, judges=[opened(notes)])
    assert go(repo, ex, spec, task="P-1").exit_code is ExitCode.FINISHED
    root = state_root_path(repo)

    d = judge_digest(repo, "P-1", "build.1.judge")
    assert d["changed_total"] == 1 and d["changed_read"] == 0
    base = judge_run(repo, "P-1", "build.1.judge")["changed_base"]
    assert base and base not in json.dumps(d)  # SRV-AC1: no commit id in a digest
    assert CANARY not in json.dumps(d)

    findings = read_findings(root, "demo", "P-1")
    assert any(f["cause"] == "judge_unread_pass" for f in findings)
    assert CANARY not in json.dumps(findings)

    loop = run_dir(root, "demo", "P-1") / "loop.jsonl"
    assert CANARY not in (loop.read_text() if loop.exists() else "")

    host = MemoryCodeHost()
    for f in findings:
        filing.file([decide(Candidate(finding=f, confidence=0.9, attributed=True), [], "team/notes")], host,
                    Outbox.at(tmp_path))
    assert all(CANARY not in str(i["body"]) for i in host.issues)
