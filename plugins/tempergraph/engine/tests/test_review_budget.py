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


def test_a_cap_under_the_first_estimate_is_lifted_to_one_review(tmp_path: Path) -> None:
    # SRV-AC19 (SRV-B33, SRV-B25); AC 1, AC 2
    build_run(tmp_path, "B-3", 3)
    ex = reviewer(0.01, 3)
    out = review.run(run_ticket(tmp_path, "B-3", 0.04), registry(ex))  # the share gives a cap of 0.01 USD
    cap = out["plan"]["cap_usd"]
    keys = [t["session_key"] for t in out["plan"]["targets"]]
    assert cap > 0.01 and round(cap, 4) == cap  # the first view's estimate, rounded up to 4 places
    assert out["done"][:1] == keys[:1] and len(ex.calls) >= 1  # the most signalled session is reviewed
    assert skipped(out) == keys[len(out["done"]):]  # every later target is decided by SRV-B25 under the lifted cap
    assert set(out["done"]).isdisjoint(skipped(out))
    log = [json.loads(ln) for ln in (run_dir(tmp_path, "demo", "B-3") / "loop.jsonl").read_text().splitlines()]
    assert next(r for r in log if r["kind"] == "review_planned")["cap_usd"] == cap


def test_a_cap_above_the_first_estimate_is_not_lifted(tmp_path: Path) -> None:  # SRV-AC19 (SRV-B33); AC 3
    build_run(tmp_path, "B-7", 6)
    t = run_ticket(tmp_path, "B-7", 4.0)  # a cap of 1.00 USD, far above one review
    alone = review.plan_for(t)
    assert alone["cap_usd"] == 1.0  # SRV-B21: the plan alone does not lift
    out = review.run(t, registry(reviewer(0.25, 6)))
    assert out["plan"]["cap_usd"] == 1.0
    keys = [x["session_key"] for x in out["plan"]["targets"]]
    assert keys == [x["session_key"] for x in alone["targets"]]
    assert out["done"] == keys[:4] and skipped(out) == keys[4:]  # as the mid-plan fixture of SRV-AC9


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


# -- stable mode: the caps of a `signals` plan (SRV-B21, SIL-B20) ---------------------------------------------


def signal_run(root: Path, task: str, n: int, cost: float = 30.0, model: str | None = None) -> dict[str, Any]:
    """A stable fixture run of `n` units, each with a session that repeated one failing call and the finding for it."""
    from tempergraph.improve.record import append_findings

    rd = run_dir(root, "demo", task)
    lines, found = [], []
    for i in range(n):
        key = f"u{i}.1.step"
        session(root, task, key, [bash("make", ok=False, out="No such file")] * 4)
        r = rec(key, **({"model": model} if model else {}))
        lines.append(json.dumps(r))
        d = digest.build(rd / "sessions" / key, r, {"tools": ["shell"]})
        (rd / "sessions" / key / "digest.json").write_text(json.dumps(d))
        found.append({"kind": "finding", "unit": f"u{i}", "cause": "tool_repeat", "class": "fault", "side": "workflow",
                      "workflow": "demo", "workflow_version": "1.0.0", "fingerprint": f"f{i}"})
    (rd / "run.jsonl").write_text("\n".join(lines) + "\n")
    append_findings(root, "demo", task, f"demo/{task}", found)
    t = run_ticket(root, task, cost)
    return {**t, "review": "signals", "mode": "stable", "workflow_version": "1.0.0",
            "fingerprints": [f["fingerprint"] for f in found]}


def loop_spent(root: Path, usd: float) -> None:
    from datetime import UTC, datetime

    with open(root / "ledger.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "loop", "workflow": "demo", "ts": datetime.now(UTC).isoformat(),
                             "cost": {"reported": usd, "estimated_only": 0.0}}) + "\n")


def test_the_stable_cap_is_the_lowest_of_the_share_the_run_cap_and_the_days_room(tmp_path: Path) -> None:
    # SRV-AC9 (SRV-B21, SIL-B20)
    t = signal_run(tmp_path, "C-1", 1, cost=30.0)
    assert review.plan_for(t)["cap_usd"] == 2.0  # a tenth of 30 is 3: the $2 per-run cap is lower
    assert review.plan_for({**t, "run_cost_usd": 5.0})["cap_usd"] == 0.5  # a tenth of the run's cost
    loop_spent(tmp_path, 49.2)  # the day's room under the $50 daily cap shrinks to 0.80
    assert review.plan_for(t)["cap_usd"] == 0.8
    assert review.plan_for(t, room=0.3)["cap_usd"] == 0.3  # the loop child passes what its own judges left over
    loop_spent(tmp_path, 5.0)
    assert review.plan_for(t)["cap_usd"] == 0.0  # no room left
    assert review.plan({**t, "mode": "dev", "review": "full"}, [], room=0.1)["cap_usd"] == 5.0  # dev mode: no room


def test_the_lift_of_a_stable_cap_stops_at_what_the_day_leaves(tmp_path: Path) -> None:
    # SRV-AC20 (SRV-B33, SIL-B20); AC 1
    model = "claude-sonnet-5-5"
    t = signal_run(tmp_path, "C-4", 2, cost=0.01, model=model)  # the share gives a cap of 0.001 USD
    assert review.plan_for(t)["cap_usd"] == 0.001
    loop_spent(tmp_path, 49.995)  # the day leaves 0.005 USD
    ex = reviewer(0.01, 2)
    out = review.run(t, registry(ex), room=0.005)
    assert out["plan"]["cap_usd"] == 0.005  # lifted to what the day leaves, not to the estimate above it
    assert not ex.calls and out["done"] == []
    assert len(skipped(out)) == len(out["plan"]["targets"]) == 2  # no review starts: all `skipped: budget`

    t2 = signal_run(tmp_path, "C-5", 2, cost=0.01, model=model)
    ex2 = reviewer(0.01, 2)
    out2 = review.run(t2, registry(ex2), room=0.5)  # the day leaves more than one review
    cap = out2["plan"]["cap_usd"]
    assert 0.001 < cap <= 0.5 and round(cap, 4) == cap  # lifted to the estimate, below the day's room
    keys = [x["session_key"] for x in out2["plan"]["targets"]]
    assert out2["done"][:1] == keys[:1]


def test_a_signals_plan_reads_at_most_three_sessions_and_skips_the_rest_in_order(tmp_path: Path) -> None:
    # SRV-AC9 (SRV-B21, SRV-B24)
    t = signal_run(tmp_path, "C-2", 5)
    p = review.plan_for(t)
    assert [x["session_key"] for x in p["targets"]] == ["u4.1.step", "u3.1.step", "u2.1.step"]  # later first
    assert [(s["session_key"], s["reason"]) for s in p["skipped"]] == [("u1.1.step", "budget"), ("u0.1.step", "budget")]
    assert p["depth"] == "partial" and p["cap_usd"] == 2.0


def test_a_review_stops_mid_plan_when_the_money_runs_out_and_skips_the_rest_as_budget(tmp_path: Path) -> None:
    # SRV-AC9 (SRV-B21, SRV-B25)
    t = signal_run(tmp_path, "C-3", 5)
    ex = reviewer(0.10, 5)
    out = review.run(t, registry(ex), room=0.25)  # the day leaves 0.25: two reviews at 0.10, the third would pass it
    keys = [x["session_key"] for x in out["plan"]["targets"]]
    assert out["plan"]["cap_usd"] == 0.25 and keys == ["u4.1.step", "u3.1.step", "u2.1.step"]
    assert out["done"] == keys[:2] and len(ex.calls) == 2
    assert [s["session_key"] for s in out["plan"]["skipped"] if s["reason"] == "budget"] == [
        "u1.1.step", "u0.1.step", "u2.1.step"]  # the two the count cap left out, then the third the money did
    assert set(out["done"]).isdisjoint(skipped(out))
    log = [json.loads(ln) for ln in (run_dir(tmp_path, "demo", "C-3") / "loop.jsonl").read_text().splitlines()]
    assert next(r for r in log if r["kind"] == "review_planned")["depth"] == "partial"
