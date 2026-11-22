"""Each review is paid for from what was reported in the run (SRV-B21, SRV-B25, SRV-AC9)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.executors.standins import answer, standin
from tempergraph.improve import digest, review
from tempergraph.store.layout import run_dir

from .test_run import registry
from .test_session_review import bash, rec, session, ticket

NONE_FOUND = "```json\n" + json.dumps({"observations": [], "conformance": [], "none_found": True}) + "\n```"


def build_run(root: Path, task: str, n: int, model: str = "claude-sonnet-5-5") -> None:
    """A fixture run of `n` one-attempt units, each with a captured session and its digest, in run order."""
    rd = run_dir(root, "demo", task)
    lines = []
    for i in range(n):
        key = f"u{i}.1.step"
        session(root, task, key, [bash("make")])
        r = rec(key, model=model)
        lines.append(json.dumps(r))
        d = digest.build(rd / "sessions" / key, r, {"tools": ["shell"]})
        (rd / "sessions" / key / "digest.json").write_text(json.dumps(d))
    (rd / "run.jsonl").write_text("\n".join(lines) + "\n")


def run_ticket(root: Path, task: str, run_cost: float) -> dict[str, Any]:
    t = ticket(root, task)
    t["run_cost_usd"] = run_cost  # the per-run cap is a quarter of this in dev mode (SRV-B21)
    t["units"] = {}
    return t


def reviewer(cost: float, n: int) -> Any:
    return standin("claude", judges=[answer(NONE_FOUND, cost=cost, session_id=f"r{i}") for i in range(n)])


def skipped(out: dict[str, Any]) -> list[str]:
    return [s["session_key"] for s in out["plan"]["skipped"] if s["reason"] == "budget"]


def test_the_r160_figures_skip_no_target(tmp_path: Path) -> None:  # SRV-AC9
    build_run(tmp_path, "B-1", 18)
    ex = reviewer(0.055, 18)  # 12 finished reviews report 0.66 USD together
    out = review.run(run_ticket(tmp_path, "B-1", 13.84), registry(ex))  # a cap of 3.46 USD
    assert out["plan"]["cap_usd"] == 3.46
    assert len(out["plan"]["targets"]) == 18 and len(out["done"]) == 18 and not skipped(out)
    assert out["cost"]["reported"] > 0.66


def test_the_next_estimate_past_the_cap_skips_that_target_and_every_later_one(tmp_path: Path) -> None:  # SRV-AC9
    build_run(tmp_path, "B-2", 6)
    out = review.run(run_ticket(tmp_path, "B-2", 4.0), registry(reviewer(0.25, 6)))  # a cap of 1.00 USD
    assert out["plan"]["cap_usd"] == 1.0
    keys = [t["session_key"] for t in out["plan"]["targets"]]
    assert out["done"] == keys[:4]  # 4 x 0.25 stays within 1.00
    assert skipped(out) == keys[4:]  # the fifth and the sixth
    log = [json.loads(ln) for ln in (run_dir(tmp_path, "demo", "B-2") / "loop.jsonl").read_text().splitlines()]
    assert [r["session_key"] for r in log if r["kind"] == "review_skipped" and r["reason"] == "budget"] == keys[4:]
    assert set(out["done"]).isdisjoint(skipped(out))  # a skipped target ranks below every target reviewed


def test_a_first_view_priced_over_the_cap_skips_every_target(tmp_path: Path) -> None:  # SRV-AC9
    build_run(tmp_path, "B-3", 3)
    ex = reviewer(0.01, 3)
    out = review.run(run_ticket(tmp_path, "B-3", 0.04), registry(ex))  # a cap of 0.01 USD: the view costs more
    assert out["done"] == [] and len(skipped(out)) == 3 and not ex.calls


def test_the_estimate_is_the_mean_of_the_reports_once_one_has_reported(tmp_path: Path) -> None:  # SRV-AC9
    build_run(tmp_path, "B-4", 4)  # each view alone is priced near 0.015 USD
    # the first review reports 0.30 USD: no later view-priced estimate would stop the second, the mean does
    ex = standin("claude", judges=[answer(NONE_FOUND, cost=0.30), answer(NONE_FOUND, cost=0.30),
                                   answer(NONE_FOUND, cost=0.30), answer(NONE_FOUND, cost=0.30)])
    out = review.run(run_ticket(tmp_path, "B-4", 3.2), registry(ex))  # a cap of 0.80 USD
    assert len(out["done"]) == 2  # 0.30 + 0.30 = 0.60; a third would need 0.60 + 0.30 = 0.90 > 0.80
    assert len(skipped(out)) == 2 and len(ex.calls) == 2


def test_earlier_plans_of_the_thread_count_toward_the_spend(tmp_path: Path) -> None:  # SRV-B25
    build_run(tmp_path, "B-5", 4)
    first = review.run(run_ticket(tmp_path, "B-5", 4.0), registry(reviewer(0.25, 4)), keys=["u0.1.step"])
    assert first["done"] == ["u0.1.step"]
    ex = reviewer(0.25, 3)  # 0.25 already spent in this run: three more fit under 1.00, the fourth does not
    out = review.run(run_ticket(tmp_path, "B-5", 4.0), registry(ex))
    assert len(out["done"]) == 3 and len(skipped(out)) == 1


def test_a_failed_review_counts_at_what_it_cost(tmp_path: Path) -> None:  # SRV-B25
    build_run(tmp_path, "B-6", 3)
    ex = standin("claude", judges=[answer("no block", cost=0.4), answer("no block", cost=0.4),
                                   answer(NONE_FOUND, cost=0.1)])  # the first review asks twice and fails
    out = review.run(run_ticket(tmp_path, "B-6", 3.2), registry(ex))  # a cap of 0.80 USD
    keys = [t["session_key"] for t in out["plan"]["targets"]]
    assert out["failed"] == [keys[0]]  # 0.40 + 0.40 spent
    assert out["done"] == [] and skipped(out) == keys[1:]  # 0.80 spent and no review reported: the view price decides
