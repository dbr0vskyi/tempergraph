"""`schedule export` (TCK-B11, TCK-B20; TCK-AC6; AC 8): a snippet is printed and nothing is kept."""

from __future__ import annotations

from pathlib import Path

import pytest

from tempergraph.cli import schedule_cli
from tempergraph.schedule import store
from tempergraph.store.layout import home_path

from .conftest import hash_tree
from .test_schedule_cli import NOW, WARSAW, home_hash, sched

WEEKDAYS = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=0"
SYSTEMS = ("github-actions", "gitlab-ci", "crontab")


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_cli, "CLOCK", lambda: NOW)
    monkeypatch.setattr(schedule_cli, "machine_zone", lambda: (WARSAW, "TZ"))
    monkeypatch.setenv("HOME", str(home_path().parent))  # no cached sign-in of the machine's own user
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-the-secret-value")  # the key is in the environment: it must not reach a snippet


def utc_schedule(repo: Path, rule: str = WEEKDAYS, *extra: str) -> str:
    code, doc, err = sched(repo, "add", "demo", "weekly digest", "--rrule", rule, "--tz", "UTC", "--run-cost-cap", "3", "--yes",
                           "--json", *extra)
    assert code == 0, err
    return str(doc["schedule_id"])


@pytest.mark.parametrize("system", SYSTEMS)
def test_tck_ac6_each_system_prints_a_snippet_and_keeps_nothing(repo: Path, system: str) -> None:
    sid = utc_schedule(repo)
    before, repo_before, entry = home_hash(), hash_tree(repo), store.read_entry(sid)
    code, text, err = sched(repo, "export", sid, "--for", system)
    assert code == 0 and isinstance(text, str) and text, err
    assert "0 8 * * 1-5" in text  # five-field cron, UTC
    assert "--run-cost-cap 3" in text and f"--label schedule-{sid}" in text and "--caller pipeline" in text
    assert f'"$(cat .tempergraph/schedules/{sid}.request.md)"' in text  # the request is read from a file in the repository
    assert "weekly digest" not in text  # never inline, and no person's text
    assert f"origin ci, schedule {{schedule_id: {sid}, declared: true}}" in text and f"ci:{system}" in text
    assert home_hash() == before and hash_tree(repo) == repo_before and store.read_entry(sid) == entry  # nothing is kept


def test_tck_ac6_the_github_snippet_has_the_concurrency_group_and_only_api_key_secrets(repo: Path) -> None:
    sid = utc_schedule(repo, WEEKDAYS, "--overlap", "queue")
    _, text, _ = sched(repo, "export", sid, "--for", "github-actions")
    assert f"group: tempergraph-{sid}" in text and "cancel-in-progress: false" in text and 'cron: "0 8 * * 1-5"' in text
    assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in text
    assert "sk-the-secret-value" not in text and "OAUTH" not in text and "interactive" not in text


def test_tck_b20_a_gitlab_snippet_carries_caller_pipeline_and_reads_the_request_from_a_repository_file(repo: Path) -> None:
    sid = utc_schedule(repo)
    _, text, _ = sched(repo, "export", sid, "--for", "gitlab-ci")
    assert f"resource_group: tempergraph-{sid}" in text and '$CI_PIPELINE_SOURCE == "schedule"' in text
    run = next(line for line in text.splitlines() if "tempergraph run" in line and not line.startswith("#"))
    assert "--caller pipeline" in run and "$(cat .tempergraph/schedules/" in run


def test_tck_ac6_the_crontab_snippet_skips_a_run_still_going_under_overlap_skip(repo: Path) -> None:
    sid = utc_schedule(repo)
    _, text, _ = sched(repo, "export", sid, "--for", "crontab")
    line = next(ln for ln in text.splitlines() if not ln.startswith("#"))
    assert line.startswith("0 8 * * 1-5 cd ") and f"flock -n /tmp/tempergraph-{sid}.lock" in line and "--caller pipeline" in line


def test_tck_ac6_a_secret_of_another_kind_is_never_named(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")  # an oauth token is for a person's machine, not for a pipeline secret
    sid = utc_schedule(repo)
    assert store.read_entry(sid)["executors_checked"][0]["kinds"] == ["oauth_token"]
    _, text, _ = sched(repo, "export", sid, "--for", "github-actions")
    assert "secrets." not in text and "OAUTH" not in text and "tok" not in text.replace("tempergraph", "")


def test_tck_b11_a_calendar_rule_in_a_zone_with_daylight_saving_exits_2_export_needs_utc(repo: Path) -> None:
    code, doc, err = sched(repo, "add", "demo", "digest", "--when", "every weekday at 8:00", "--tz", WARSAW, "--run-cost-cap", "3",
                           "--yes", "--json")
    assert code == 0, err
    sid = str(doc["schedule_id"])
    before = home_hash()
    code, _, err = sched(repo, "export", sid, "--for", "github-actions")
    assert code == 2 and "export_needs_utc" in err and home_hash() == before


def test_tck_b11_pin_offset_prints_todays_offset_and_a_comment_on_the_other_season(repo: Path) -> None:
    _, doc, _ = sched(repo, "add", "demo", "digest", "--when", "every weekday at 8:00", "--tz", WARSAW, "--run-cost-cap", "3",
                      "--yes", "--json")
    _, text, _ = sched(repo, "export", str(doc["schedule_id"]), "--for", "github-actions", "--pin-offset")
    assert 'cron: "0 7 * * 1-5"' in text  # November in Warsaw is UTC+01:00
    assert "(+01:00)" in text and "in summer (+02:00) this job runs at 09:00 local instead of 08:00" in text


def test_tck_b11_a_zone_without_daylight_saving_and_an_hourly_rule_need_no_pin(repo: Path) -> None:
    code, doc, _ = sched(repo, "add", "demo", "digest", "--every", "PT1H", "--tz", WARSAW, "--run-cost-cap", "3", "--yes", "--json")
    assert code == 0
    assert 'cron: "0 * * * *"' in sched(repo, "export", str(doc["schedule_id"]), "--for", "github-actions")[1]  # every hour: no zone
    code, doc, _ = sched(repo, "add", "demo", "digest", "--every", "PT2H", "--tz", "UTC", "--run-cost-cap", "3", "--yes", "--json")
    assert 'cron: "0 */2 * * *"' in sched(repo, "export", str(doc["schedule_id"]), "--for", "github-actions")[1]
    code, doc, _ = sched(repo, "add", "demo", "digest", "--every", "PT2H", "--tz", WARSAW, "--run-cost-cap", "3", "--yes", "--json")
    assert sched(repo, "export", str(doc["schedule_id"]), "--for", "github-actions")[0] == 2  # two hours from a local anchor: needs UTC
    sid = utc_schedule(repo, "FREQ=DAILY;BYHOUR=23;BYMINUTE=30")
    assert "30 23 * * *" in sched(repo, "export", sid, "--for", "crontab")[1]


def test_tck_b20_a_unit_that_crosses_midnight_in_utc_moves_the_weekday(repo: Path) -> None:
    code, doc, err = sched(repo, "add", "demo", "digest", "--rrule", "FREQ=WEEKLY;BYDAY=MO;BYHOUR=1;BYMINUTE=0", "--tz", "Asia/Tokyo",
                           "--run-cost-cap", "3", "--yes", "--json")
    assert code == 0, err
    _, text, _ = sched(repo, "export", str(doc["schedule_id"]), "--for", "github-actions")
    assert 'cron: "0 16 * * 0"' in text  # Monday 01:00 in Tokyo is Sunday 16:00 UTC


def test_tck_b20_a_rule_cron_cannot_hold_is_refused_and_an_unknown_target_too(repo: Path) -> None:
    sid = utc_schedule(repo, "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=8;BYMINUTE=0")
    code, _, err = sched(repo, "export", sid, "--for", "crontab")
    assert code == 2 and "export_not_expressible" in err
    code, _, err = sched(repo, "export", sid, "--for", "jenkins")
    assert code == 2 and err
    assert sched(repo, "export", "nope-0000", "--for", "crontab")[0] == 2
