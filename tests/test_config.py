from __future__ import annotations

from pathlib import Path

from typefully_twitter_skill.config import Settings, env_bool, load_dotenv


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


def test_env_bool_parses_common_values(monkeypatch):
    monkeypatch.setenv("TYPEFULLY_TWITTER_DEFAULT_LONG_POST", "yes")
    assert env_bool("TYPEFULLY_TWITTER_DEFAULT_LONG_POST") is True

    monkeypatch.setenv("TYPEFULLY_TWITTER_DEFAULT_LONG_POST", "0")
    assert env_bool("TYPEFULLY_TWITTER_DEFAULT_LONG_POST") is False

    monkeypatch.delenv("TYPEFULLY_TWITTER_DEFAULT_LONG_POST", raising=False)
    assert env_bool("TYPEFULLY_TWITTER_DEFAULT_LONG_POST") is False


def test_settings_reports_default_long_post(monkeypatch):
    monkeypatch.setenv("TYPEFULLY_TWITTER_DEFAULT_LONG_POST", "true")

    settings = Settings.from_env()
    payload = settings.doctor_payload()

    assert settings.default_long_post is True
    assert payload["posting"]["default_long_post"] is True


def test_settings_resolves_1password_references(monkeypatch):
    monkeypatch.setenv("TYPEFULLY_API_KEY", "op://vault/item/api-key")
    monkeypatch.setenv("TYPEFULLY_AUTHORIZATION", "op://vault/item/authorization")
    monkeypatch.setenv("TYPEFULLY_ACCOUNT", "op://vault/item/account")
    monkeypatch.setenv("TYPEFULLY_SESSION", "op://vault/item/session")
    monkeypatch.setenv("X_AUTH_TOKEN", "op://vault/item/x-auth")
    monkeypatch.setenv("X_CSRF_TOKEN", "op://vault/item/x-csrf")

    from typefully_twitter_skill import config

    values = {
        "op://vault/item/api-key": "api-key",
        "op://vault/item/authorization": "authorization",
        "op://vault/item/account": "account",
        "op://vault/item/session": "session",
        "op://vault/item/x-auth": "x-auth",
        "op://vault/item/x-csrf": "x-csrf",
    }

    class Result:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(args, **kwargs):
        assert args[:2] == ["op", "read"]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        return Result(values[args[2]] + "\n")

    monkeypatch.setattr(config.subprocess, "run", fake_run)

    settings = Settings.from_env()

    assert settings.typefully_api_key == "api-key"
    assert settings.has_typefully_metrics() is True
    assert settings.x_auth_token == "x-auth"
    assert settings.x_csrf_token == "x-csrf"
    assert settings.has_x_analytics() is True
