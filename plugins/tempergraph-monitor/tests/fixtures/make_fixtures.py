"""Write the monitor's engine fixtures from a scripted-executor run (no model is called).

Run from plugins/tempergraph/engine:  python ../../tempergraph-monitor/tests/fixtures/make_fixtures.py
The engine test `test_monitor_fixtures_match_the_engine` checks the fixtures still have the engine's shape.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3] / "tempergraph" / "engine"
sys.path.insert(0, str(ENGINE))

from tempergraph.durability.status import status  # noqa: E402
from tempergraph.observe.detail import detail  # noqa: E402
from tempergraph.store.layout import run_dir, state_root_path  # noqa: E402
from tests.fixtures.workflows import two_step  # noqa: E402
from tests.test_run import DRAFT, REVIEW, go, judge, verdict_block  # noqa: E402
from tempergraph.executors.standins import standin  # noqa: E402

OUT = Path(__file__).resolve().parent


def scrub_paths(text: str, root: Path) -> str:
    text = text.replace(str(root.parent), "/work")
    return re.sub(r'"pid": \d+', '"pid": 1', text)


def machine(tmp: str, name: str, sink: Path) -> Path:
    """One simulated machine: its own home folder, labelled `name`, with `sink` configured as `team`."""
    from tempergraph.store.layout import ensure_home

    home = Path(tmp) / name / ".tempergraph"
    os.environ["TEMPERGRAPH_HOME"] = str(home)
    ensure_home(home)
    m = json.loads((home / "machine.json").read_text())
    (home / "machine.json").write_text(json.dumps({**m, "label": name}))
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / "sinks.json").write_text(json.dumps(
        {"schema_version": 1, "sinks": [{"name": "team", "kind": "directory", "path": str(sink)}]}))
    return home


def cli_doc(repo: Path, *argv: str) -> dict:
    import io

    from tempergraph.catalog import Catalog
    from tempergraph.cli.main import main as engine_main

    out = io.StringIO()
    assert engine_main(list(argv), catalog=Catalog(specs={"demo": two_step()}), cwd=repo, out=out) == 0, argv
    return json.loads(out.getvalue())


def fleet_docs(tmp: str, repo: Path) -> dict[str, dict]:
    """`stats --live`, the month by machine and `--projection` from two machines sharing one sink folder."""
    sink = Path(tmp) / "share"
    sink.mkdir()
    os.environ["TEMPERGRAPH_FLUSHER"] = "inline"
    machine(tmp, "desk-b", sink)
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(verdict_block("UNVERIFIABLE")), judge()]),
       task="T-8")  # paused on desk-b
    machine(tmp, "laptop-a", sink)
    go(repo, standin("claude", steps=[DRAFT, REVIEW], judges=[judge(), judge()]), task="T-9")
    month = datetime.now(UTC).strftime("%Y-%m")
    return {"stats-live.json": cli_doc(repo, "stats", "--live", "--json"),
            "stats-machine.json": cli_doc(repo, "stats", "--month", month, "--by", "machine", "--json"),
            "stats-projection.json": cli_doc(repo, "stats", "--projection", "--by", "workflow", "--json")}


def main() -> None:
    saved = {k: os.environ.get(k) for k in ("TEMPERGRAPH_HOME", "TEMPERGRAPH_FLUSHER")}
    try:
        _write()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _write() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TEMPERGRAPH_HOME"] = str(Path(tmp) / "home" / ".tempergraph")  # never the real home
        repo = Path(tmp) / "repo"
        repo.mkdir()
        for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.invalid"],
                     ["config", "user.name", "T"]):
            subprocess.run(["git", *args], cwd=repo, check=True)
        (repo / "README.md").write_text("x\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "i"], cwd=repo, check=True)
        ex = standin("claude", steps=[DRAFT, DRAFT, REVIEW, DRAFT, REVIEW],
                     judges=[judge(verdict_block("UNMET")), judge(), judge(verdict_block("UNMET", defect_in="notes")),
                             judge(), judge(verdict_block("UNVERIFIABLE"))])
        go(repo, ex)
        root = state_root_path(repo)
        spec = two_step()
        docs = {
            "status.json": status(root, {"demo": spec}),
            "detail-paused.json": detail(root, spec, "demo/T-1"),
        }
        log = (run_dir(root, "demo", "T-1") / "run.jsonl").read_text()
        docs.update(fleet_docs(tmp, repo))
        for name, doc in docs.items():
            (OUT / name).write_text(scrub_paths(json.dumps(doc, indent=2), repo) + "\n")
        (OUT / "run-paused.jsonl").write_text(scrub_paths(log, repo))
        # The mod's session tests load only code files, so the same documents also go out as one module.
        module = ["// Written by make_fixtures.py; do not edit. The same documents as the .json files beside it.\n"]
        for name, doc in docs.items():
            ident = re.sub(r"-(\w)", lambda m: m.group(1).upper(), name.removesuffix(".json"))
            module.append(f"export const {ident} = {scrub_paths(json.dumps(doc, indent=2), repo)} as const\n")
        (OUT / "documents.ts").write_text("\n".join(module))


if __name__ == "__main__":
    main()
