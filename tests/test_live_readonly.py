from __future__ import annotations

import os

import pytest

from typefully_twitter_skill.config import Settings, load_dotenv
from typefully_twitter_skill.typefully_post import TypefullyPostClient
from typefully_twitter_skill.x_analytics import XAnalyticsClient, extract_posts, window_from_args


pytestmark = pytest.mark.live_integration


def require_live() -> None:
    if os.getenv("TYPEFULLY_TWITTER_ENABLE_LIVE_TESTS") != "1":
        pytest.skip("Set TYPEFULLY_TWITTER_ENABLE_LIVE_TESTS=1 to run read-only live tests")


def test_live_typefully_api_readonly():
    require_live()
    load_dotenv()
    settings = Settings.from_env()
    if not settings.has_typefully_api():
        pytest.skip("TYPEFULLY_API_KEY not configured")
    client = TypefullyPostClient(settings)
    me = client.me()
    social_sets = client.social_sets()
    assert me is not None
    assert social_sets is not None


def test_live_x_analytics_readonly():
    require_live()
    load_dotenv()
    settings = Settings.from_env()
    if not settings.has_x_analytics():
        pytest.skip("X analytics cookies not configured")
    from_iso, to_iso = window_from_args(days=1)
    raw = XAnalyticsClient(settings).fetch_posts(from_iso, to_iso)
    rows = extract_posts(raw)
    assert isinstance(rows, list)
