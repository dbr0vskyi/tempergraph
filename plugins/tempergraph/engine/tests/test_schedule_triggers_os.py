"""The `os` adapter: entries written as files, checked against golden files, never installed for real (TCK-B1, TCK-B8, TCK-B14,
TCK-B15; TCK-AC1; AC 7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tempergraph.cli import schedule_cli
from tempergraph.install import shim as shimmod
from tempergraph.schedule import tick, triggers
from tempergraph.store.layout import home_path

from .conftest import ENGINE_ROOT, hash_tree
from .test_schedule_cli import NOW, WARSAW, home_hash, sched

GOLDEN = ENGINE_ROOT / "tests" / "golden" / "schedule"
SHIM = "/home/user/.tempergraph/bin/tempergraph"
WIN_SHIM = "C:\\Users\\user\\.tempergraph\\bin\\tempergraph.cmd"
CASES = [("launchagent", "launchagent.plist", SHIM), ("systemd", "tempergraph-schedule.service", SHIM),
         ("taskscheduler", "task.xml", WIN_SHIM), ("crontab", "crontab.txt", SHIM)]
PLATFORMS = {"launchagent": ("darwin", lambda name: None), "systemd": ("linux", lambda name: "/bin/systemctl"),
             "taskscheduler": ("win32", lambda name: None), "crontab": ("linux", lambda name: "/usr/bin/crontab" if name == "crontab" else None)}


def golden_text(name: str) -> str:
    """A golden file, without the line that names the criterion it proves (TCK-AC1)."""
    lines = (GOLDEN / name).read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(line for line in lines if "TCK-AC1" not in line)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))


@pytest.fixture
def user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    u = tmp_path / "user"
    u.mkdir()
    monkeypatch.setenv("HOME", str(u))  # nothing is ever written to the real user folders
    return u


@pytest.mark.parametrize(("kind", "golden", "shim"), CASES)
def test_tck_ac1_each_entry_equals_its_golden_file_and_holds_only_the_shim_and_the_verb(kind: str, golden: str, shim: str) -> None:
    text = triggers.render(kind, Path(shim))
    assert text == golden_text(golden)
    verb = "schedule tick" if kind == "crontab" else "schedule loop"
    assert shim in text and text.count("schedule") >= 1
    for banned in ("sh -c", "/bin/sh", "bash", "cmd /c", "Environment", "TEMPERGRAPH_", "$", "`", "&&", "|"):
        assert banned not in text, (kind, banned)
    flat = text.replace("</string>\n    <string>", " ")  # a LaunchAgent lists its words one to a line
    assert verb in flat and ("schedule loop" in flat) is (kind != "crontab")  # the crontab fallback ticks, the rest loop


@pytest.mark.parametrize(("kind", "golden", "shim"), CASES)
def test_tck_ac1_install_writes_the_entry_for_the_platform_and_twice_leaves_one(kind: str, golden: str, shim: str,
                                                                                  user: Path) -> None:
    platform, which = PLATFORMS[kind]
    home = home_path()
    first = triggers.install(home, platform=platform, user_home=user, which=which)
    assert first["kind"] == kind and first["written"] is True
    path = Path(first["path"])
    wanted = golden_text(golden)
    assert path.read_text(encoding="utf-8").replace(str(triggers.shim_for(home, platform)), shim) == wanted
    before = hash_tree(user) | hash_tree(home)
    again = triggers.install(home, platform=platform, user_home=user, which=which)
    assert again["written"] is False and (hash_tree(user) | hash_tree(home)) == before  # idempotent: one entry
    assert len(triggers.status(home, platform=platform, user_home=user)) == 1


def test_tck_ac1_systemd_gets_its_wants_link_and_nothing_is_launched(user: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def boom(*a: object, **k: object) -> None:
        raise AssertionError("a process was started")

    monkeypatch.setattr(subprocess, "Popen", boom)
    got = triggers.install(home_path(), platform="linux", user_home=user, which=PLATFORMS["systemd"][1])
    link = user / ".config" / "systemd" / "user" / "default.target.wants" / triggers.UNIT
    assert link.is_symlink() and link.resolve() == Path(got["path"]).resolve()


def test_tck_ac1_status_reports_a_missing_shim_as_broken_and_install_rewrites_it(user: Path) -> None:
    home = home_path()
    triggers.install(home, platform="linux", user_home=user, which=PLATFORMS["systemd"][1])
    shim = shimmod.shim_path(home)
    assert triggers.status(home, platform="linux", user_home=user)[0]["state"] == "installed"
    shim.unlink()  # the shim was deleted
    (row,) = triggers.status(home, platform="linux", user_home=user)
    assert row["state"] == "broken" and row["trigger"] == "os:systemd"
    again = triggers.install(home, platform="linux", user_home=user, which=PLATFORMS["systemd"][1])
    assert shim.is_file() and triggers.status(home, platform="linux", user_home=user)[0]["state"] == "installed"
    assert again["written"] is False  # the entry's text was right; the shim it names is what was missing


def test_tck_b8_an_entry_whose_shim_path_changed_is_rewritten_and_one_that_did_not_is_left(user: Path) -> None:
    home = home_path()
    path = triggers.entry_path("systemd", home, user)
    path.parent.mkdir(parents=True)
    path.write_text(triggers.render("systemd", Path("/old/engines/bin/tempergraph")), encoding="utf-8")  # before the update
    assert triggers.status(home, platform="linux", user_home=user)[0]["state"] == "broken"
    assert triggers.refresh(home, platform="linux", user_home=user) == ["systemd"]
    assert str(triggers.shim_for(home, "linux")) in path.read_text(encoding="utf-8")
    before = path.stat().st_mtime_ns
    assert triggers.refresh(home, platform="linux", user_home=user) == [] and path.stat().st_mtime_ns == before
    assert triggers.refresh(home_path() / "none", platform="linux", user_home=user / "nobody") == []  # no entry: nothing


def test_tck_ac1_remove_deletes_what_install_wrote_and_leaves_no_trace(user: Path) -> None:
    home = home_path()
    home.mkdir(parents=True, exist_ok=True)
    before = hash_tree(user), {k: v for k, v in hash_tree(home).items() if "bin" not in k}
    for kind in ("systemd", "launchagent", "crontab"):
        platform, which = PLATFORMS[kind]
        triggers.install(home, platform=platform, user_home=user, which=which)
    assert triggers.entries_present(home, user)
    gone = triggers.remove(home, user_home=user)
    assert len(gone) == 3 and not triggers.entries_present(home, user)
    assert hash_tree(user) == before[0]  # the user's folders are as they were
    assert {k: v for k, v in hash_tree(home).items() if "bin" not in k} == before[1]
    assert triggers.remove(home, user_home=user) == []


def test_tck_b14_a_shim_path_a_crontab_line_cannot_carry_is_refused() -> None:
    with pytest.raises(triggers.UnsafePath):
        triggers.render("crontab", Path("/home/a b/.tempergraph/bin/tempergraph"))
    with pytest.raises(triggers.UnsafePath):
        triggers.render("crontab", Path("/home/x;rm -rf ~/tempergraph"))


def test_tck_b14_no_usable_scheduler_exits_2_no_os_scheduler_while_loop_and_tick_still_work(
        repo: Path, user: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tempergraph import detach

    monkeypatch.setattr(triggers, "PLATFORM", "linux")
    monkeypatch.setattr("shutil.which", lambda name: None)
    before = home_hash()
    code, _, err = sched(repo, "trigger", "install", "--os")
    assert code == 2 and "no_os_scheduler" in err and home_hash() == before and not any(user.rglob("*"))
    monkeypatch.setattr(detach, "start_loop", lambda home, shim=None: True)
    assert sched(repo, "loop", "--detach")[0] == 0 and sched(repo, "tick")[0] == 0  # both still work


def test_tck_b1_install_os_run_twice_leaves_exactly_one_entry_and_names_the_shim_and_the_loop_only(
        repo: Path, user: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(triggers, "PLATFORM", "darwin")
    code, doc, err = sched(repo, "trigger", "install", "--os", "--json")
    assert code == 0 and doc["kind"] == "launchagent", err
    assert sched(repo, "trigger", "install", "--os", "--json")[1]["written"] is False
    entries = [p for p in user.rglob("*") if p.is_file()]
    assert len(entries) == 1 and entries[0].name == f"{triggers.LABEL}.plist"
    text = entries[0].read_text(encoding="utf-8")
    assert str(shimmod.shim_path(home_path())) in text and "<string>schedule</string>" in text and "<string>loop</string>" in text
    assert sched(repo, "trigger", "install")[0] == 2  # `--os` names the adapter


def test_tck_b15_status_lists_every_trigger_seen_with_the_last_error_and_writes_nothing(
        repo: Path, user: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tempergraph.docs import write_json

    monkeypatch.setattr(triggers, "PLATFORM", "linux")
    monkeypatch.setattr("shutil.which", lambda name: "/bin/systemctl")
    assert sched(repo, "trigger", "install", "--os")[0] == 0
    shimmod.shim_path(home_path()).unlink()  # broken
    write_json(tick.heartbeat_path(home_path()), {"schema_version": 1, "last_tick_at": "2026-11-23T08:20:30Z", "interval_s": 300,
                                                  "trigger": "external", "last_error": "RuntimeError: x"})
    before, user_before = home_hash(), hash_tree(user)
    code, doc, err = sched(repo, "trigger", "status", "--json")
    assert code == 0, err
    rows = {r["trigger"]: r for r in doc["triggers"]}
    assert set(rows) == {"loop", "hook", "os:systemd", "external"}
    assert rows["os:systemd"]["state"] == "broken" and rows["os:systemd"]["last_error"]
    assert rows["external"]["last_error"] == "RuntimeError: x" and rows["loop"]["state"] == "stopped"
    assert doc["heartbeat"]["trigger"] == "external" and doc["heartbeat"]["age_s"] == 600.0
    assert home_hash() == before and hash_tree(user) == user_before  # read-only
    code, text, _ = sched(repo, "trigger", "status")
    assert code == 0 and "os:systemd\tbroken" in text and "last tick: 2026-11-23T08:20:30Z (600.0s ago, trigger external)" in text


def test_tck_b15_remove_through_the_cli_deletes_the_entry(repo: Path, user: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(triggers, "PLATFORM", "darwin")
    sched(repo, "trigger", "install", "--os")
    code, doc, _ = sched(repo, "trigger", "remove", "--json")
    assert code == 0 and len(doc["removed"]) == 1 and not triggers.entries_present(home_path(), user)


def test_tck_b15_an_os_entry_counts_as_a_live_trigger_for_schedule_add(repo: Path, user: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from .test_schedule_cli import add

    monkeypatch.setattr(triggers, "PLATFORM", "darwin")
    assert "trigger_warning" in add(repo)[1]
    sched(repo, "trigger", "install", "--os")
    assert "trigger_warning" not in add(repo)[1]
