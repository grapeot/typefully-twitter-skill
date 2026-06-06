from __future__ import annotations

from typefully_twitter_skill.config import Settings
from typefully_twitter_skill.typefully_metrics import TypefullyMetricsClient
from typefully_twitter_skill.typefully_post import TypefullyPostClient


def base_settings() -> Settings:
    return Settings(
        typefully_api_key="tf_test",
        typefully_social_set_id="123",
        typefully_authorization="auth",
        typefully_account="acct",
        typefully_session="sess",
        typefully_cookie=None,
        typefully_base_url="https://typefully.com",
        typefully_timeout=30,
        x_auth_token=None,
        x_csrf_token=None,
        x_user_id=None,
        data_dir=__import__("pathlib").Path("data"),
        db_path=__import__("pathlib").Path("data/twitter_analytics.db"),
        default_long_post=False,
    )


class FakeResponse:
    status_code = 200
    text = '{"id": 42, "status": "draft"}'

    def json(self):
        return {"id": 42, "status": "draft"}


def test_typefully_post_payload(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("requests.request", fake_request)
    client = TypefullyPostClient(base_settings())
    result = client.create_draft(["hello"], draft_title="test")

    assert result["id"] == 42
    assert calls[0][0] == "POST"
    assert calls[0][2]["json"]["platforms"]["x"]["posts"] == [{"text": "hello"}]


def test_typefully_metric_endpoint(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("requests.get", fake_get)
    client = TypefullyMetricsClient(base_settings())
    result = client.metric("impressions", "2026-01-01", "2026-01-02")

    assert result["id"] == 42
    assert calls[0][0].endswith("/api/backend-alt/metric/impressions")
    assert calls[0][1]["params"] == {"start_date": "2026-01-01", "end_date": "2026-01-02"}
