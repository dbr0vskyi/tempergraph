"""The tool's behaviour when `tool.toml` is missing."""

from tool.main import main


def test_missing_config_prints_one_line_naming_the_file(tmp_path, monkeypatch, capsys):  # CFG-AC1
    monkeypatch.chdir(tmp_path)
    main([])
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    assert "tool.toml" in lines[0]
