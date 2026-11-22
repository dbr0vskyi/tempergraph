"""Run state carried on its own branch (CAR-B5, CAR-B1 to B4, CAR-AC1 to AC-4): two state roots, one bare
remote, and two machine identities."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tempergraph import identity
from tempergraph.constants import ExitCode
from tempergraph.durability import carry
from tempergraph.executors.standins import standin
from tempergraph.run.log import RunLog
from tempergraph.store.layout import run_dir, state_root_path

from .test_cli import cli
from .test_run import DRAFT, REVIEW, judge, verdict_block

BRANCH = "tempergraph/state/demo/t1"
SECRET = "sk-ant-api03-abcdefghijklmnop"


def git(cwd: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True).stdout.strip()


class World:
    """Two machines with a clone each, and the bare remote between them."""

    def __init__(self, tmp: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp, self.a, self.monkeypatch = tmp, repo, monkeypatch
        self.remote = tmp / "remote.git"
        git(tmp, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(repo, "remote", "add", "origin", str(self.remote))
        git(repo, "push", "-q", "-u", "origin", "main")
        self.b = tmp / "b" / "repo"
        self.b.parent.mkdir()
        git(tmp, "clone", "-q", str(self.remote), str(self.b))
        git(self.b, "config", "user.email", "b@example.invalid")
        git(self.b, "config", "user.name", "B")

    def on(self, name: str) -> Path:
        """Become machine `a` or `b`: its own home folder, so its own machine id."""
        self.monkeypatch.setenv("TEMPERGRAPH_HOME", str(self.tmp / f"home-{name}" / ".tempergraph"))
        return self.a if name == "a" else self.b

    def machine(self, name: str) -> str:
        self.on(name)
        return str(identity.machine_id())

    def paused_on_a(self, *extra: str) -> Path:
        """A carried run that pauses at the draft gate on machine A, with its work branch on the remote."""
        repo = self.on("a")
        ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
        code, _, err = cli(repo, ex, "run", "demo", "notes", "--task-id", "t1", "--carry", *extra)
        assert code == ExitCode.PAUSED, err
        work = self.work_branch(repo)
        git(repo, "push", "-q", "origin", work)  # the person's own push of the work branch
        return repo

    def work_branch(self, repo: Path) -> str:
        from tempergraph.run.events import records

        ws = [r for r in records(run_dir(state_root_path(repo), "demo", "t1") / "run.jsonl") if r["kind"] == "workspace"]
        return str(ws[-1]["branch"])

    def remote_heads(self) -> list[str]:
        return [ln.split("refs/heads/")[1] for ln in git(self.remote, "show-ref", "--heads", check=False).splitlines()]

    def state_paths(self) -> list[str]:
        return git(self.remote, "ls-tree", "-r", "--name-only", BRANCH).splitlines()

    def manifest(self) -> dict[str, Any]:
        return json.loads(git(self.remote, "show", f"{BRANCH}:.tempergraph-carry/carry.json"))


@pytest.fixture
def world(tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    return World(tmp_path, repo, monkeypatch)


def finish_on(repo: Path) -> tuple[int, Any, str]:
    ex = standin("claude", steps=[REVIEW], judges=[judge()])
    return cli(repo, ex, "resume", "demo", "t1", "--decision", "proceed", "--json")


# -- CAR-B1, CAR-B3 ---------------------------------------------------------------------------------------------


def test_pause_on_one_machine_resume_on_another(world: World) -> None:
    a = world.paused_on_a()
    work = world.work_branch(a)
    assert BRANCH in world.remote_heads()
    assert git(world.remote, "rev-list", "--count", BRANCH) == "1"
    assert git(world.remote, "log", "-1", "--format=%s", BRANCH).startswith("tempergraph state demo/t1 seq ")
    assert all(p.startswith(".tempergraph-carry/") for p in world.state_paths())
    assert world.manifest()["lease"] is None
    assert git(world.remote, "merge-base", BRANCH, "main", check=False) == ""  # an orphan branch
    assert git(a, "status", "--porcelain") == ""  # no checkout or index was touched
    before = git(world.remote, "rev-parse", work)

    b = world.on("b")
    code, doc, err = cli(b, None, "carry", "pull", "demo", "t1", "--json")
    assert code == 0 and doc["imported"] > 3 and doc["takeover"] is False, err
    code, st, _ = cli(b, None, "status")
    assert [(t["thread_id"], t["state"]) for t in st["threads"]] == [("demo/t1", "paused")]
    code, doc, err = finish_on(b)
    assert code == 0, (err, doc)
    kinds = [r["kind"] for r in _records(b)]
    assert kinds.count("run_started") == 2 and "run_exit" in kinds  # A's segment travelled, B's continued it
    assert [r["unit"] for r in _records(b) if r["kind"] == "agent_run" and r.get("session_kind") == "step"] == [
        "draft", "review"]

    # CAR-B3, CAR-AC3: no trace after the finish
    assert BRANCH not in world.remote_heads()
    assert git(b, "for-each-ref", "refs/heads/tempergraph/state/") == ""
    assert git(world.remote, "rev-parse", work) == before  # carrying added no commit to the work branch
    assert ".tempergraph-carry" not in git(world.remote, "log", "--all", "--name-only", "--format=")
    assert carry.marker(state_root_path(b), "demo", "t1")["state"] == "finished"


def _records(repo: Path) -> list[dict[str, Any]]:
    from tempergraph.run.events import records

    return list(records(run_dir(state_root_path(repo), "demo", "t1") / "run.jsonl"))


# -- CAR-B2, CAR-AC2 -------------------------------------------------------------------------------------------


def test_nothing_private_travels(world: World) -> None:
    a = world.paused_on_a()
    root = state_root_path(a)
    base = run_dir(root, "demo", "t1")
    private = ["sessions/s1/raw.jsonl", "sessions/s1/stderr.log", "stderr.log", "output/out.txt",
               "evidence/prompts/p.md", "checks/c.json", "hooks/h.log", "sessions/s1/extra.bin"]
    kept = ["sessions/s1/meta.json", "sessions/s1/activity.jsonl", "sessions/s1/digest.json"]
    for rel in private + kept:
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_text(json.dumps({"note": f"the key is {SECRET}"}) + "\n")
    for rel in ("config/settings.json", "scratch/x.txt", "locks/x.lock", "authoring/a.json", "upgrades/u.json",
                "backups/b.json", "engine/e.json", "runs/demo/other/run.jsonl", "runs/else/t9/run.jsonl"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(f"{SECRET}\n")
    with (root / "ledger.jsonl").open("a") as fh:
        fh.write(json.dumps({"kind": "run_segment", "thread_id": "demo/other", "note": "another thread"}) + "\n")
    code, _, err = cli(a, None, "carry", "push", "demo", "t1")
    assert code == 0, err
    paths = world.state_paths()
    assert all(p.startswith(".tempergraph-carry/") for p in paths)
    inner = {p.split("/", 1)[1] for p in paths}
    assert {"carry.json", "checkpoint.sqlite", "ledger.jsonl", "workspace.json", "run/run.jsonl"} <= inner
    assert {f"run/{k}" for k in kept} <= inner
    assert not any(f"run/{p}" in inner for p in private)
    assert "run/engine.json" in inner  # the thread's engine record travels with it (MIG-B8)
    assert not any(part in p for p in inner - {"run/engine.json"} for part in ("config", "scratch", "locks", "authoring", "upgrades",
                                                          "backups", "engine", "carry.local", "other", "t9"))
    blob = git(world.remote, "grep", "-c", "-e", SECRET, BRANCH, check=False)
    assert blob == ""  # the scrubber ran on every text file
    man = world.manifest()
    assert man["scrubbed"]["run/sessions/s1/meta.json"] == 1 and man["seq"] > 0
    assert "demo/other" not in git(world.remote, "show", f"{BRANCH}:.tempergraph-carry/ledger.jsonl")
    assert "path" not in json.loads(git(world.remote, "show", f"{BRANCH}:.tempergraph-carry/workspace.json"))


def test_a_state_commit_holds_only_the_carry_folder(world: World, tmp_path: Path) -> None:
    """CAR-B5, CAR-B8, CAR-B11, CAR-B6."""
    f = tmp_path / "x.txt"
    f.write_text("x\n")
    with pytest.raises(carry.CarryRefused, match="not a path inside"):
        carry._tree(world.a, {"../escape.txt": f})
    tree = git(world.a, "write-tree")  # a tree with the work files in it
    commit = git(world.a, "commit-tree", tree, "-m", "not a state commit")
    with pytest.raises(carry.CarryRefused, match="outside"):
        carry._read_tree(world.a, commit, tmp_path / "into")


# -- CAR-B4 and its table ----------------------------------------------------------------------------------------


def test_one_driver(world: World) -> None:
    a = world.paused_on_a()
    root_a = state_root_path(a)
    machine_a = world.machine("a")
    carry.push(root_a, a, "demo", "t1", lease=carry.lease_of(machine_a), machine=machine_a)  # A is resuming
    assert world.manifest()["lease"]["machine"] == machine_a

    b = world.on("b")
    code, _, err = cli(b, None, "carry", "pull", "demo", "t1")
    assert code == 2 and "carry_leased" in err and machine_a in err and "since" in err
    assert not (state_root_path(b) / "runs").exists()
    code, doc, err = cli(b, None, "carry", "pull", "demo", "t1", "--force", "--json")
    assert code == 0 and doc["takeover"] is True, err
    rows = [json.loads(ln) for ln in (state_root_path(b) / "ledger.jsonl").read_text().splitlines()]
    took = [r for r in rows if r.get("cause") == "carry_takeover"]
    assert len(took) == 1 and took[0]["touches"] == [{"class": "steer", "action": "carry_takeover"}]
    assert took[0]["caller"]["kind"] == "person" and took[0]["taken_from"]["machine"] == machine_a

    # A pushes again (its own lease still stands on the branch): B must pull before it resumes
    world.on("a")
    RunLog(run_dir(root_a, "demo", "t1") / "run.jsonl").write("engine_error", scope="test", error="later record")
    carry.push(root_a, a, "demo", "t1", lease=None, machine=machine_a)
    world.on("b")
    code, _, err = finish_on(b)
    assert code == 2 and "newer than this machine" in err and "carry pull demo t1" in err
    code, _, err = cli(b, None, "carry", "pull", "demo", "t1")
    assert code == 0, err
    assert (state_root_path(b) / "backups").is_dir()  # the replaced local copy was kept
    assert finish_on(b)[0] == 0


def test_a_resume_takes_the_lease_and_a_pause_releases_it(world: World) -> None:
    a = world.paused_on_a()
    seen: list[Any] = []

    def reviewing(req: Any) -> Any:
        seen.append(world.manifest()["lease"])  # the lease is on the branch before the first attempt
        return REVIEW

    ex = standin("claude", steps=[reviewing], judges=[judge(verdict_block("UNVERIFIABLE"))])
    code, _, err = cli(a, ex, "resume", "demo", "t1", "--decision", "proceed")
    assert code == ExitCode.PAUSED, err
    assert seen and seen[0]["machine"] == world.machine("a") and seen[0]["since"]
    assert world.manifest()["lease"] is None
    assert git(world.remote, "rev-list", "--count", BRANCH) == "3"  # the pause, the lease, the second pause


def test_pull_where_the_thread_is_needs_a_newer_state(world: World) -> None:
    a = world.paused_on_a()
    code, _, err = cli(a, None, "carry", "pull", "demo", "t1")
    assert code == 2 and "carry_not_newer" in err


# -- CAR-B10, CAR-AC4 --------------------------------------------------------------------------------------------


def _rewrite(world: World, change: Any) -> None:
    """Replace the state branch on the remote with a commit whose carried files `change` has edited."""
    a = world.a
    tip = git(world.remote, "rev-parse", BRANCH)
    git(a, "fetch", "-q", "origin", BRANCH)
    into = world.tmp / f"rewrite-{tip[:8]}"
    files = carry._read_tree(a, tip, into)
    change(files)
    commit = git(a, "commit-tree", carry._tree(a, files), "-p", tip, "-m", "edited")
    git(a, "push", "-q", "origin", f"{commit}:refs/heads/{BRANCH}")


def _manifest_edit(**fields: Any) -> Any:
    def change(files: dict[str, Path]) -> None:
        doc = json.loads(files["carry.json"].read_text())
        files["carry.json"].write_text(json.dumps({**doc, **fields}))

    return change


def test_pull_checks_before_it_imports(world: World) -> None:
    a = world.paused_on_a()
    work = world.work_branch(a)
    b = world.on("b")

    def refused(code_word: str, *argv: str) -> str:
        code, _, err = cli(b, None, "carry", "pull", "demo", "t1", *argv)
        assert code == 2 and code_word in err, err
        assert not (state_root_path(b) / "runs" / "demo" / "t1" / "run.jsonl").exists()
        return err

    git(world.remote, "branch", "-m", work, "kept-aside")  # the work branch is not on the remote
    assert "nothing to resume on" in refused("carry_no_work_branch")
    git(world.remote, "branch", "-m", "kept-aside", work)

    _rewrite(world, _manifest_edit(workflow_version="9.9.9+other"))
    assert "9.9.9+other" in refused("carry_workflow")
    code, _, err = cli(b, None, "carry", "pull", "demo", "t1", "--force")  # MIG's change-under-a-thread rules
    assert code == 0, err
    import shutil

    shutil.rmtree(state_root_path(b) / "runs" / "demo" / "t1")

    _rewrite(world, _manifest_edit(store_layout=99, engine_version="9.0.0"))
    assert "9.0.0" in refused("carry_newer")
    _rewrite(world, _manifest_edit(store_layout=1, checkpoint_format=99))
    refused("carry_newer")

    _rewrite(world, lambda files: files["ledger.jsonl"].write_text("{}\n"))
    assert "ledger.jsonl" in refused("carry_digest")
    _rewrite(world, lambda files: files["carry.json"].write_text("{not json"))
    refused("carry_manifest")


def test_pull_of_an_unregistered_workflow_is_refused(world: World) -> None:
    world.paused_on_a()
    with pytest.raises(carry.CarryRefused, match="not registered"):
        carry.pull(state_root_path(world.b), world.on("b"), "demo", "t1", current_version=None)


# -- CAR-B5, CAR-B8, CAR-B11, CAR-B6 -----------------------------------------------------------------------------------------------------


def test_carry_needs_a_remote(repo: Path) -> None:
    ex = standin("claude", steps=[DRAFT], judges=[judge()])
    code, _, err = cli(repo, ex, "run", "demo", "notes", "--task-id", "t1", "--carry")
    assert code == 2 and "carrying needs a git remote" in err
    assert not (repo / ".tempergraph").exists() and ex.calls == []


def test_a_failed_push_never_changes_the_exit(world: World) -> None:
    a = world.on("a")
    git(a, "remote", "set-url", "origin", str(world.tmp / "gone.git"))
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    code, doc, err = cli(a, ex, "run", "demo", "notes", "--task-id", "t1", "--carry", "--json")
    assert code == ExitCode.PAUSED and "carry: unpushed" in doc["warnings"], err
    code, st, _ = cli(a, None, "status")
    assert st["threads"][0]["carry"] == "unpushed"
    git(a, "remote", "set-url", "origin", str(world.remote))
    code, doc, err = cli(a, None, "carry", "push", "demo", "t1", "--json")
    assert code == 0 and doc["seq"] > 0 and BRANCH in world.remote_heads(), err
    code, doc, _ = cli(a, None, "carry", "status", "demo", "t1", "--json")
    assert doc["state"] == "pushed" and doc["remote_seq"] == doc["local_seq"] and doc["lease"] is None


def test_drop_deletes_the_branch(world: World) -> None:
    a = world.paused_on_a()
    code, doc, err = cli(a, None, "carry", "drop", "demo", "t1", "--json")
    assert code == 0 and doc["deleted"] is True, err
    assert BRANCH not in world.remote_heads() and git(a, "for-each-ref", "refs/heads/tempergraph/state/") == ""
    assert carry.marker(state_root_path(a), "demo", "t1")["on"] is False
    code, st, _ = cli(a, None, "status")
    assert "carry" not in st["threads"][0] or st["threads"][0]["carry"] == "dropped"


def test_resume_can_turn_carrying_on(world: World) -> None:
    a = world.on("a")
    ex = standin("claude", steps=[DRAFT], judges=[judge(verdict_block("UNVERIFIABLE"))])
    assert cli(a, ex, "run", "demo", "notes", "--task-id", "t1")[0] == ExitCode.PAUSED
    assert BRANCH not in world.remote_heads()
    ex = standin("claude", steps=[REVIEW], judges=[judge(verdict_block("UNVERIFIABLE"))])
    code, _, err = cli(a, ex, "resume", "demo", "t1", "--decision", "proceed", "--carry")
    assert code == ExitCode.PAUSED and BRANCH in world.remote_heads(), err
