"""Decision records whose revisit trigger has fired (DRV-B1 to DRV-B4; GitHub issue #230)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from tempergraph.audit import audit, revisit
from tempergraph.cli.main import main
from tempergraph.executors.registry import Registry
from tempergraph.executors.standins import standin
from tempergraph.package.loader import load_package

from .fixtures.packages import minimal_package, write
from .test_audit import ctx

RECORD = """# A decision

## Decision

We keep one prompt.

## Revisit when

- Live check `TS-L1` has a result.
- Issue #12 is closed.
- `prompts/draft.md` chars above 200.
- The engine version moves.
- Claude version reaches 9.9.9.
- The team grows.
"""
PLAN = "| Row | Result |\n|---|---|\n| TS-L1 | not run |\n"


def _pkg(tmp: Path) -> Path:
    root = minimal_package(tmp)
    write(root, "docs/adr/keep-one-prompt.adr.md", RECORD)
    write(root, "docs/plans/live.plan.md", PLAN)
    return root


def _readers(issue: str | None = "open", claude: str | None = "2.1.332", engine: str = "0.3.0") -> revisit.Readers:
    return revisit.Readers(issue=lambda n: issue, claude_version=lambda: claude, engine_version=engine)


def _stamp(root: Path, readers: revisit.Readers) -> dict[str, Any]:
    return {"revisit": revisit.states(load_package(root).spec, readers)}


def test_drv_ac1_each_trigger_form_is_parsed_and_prose_is_listed(tmp_path: Path) -> None:  # DRV-AC1 (DRV-B1)
    triggers, prose = revisit.parse("docs/adr/a.adr.md", RECORD)
    assert [t.key for t in triggers] == ["live_check:TS-L1", "issue:12", "measure:prompts/draft.md:chars>200",
                                         "version:engine", "version:claude>=9.9.9"]
    assert [p.text for p in prose] == ["The team grows."]


def test_drv_ac2_an_unchanged_trigger_does_not_fire(tmp_path: Path) -> None:  # DRV-AC2 (DRV-B2)
    root = _pkg(tmp_path)
    spec = load_package(root).spec
    stamp = _stamp(root, _readers())
    assert revisit.findings(spec, stamp, _readers()) == []
    assert revisit.findings(spec, None, _readers(issue="closed")) == []  # no stamp: nothing to compare with


def test_drv_ac2_each_form_fires_when_its_state_changes(tmp_path: Path) -> None:  # DRV-AC2 (DRV-B2)
    root = _pkg(tmp_path)
    stamp = _stamp(root, _readers())
    write(root, "docs/plans/live.plan.md", PLAN.replace("not run", "passed 2026-11-26"))
    write(root, "prompts/draft.md", "Write release notes for {request} into notes.md.\n" + "x" * 300 + "\n")
    lp = load_package(root)
    due = {f.item for f in revisit.findings(lp.spec, stamp, _readers(issue="closed", claude="9.9.9", engine="0.4.0"))}
    assert due == {"live_check:TS-L1", "issue:12", "measure:prompts/draft.md:chars>200", "version:engine",
                   "version:claude>=9.9.9"}


def test_drv_ac2_an_unreadable_issue_never_fires(tmp_path: Path) -> None:  # DRV-AC2 (DRV-B2)
    root = _pkg(tmp_path)
    stamp = _stamp(root, _readers(issue=None))
    assert not [f for f in revisit.findings(load_package(root).spec, stamp, _readers(issue=None))
                if f.item == "issue:12"]


def test_drv_ac3_the_audit_reports_the_rule_as_info_and_the_stamp_records_states(tmp_path: Path) -> None:
    # DRV-AC3 (DRV-B2, DRV-B3)
    root = _pkg(tmp_path)
    lp = load_package(root)
    stamp = _stamp(root, revisit.Readers(engine_version="0.0.1"))
    assert stamp["revisit"]["docs/adr/keep-one-prompt.adr.md"]["version:engine"] == "0.0.1"
    assert "issue:12" not in stamp["revisit"]["docs/adr/keep-one-prompt.adr.md"]  # read online only
    rep = audit(lp.spec, {"definition"}, ctx(tmp_path, issue_state=lambda n: "closed"), manifest=lp.manifests.engine,
                stamp=stamp)
    got = {f.item: f for f in rep.findings if f.rule == "decision-revisit-due"}
    assert set(got) == {"issue:12", "version:engine"}  # the engine moved from 0.0.1; the issue closed
    assert all(f.severity == "info" for f in got.values())


def test_drv_ac4_audit_decisions_lists_triggers_and_prose(tmp_path: Path) -> None:  # DRV-AC4 (DRV-B4)
    root = _pkg(tmp_path)
    out = io.StringIO()
    reg = Registry()
    reg.register(standin("claude"))
    assert main(["audit", "decisions", str(root)], registry=reg, cwd=tmp_path, out=out, err=io.StringIO()) == 0
    doc = json.loads(out.getvalue())
    kinds = [r["kind"] for r in doc["triggers"]]
    assert kinds.count("not machine-readable") == 1 and "live_check" in kinds
