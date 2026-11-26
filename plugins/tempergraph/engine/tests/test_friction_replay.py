"""A replay of five runs: causes a judge attributes in one run only file nothing (SIL-AC34, SIL-AC35)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.executors.standins import answer, standin
from tempergraph.improve import child, params, record
from tempergraph.improve.codehost import MemoryCodeHost

from .test_loop_child import friction_ticket, loop_rows
from .test_run import registry

ONE_RUN = ("agent_decided:escalation", "check_fail:draft", "retries_spent")
EVERY_RUN = "slow_step"
CAUSES = (*ONE_RUN, EVERY_RUN)


def fp(cause: str) -> str:
    return record.fingerprint("workflow", "demo", cause, "draft")


def scripted(run: int) -> Any:
    """Cause i of the three is attributed in run i + 2 only (runs 2 to 4); the fourth cause in every run, at 0.5."""

    def reply(req: Any) -> Any:
        rows = [{"fingerprint": fp(c), "attributed": i == run - 2, "confidence": 0.5} for i, c in enumerate(ONE_RUN)]
        rows.append({"fingerprint": fp(EVERY_RUN), "attributed": True, "confidence": 0.5})
        return answer("```json\n" + json.dumps({"findings": rows}) + "\n```", session_id="loop")

    return reply


def test_a_cause_attributed_in_one_run_files_nothing_and_a_cause_in_every_run_files_once() -> None:  # SIL-AC34, SIL-AC35
    import tempfile

    root = Path(tempfile.mkdtemp()) / ".tempergraph"
    host = MemoryCodeHost()
    reg = registry(standin("claude", judges=[scripted(n) for n in range(1, 6)]))
    ones = {fp(c) for c in ONE_RUN}
    outs = [child.process(friction_ticket(root, n, CAUSES), reg, host) for n in range(1, 6)]
    for n, out in enumerate(outs, start=1):  # the three causes: nothing filed or commented at any exit
        for r in out["results"]:
            if r.get("fingerprint") in ones:
                assert r["op"] == "recorded", (n, r)
    ops = [[r["op"] for r in o["results"] if r.get("fingerprint") not in ones] for o in outs]
    assert ops[0] == ops[1] == ["recorded"] and ops[2] == ["filed"]
    assert ops[3] == ["commented"] and ops[4] == ["comment_capped"]
    assert len(host.issues) == 1 and len(host.comments) <= params.value("seen_again.max_per_issue_per_day")
    for issue in host.issues:
        assert not any(c in issue["body"] for c in ONE_RUN)
    rows = [r for n in range(1, 6) for r in loop_rows(root, f"F-{n}")]
    assert len([r for r in rows if r["kind"] == "issue_commented"]) == 1
    assert len([r for r in rows if r["kind"] == "loop_result" and r["op"] == "comment_capped"]) == 1
