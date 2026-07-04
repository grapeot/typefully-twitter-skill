"""Tests for URL/domain validation in Twitter post copy.

These tests verify that the url_validator module correctly:
1. Allows exactly one URL on the allowed domain (yage.ai)
2. Flags external explicit URLs (https://other.com)
3. Flags bare-domain tokens (Character.AI, thereallo.dev, github.com)
4. Does not flag false positives (file.py, e.g., common abbreviations)
5. Reports no-URL and multiple-URL errors correctly
"""

from __future__ import annotations

import pytest

from typefully_twitter_skill.url_validator import (
    BARE_DOMAIN_RE,
    check_post_urls,
    find_url_like_tokens,
)


class TestFindUrlLikeTokens:
    """Tests for the token finder."""

    def test_explicit_url(self):
        tokens = find_url_like_tokens("see https://yage.ai/share/foo")
        assert len(tokens) == 1
        assert tokens[0].kind == "explicit_url"
        assert tokens[0].domain == "yage.ai"

    def test_bare_domain_character_ai(self):
        tokens = find_url_like_tokens("the Character.AI case shows")
        assert len(tokens) == 1
        assert tokens[0].kind == "bare_domain"
        assert tokens[0].text == "Character.AI"

    def test_bare_domain_thereallo_dev(self):
        tokens = find_url_like_tokens("thereallo.dev wrote a blog")
        assert len(tokens) == 1
        assert tokens[0].kind == "bare_domain"
        assert tokens[0].text == "thereallo.dev"

    def test_bare_domain_github_com(self):
        tokens = find_url_like_tokens("filed github.com issue")
        assert len(tokens) == 1
        assert tokens[0].text == "github.com"

    def test_no_false_positive_file_py(self):
        tokens = find_url_like_tokens("run the file.py script")
        assert len(tokens) == 0

    def test_no_false_positive_abbreviations(self):
        tokens = find_url_like_tokens("see e.g. the config")
        assert len(tokens) == 0

    def test_no_false_positive_sentence_period(self):
        # "This is fine." should not match
        tokens = find_url_like_tokens("This is fine. Also that.")
        assert len(tokens) == 0

    def test_mixed_explicit_and_bare(self):
        tokens = find_url_like_tokens(
            "Character.AI had issues. See https://yage.ai/share/x"
        )
        assert len(tokens) == 2
        kinds = {t.kind for t in tokens}
        assert kinds == {"explicit_url", "bare_domain"}


class TestCheckPostUrls:
    """Tests for the full check function."""

    def test_pass_single_yage_url(self):
        text = "Some analysis here.\n\nhttps://yage.ai/share/foo?utm_source=twitter"
        result = check_post_urls(text)
        assert result.passed is True
        assert len(result.errors) == 0

    def test_fail_no_url(self):
        text = "Some analysis with no URL at all"
        result = check_post_urls(text)
        assert result.passed is False
        assert "No URL-like tokens" in result.errors[0]

    def test_fail_external_explicit_url(self):
        text = "See https://example.com for more.\n\nhttps://yage.ai/share/foo"
        result = check_post_urls(text)
        assert result.passed is False
        assert any("Disallowed" in e for e in result.errors)

    def test_fail_bare_domain_character_ai(self):
        text = (
            "Character.AI had a case where a teen was harmed.\n\n"
            "https://yage.ai/share/foo?utm_source=twitter"
        )
        result = check_post_urls(text)
        assert result.passed is False
        assert any("Character.AI" in e for e in result.errors)

    def test_fail_bare_domain_thereallo_dev(self):
        text = (
            "thereallo.dev discovered the steganography.\n\n"
            "https://yage.ai/share/foo"
        )
        result = check_post_urls(text)
        assert result.passed is False
        assert any("thereallo.dev" in e for e in result.errors)

    def test_pass_when_domain_mentioned_as_name_not_tld(self):
        # "Character AI" without the dot should NOT be flagged
        text = (
            "Character AI had a case where a teen was harmed.\n\n"
            "https://yage.ai/share/foo?utm_source=twitter"
        )
        result = check_post_urls(text)
        assert result.passed is True

    def test_fail_multiple_yage_urls(self):
        text = "https://yage.ai/share/a and https://yage.ai/share/b"
        result = check_post_urls(text)
        assert result.passed is False
        assert "Multiple URLs" in result.errors[0]

    def test_fail_only_external_no_yage(self):
        text = "See https://example.com for details"
        result = check_post_urls(text)
        assert result.passed is False
        assert "No URL on allowed domain" in result.errors[0]

    def test_pass_with_utm_params(self):
        text = (
            "Full analysis:\n\n"
            "https://yage.ai/share/uga-sunset-20260704.html"
            "?utm_source=twitter&utm_medium=thread&utm_campaign=uga-sunset-20260704"
        )
        result = check_post_urls(text)
        assert result.passed is True


class TestBareDomainRegex:
    """Targeted tests for the bare-domain regex edge cases."""

    def test_does_not_match_inside_word(self):
        # "app.config" in prose should match (it looks like a domain)
        # but "configuration" should NOT match
        tokens = find_url_like_tokens("the configuration file")
        assert len(tokens) == 0

    def test_does_not_match_email(self):
        # user@host.com should not produce a bare-domain match
        # because the @ precedes the domain part
        tokens = find_url_like_tokens("contact user@host.com for help")
        # The regex has a negative lookbehind for @, so this should be 0
        # (the @host.com part is preceded by @)
        bare = [t for t in tokens if t.kind == "bare_domain"]
        assert len(bare) == 0

    def test_matches_dotted_product_name_as_domain(self):
        # "Character.AI" is a real domain — this SHOULD be flagged
        tokens = find_url_like_tokens("via Character.AI")
        assert len(tokens) == 1
        assert tokens[0].text == "Character.AI"

    def test_does_not_match_version_numbers(self):
        tokens = find_url_like_tokens("version 2.0 is out")
        # "2.0" — 0 is not a letter, so the TLD part [a-zA-Z]{2,12} fails
        assert len(tokens) == 0