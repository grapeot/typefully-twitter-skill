from __future__ import annotations

import json

from typefully_twitter_skill.cli import main


def test_cli_count_accepts_format_after_subcommand(capsys):
    code = main(["post", "count", "--text", "hello", "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["posts"][0]["weighted_length"] == 5


def test_cli_missing_typefully_api_gracefully_fails(monkeypatch, capsys):
    monkeypatch.setenv("TYPEFULLY_API_KEY", "")
    code = main(["post", "list", "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 2
    assert out["capability"] == "typefully_api"
    assert "TYPEFULLY_API_KEY" in out["missing_env"]
