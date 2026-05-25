from __future__ import annotations

import pytest

from typefully_twitter_skill.typefully_post import count_posts, parse_thread_text, validate_posts, weighted_tweet_length


def test_thread_parser_uses_dash_separator():
    assert parse_thread_text("one\n---\ntwo") == ["one", "two"]


def test_url_counts_as_transformed_length():
    assert weighted_tweet_length("a https://example.com/very/long/path") == 1 + 1 + 23


def test_cjk_counts_as_two():
    assert weighted_tweet_length("你好") == 4


def test_count_posts_marks_too_long():
    rows = count_posts(["x" * 281])
    assert rows[0]["status"] == "TOO_LONG"


def test_long_post_allows_over_standard_limit():
    validate_posts(["x" * 281], long_post=True)
    with pytest.raises(ValueError):
        validate_posts(["x" * 281], long_post=False)
