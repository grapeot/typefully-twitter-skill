from __future__ import annotations

from pathlib import Path

from typefully_twitter_skill.config import Settings, load_dotenv


def test_doctor_reports_partial_capabilities(monkeypatch):
    monkeypatch.setenv("TYPEFULLY_API_KEY", "tf_test_123456")
    monkeypatch.delenv("X_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("X_CSRF_TOKEN", raising=False)

    settings = Settings.from_env()
    payload = settings.doctor_payload()

    assert payload["typefully_api"]["configured"] is True
    assert payload["x_analytics"]["configured"] is False
    assert "post.draft" in payload["available_workflows"]
    assert "x.fetch" not in payload["available_workflows"]


def test_load_dotenv_from_explicit_file(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TYPEFULLY_SOCIAL_SET_ID=999\n", encoding="utf-8")
    monkeypatch.delenv("TYPEFULLY_SOCIAL_SET_ID", raising=False)

    loaded = load_dotenv(str(env))

    assert env in loaded
    assert Settings.from_env().typefully_social_set_id == "999"
