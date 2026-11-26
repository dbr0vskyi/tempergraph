"""A replay of five runs of a fixture workflow through the loop child, with a scripted judge and the memory code host:
the three causes the judge attributes in one run only file nothing at any exit, and the cause it attributes in every
run files one issue at the third exit and is commented within the bound (SIL-AC34, SIL-AC35; task AC 11)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child, params, record
from tempergraph.improve.codehost import MemoryCodeHost

from .test_loop_child import friction_ticket, loop_rows
from .test_run import registry

NOISE = ("agent_decided:escalation", "check_fail:suite", "retries_spent")  # the review's three causes
STEADY = "empty_output"  # the fourth cause, attributed in every run
CAUSES = (*NOISE, STEADY)
ATTRIBUTED_IN = {"agent_decided:escalation": 1, "check_fail:suite": 3, "retries_spent": 5}  # one run each


def scripted_judge() -> Any:
    """One reply for each exit, in order: the cause of each fingerprint in the prompt is answered by its run."""
    fps = {record.fingerprint("workflow", "demo", cause, "draft"): cause for cause in CAUSES}
    exits = {"n": 0}

    def reply(req: Any) -> Any:
        exits["n"] += 1
        run = exits["n"]
        asked = [ln.split("`")[1] for ln in req.prompt.splitlines() if ln.startswith("- `") and "cause" in ln]
        rows = [{"fingerprint": fp, "confidence": 0.5,
                 "attributed": fps[fp] == STEADY or ATTRIBUTED_IN.get(fps[fp]) == run} for fp in asked]
        return answer("```json\n" + json.dumps({"findings": rows}) + "\n```", session_id="loop")

    return reply


def test_five_runs_file_one_issue_for_the_steady_cause_and_nothing_for_the_others(
        tmp_path: Path) -> None:  # SIL-AC34, SIL-AC35, ISS-AC12 (task AC 11)
    root = tmp_path / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude", judges=[scripted_judge()] * 5))
    ops: list[list[tuple[str, str]]] = []
    for n in range(1, 6):
        out = child.process(friction_ticket(root, n, CAUSES), reg, host)
        causes_of = {record.fingerprint("workflow", "demo", c, "draft"): c for c in CAUSES}
        ops.append([(causes_of[r["fingerprint"]], r["op"]) for r in out["results"] if "fingerprint" in r])
        # at no exit does a cause of the three file or get a comment
        assert not [c for c, op in ops[-1] if c in NOISE and op in ("filed", "commented", "comment_capped")], n
        issues_now = len(host.issues)
        assert issues_now == (0 if n < 3 else 1), n  # one issue, at the third exit
    assert len(host.issues) == 1 and STEADY in host.issues[0]["body"]
    for cause in NOISE:  # no issue body or comment names a cause of the three
        assert all(cause not in text for text in [i["body"] for i in host.issues] + [c["body"] for c in host.comments])
    bound = int(params.value("seen_again.max_per_issue_per_day"))
    assert len(host.comments) == bound  # the fourth exit comments; the fifth is over the bound
    rows = [r for n in range(1, 6) for r in loop_rows(root, f"F-{n}")]
    assert len([r for r in rows if r["kind"] == "issue_commented"]) == bound
    capped = [r for r in rows if r["kind"] == "loop_result" and r.get("op") == "comment_capped"]
    assert len(capped) == 5 - 3 - bound and all("body" not in r and "text" not in r for r in capped)
