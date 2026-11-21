"""Tests of the missing config file behaviour."""


def test_missing_file_message(run_tool):  # CFG-AC1
    assert run_tool().stderr.count("tool.toml") == 1


