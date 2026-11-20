"""T7.5 read side: supervision fields on the stats row (SUP §2.5, AC-2), `report --supervision` (SUP §2.4,
SUP-B5, AC-3's report half, AC-4, AC-5), the detail block, and `label` (FBK §2.2 explicit, FBK-AC-3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tempergraph.executors.standins import standin
from tempergraph.observe import supervision_report as sup
from tempergraph.store.layout import home_path, state_root_path

from .conftest import hash_tree
from .test_cli import cli
from .test_feedback import Seen, paused
from .test_provenance import CC
from .test_reports import write_log
from .test_run import DRAFT, REVIEW, go, judge
from .test_sinks import machine

CANARY = "canary-7f3e"


def record(level: str, *, rescue: dict[str, int] | None = None, steer: dict[str, int] | None = None,
           cost: float | None = None, unknown: int = 0, wait: float = 0.0, **extra: Any) -> dict[str, Any]:
    rescue, steer = rescue or {}, steer or {}
    return {"kind": "supervision", "level": level, "level_by": extra.pop("level_by", "none"),
            "touches": {"designed": {}, "rescue": rescue, "steer": steer, "engine": {}},
            "undesigned": sum(rescue.values()) + sum(steer.values()), "agent_own_rescues": rescue.get("agent", 0),
            "relayed": extra.pop("relayed", {}), "person_wait_s": wait, "callers_unknown": unknown,
            "supervision_cost": cost, "supervision_share": None, "observations": None,
            "supervisors": {"sessions": 0, "hosts": extra.pop("hosts", [])}, **extra}


def thread(root: Path, task: str, rec: dict[str, Any], *, origin: str = "cli", version: str = "1") -> None:
    write_log(root, task, [{"kind": "run_started", "workflow_version": version, "origin": origin},
                           rec, {"kind": "run_exit", "exit_code": 0}])


def test_aggregates_per_workflow(repo: Path) -> None:  # SUP §2.4
    root = state_root_path(repo)
    thread(root, "T-1", record("observer"))
    thread(root, "T-2", record("approver"))
    thread(root, "T-3", record("consultant", rescue={"agent": 2}, level_by="agent", hosts=["claude-code"],
                               relayed={"claimed": 1, "turn_named": 1}))
    thread(root, "T-4", record("collaborator", rescue={"person": 1}, steer={"person": 1}, level_by="person",
                               wait=600.0, unknown=1))
    thread(root, "T-5", record("observer"), origin="evals")  # never in a production figure (SUP-AC-4)
    doc = sup.report(root, None)
    a = doc["total"]
    assert a["runs"] == 4 and a["thin"] is True
    assert a["unattended_rate"] == 0.5 and a["unattended_interval"] == [0.15, 0.85]
    assert a["undesigned_per_run"] == 1.0 and a["undesigned_per_run_by_decider"] == {"agent": 0.5, "person": 0.5}
    assert a["agent_own_rescue_share"] == round(2 / 3, 4)
    assert a["relay_quality"] == {"claimed": 0.5, "turn_named": 0.5}
    assert a["person_wait_s"] == {"p50": 0.0, "p90": 600.0}
    assert a["supervision_cost_per_run"] == {"p50": None, "p90": None, "measured": 0, "of": 4}  # AC-5: never 0
    assert a["data_quality"]["callers_known"] == 0.75
    assert set(sup.report(root, None, "host")["groups"]) == {"claude-code", "none"}
    assert sup.report(root, None, "level")["groups"]["observer"]["runs"] == 1


def test_thin_and_measured_counts(repo: Path) -> None:  # SUP-B5
    root = state_root_path(repo)
    for i in range(12):
        thread(root, f"T-{i}", record("observer", cost=0.05 if i < 8 else None))
    a = sup.report(root, None)["total"]
    assert a["thin"] is False and a["supervision_cost_per_run"]["measured"] == 8
    assert a["data_quality"]["cost_measured"] == 0.6667
    code, text, _ = cli(repo, None, "report", "all", "--supervision")
    assert code == 0 and "measured 8 of 12" in str(text)


def test_agent_rescue_reaches_stats_row_and_report(repo: Path) -> None:  # SUP-B1, AC-2, AC-3
    seen = Seen()
    ex = paused(repo, "S-1", seen)
    ex.steps, ex.judges = [seen(DRAFT), seen(REVIEW)], [seen(judge()), seen(judge())]
    code, _, err = cli(repo, ex, "resume", "demo", "S-1", "--decision", "proceed", signals=(CC, False))
    assert code == 0, err
    rows = [json.loads(x) for p in sorted((home_path() / "stats").glob("*.jsonl")) for x in p.read_text().splitlines()]
    last = rows[-1]
    # one undesigned touch on one of the two units reached: half of them, so `operator` (SUP §2.3)
    assert (last["level"], last["level_by"], last["agent_own_rescues"]) == ("operator", "agent", 1)
    assert last["touches_undesigned"] == 1 and last["touches_by_decider"] == {"agent": 1}
    ledger = [json.loads(x) for x in (state_root_path(repo) / "ledger.jsonl").read_text().splitlines()]
    seg = [r for r in ledger if r.get("kind") == "run_segment" and r.get("thread_id") == "demo/S-1"][-1]
    assert seg["supervision"]["level"] == last["level"] and seg["supervision"]["undesigned"] == last["touches_undesigned"]
    root = state_root_path(repo)
    before = hash_tree(root)
    code, doc, _ = cli(repo, None, "report", "--supervision", "--by", "unit", "--json")
    assert code == 0 and doc["groups"]["demo.draft"]["by_decider"] == {"agent": 1}
    assert hash_tree(root) == before
    code, det, _ = cli(repo, None, "status", "demo/S-1", "--detail")
    assert code == 0 and det["supervision"]["level"] == "operator" and det["supervision"]["level_by"] == "agent"
    assert cli(repo, None, "report", "--by", "host")[0] == 2  # host needs --supervision


def test_sink_row_carries_the_same_touch_figures(repo: Path, tmp_path: Path, monkeypatch: Any) -> None:  # AC-2
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "inline")
    team = tmp_path / "share"
    team.mkdir()
    machine(monkeypatch, tmp_path, "a", team)
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), task="T-1")
    [runs] = list(team.glob("machines/*/runs/*.jsonl"))
    row = json.loads(runs.read_text())
    assert (row["level"], row["touches_undesigned"], row["level_by"]) == ("observer", 0, "none")


def test_label_is_metadata_only(repo: Path) -> None:  # FBK §2.1, FBK-AC-3, IMD-AC-1
    seen = Seen()
    paused(repo, "L-1", seen)
    code, doc, err = cli(repo, None, "label", "demo/L-1", "draft", "--value", "disagree", "--json")
    assert code == 0, err
    assert doc["label_kind"] == "explicit" and doc["value"] == "disagree" and doc["source"] == "person"
    assert doc["attempt"] == 1 and doc["gate_verdict"] == "ESCALATE" and doc["binding"]["executor"] == "claude"
    assert len(doc["repo"]) == 32 and doc["workflow"] == "demo" and doc["machine"]
    code, agent, _ = cli(repo, None, "label", "demo/L-1", "draft", "--value", "agree", "--json", signals=(CC, False))
    assert code == 0 and agent["source"] == "agent"  # an agent's own label never grades a judge (FBK-B2)
    ledger = (state_root_path(repo) / "ledger.jsonl").read_text().splitlines()
    labels = [json.loads(x) for x in ledger if '"kind": "label"' in x]
    assert len(labels) == 2
    assert all("notes" not in json.dumps(lab) for lab in labels)  # the run's request text
    assert cli(repo, None, "label", "demo/L-1", "nope", "--value", "agree")[0] == 2
    assert cli(repo, None, "label", "demo/L-1", "draft", "--value", "agree", "--criterion", "zzz")[0] == 2
    assert cli(repo, None, "label", "demo/L-1", "draft", "--value", "maybe")[0] == 2


def test_no_planted_text_crosses_to_the_aggregate(repo: Path, tmp_path: Path, monkeypatch: Any) -> None:  # IMD-AC-1
    monkeypatch.setenv("TEMPERGRAPH_FLUSHER", "inline")
    team = tmp_path / "share"
    team.mkdir()
    home = machine(monkeypatch, tmp_path, "a", team)
    seen = Seen()
    ex = paused(repo, f"PROJ-{CANARY}", seen)
    ex.steps, ex.judges = [seen(DRAFT), seen(REVIEW)], [seen(judge()), seen(judge())]
    code, _, err = cli(repo, ex, "resume", "demo", f"PROJ-{CANARY}", "--decision", "retry", "--feedback",
                       f"please fix {CANARY}")
    assert code == 0, err
    assert cli(repo, None, "label", f"demo/PROJ-{CANARY}", "review", "--value", "agree")[0] == 0
    assert cli(repo, None, "stats", "sync")[0] == 0
    crossed = [p for p in sorted(team.rglob("*")) + sorted((home / "fleet").rglob("*")) + sorted((home / "outbox").rglob("*"))
               if p.is_file() and CANARY in p.read_text(errors="replace")]
    assert crossed == []
    labels = [x for x in (state_root_path(repo) / "ledger.jsonl").read_text().splitlines() if '"kind": "label"' in x]
    assert labels and all(CANARY not in x.replace(f"demo/PROJ-{CANARY}", "") for x in labels)
