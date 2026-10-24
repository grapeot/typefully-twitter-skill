"""Tests for URL/domain validation in Twitter post copy.

These tests verify that the url_validator module correctly:
1. Allows exactly one URL on the allowed domain (example.com)
2. Flags external explicit URLs (https://other.com)
3. Flags bare-domain tokens (Character.AI, thereallo.dev, github.com)
4. Does not flag false positives (file.py, e.g., common abbreviations)
5. Reports no-URL and multiple-URL errors correctly
"""

from __future__ import annotations

from typefully_twitter_skill.url_validator import (
    BARE_DOMAIN_RE,
    check_post_urls,
    find_url_like_tokens,
)

ALLOWED = "example.com"


class TestFindUrlLikeTokens:
    """Tests for the token finder."""

    def test_explicit_url(self):
        tokens = find_url_like_tokens(f"see https://{ALLOWED}/share/foo")
        assert len(tokens) == 1
        assert tokens[0].kind == "explicit_url"
        assert tokens[0].domain == ALLOWED

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
        tokens = find_url_like_tokens("This is fine. Also that.")
        assert len(tokens) == 0

    def test_mixed_explicit_and_bare(self):
        tokens = find_url_like_tokens(
            f"Character.AI had issues. See https://{ALLOWED}/share/x"
        )
        assert len(tokens) == 2
        kinds = {t.kind for t in tokens}
        assert kinds == {"explicit_url", "bare_domain"}


class TestCheckPostUrls:
    """Tests for the full check function."""

    def test_pass_single_allowed_url(self):
        text = f"Some analysis here.\n\nhttps://{ALLOWED}/share/foo?utm_source=twitter"
        result = check_post_urls(text, allowed_domain=ALLOWED)
        assert result.passed is True
        assert len(result.errors) == 0

    def test_fail_no_url(self):
        text = "Some analysis with no URL at all"
        result = check_post_urls(text, allowed_domain=ALLOWED)
        assert result.passed is False
        assert "No URL-like tokens" in result.errors[0]

    def test_fail_external_explicit_url(self):
        text = f"See https://other-site.com for more.\n\nhttps://{ALLOWED}/share/foo"
        result = check_post_urls(text, allowed_domain=ALLOWED)
        assert result.passed is False
        assert any("Disallowed" in e for e in result.errors)

    def test_fail_bare_domain_character_ai(self):
        text = (
            "Character.AI had a case where a teen was harmed.\n\n"
            f"https://{ALLOWED}/share/foo?utm_source=twitter"
        )
        result = check_post_urls(text, allowed_domain=ALLOWED)
        assert result.passed is False
        assert any("Character.AI" in e for e in result.errors)

    def test_fail_bare_domain_thereallo_dev(self):
        text = (
            "thereallo.dev discovered the steganography.\n\n"
            f"https://{ALLOWED}/share/foo"
        )
        result = check_post_urls(text, allowed_domain=ALLOWED)
        assert result.passed is False
        assert any("thereallo.dev" in e for e in result.errors)

    def test_pass_when_domain_mentioned_as_name_not_tld(self):
        text = (
            "Character AI had a case where a teen was harmed.\n\n"
            f"https://{ALLOWED}/share/foo?utm_source=twitter"
        )
        result = check_post_urls(text, allowed_domain=ALLOWED)
        assert result.passed is True

    def test_fail_multiple_allowed_urls(self):
        text = f"https://{ALLOWED}/share/a and https://{ALLOWED}/share/b"
        result = check_post_urls(text, allowed_domain=ALLOWED)
        assert result.passed is False
        assert "Multiple URLs" in result.errors[0]

    def test_fail_only_external_no_allowed(self):
        text = "See https://other-site.com for details"
        result = check_post_urls(text, allowed_domain=ALLOWED)
        assert result.passed is False
        assert "No URL on allowed domain" in result.errors[0]

    def test_pass_with_utm_params(self):
        text = (
            "Full analysis:\n\n"
            f"https://{ALLOWED}/share/article-20260704.html"
            "?utm_source=twitter&utm_medium=thread&utm_campaign=article-20260704"
        )
        result = check_post_urls(text, allowed_domain=ALLOWED)
        assert result.passed is True


class TestBareDomainRegex:
    """Targeted tests for the bare-domain regex edge cases."""

    def test_does_not_match_inside_word(self):
        tokens = find_url_like_tokens("the configuration file")
        assert len(tokens) == 0

    def test_does_not_match_email(self):
        tokens = find_url_like_tokens("contact user@host.com for help")
        bare = [t for t in tokens if t.kind == "bare_domain"]
        assert len(bare) == 0

    def test_matches_dotted_product_name_as_domain(self):
        tokens = find_url_like_tokens("via Character.AI")
        assert len(tokens) == 1
        assert tokens[0].text == "Character.AI"

    def test_does_not_match_version_numbers(self):
        tokens = find_url_like_tokens("version 2.0 is out")
        assert len(tokens) == 0

class TestMultiDomain:
    """Multiple allowed domains, subdomains, and expected URL counts."""

    def test_two_links_on_two_allowed_domains(self):
        from typefully_twitter_skill.url_validator import check_post_urls
        text = "watch https://www.youtube.com/watch?v=abc and https://www.example.com/post?utm_source=x"
        r = check_post_urls(text, allowed_domain=["youtube.com", "example.com"], include_subdomains=True, expected_count=2)
        assert r.passed, r.errors

    def test_subdomain_rejected_without_flag(self):
        from typefully_twitter_skill.url_validator import check_post_urls
        r = check_post_urls("see https://www.example.com/x", allowed_domain="example.com")
        assert not r.passed

    def test_lookalike_domain_is_not_a_subdomain(self):
        from typefully_twitter_skill.url_validator import check_post_urls
        r = check_post_urls("see https://badexample.com/x", allowed_domain="example.com", include_subdomains=True)
        assert not r.passed

    def test_expected_count_mismatch(self):
        from typefully_twitter_skill.url_validator import check_post_urls
        r = check_post_urls("one https://example.com/a", allowed_domain="example.com", expected_count=2)
        assert not r.passed
        assert "expected exactly 2" in r.errors[0]

    def test_thread_per_post_expected_counts(self):
        from typefully_twitter_skill.url_validator import check_thread_posts
        posts = ["main https://www.example.net/video/1", "reply https://example.com/a\nhttps://youtu.be/x"]
        results = check_thread_posts(
            posts,
            allowed_domain=["example.net", "example.com", "youtu.be"],
            include_subdomains=True,
            expected_counts={2: 2},
        )
        assert [r["passed"] for r in results] == [True, True, True]
        assert results[-1]["expected_urls"] == 3

    def test_cli_repeatable_allowed_domain(self, capsys):
        import json
        from typefully_twitter_skill.cli import main
        code = main([
            "post", "check-urls", "--text", "a https://www.youtube.com/watch?v=1\\nb https://example.com/x",
            "--allowed-domain", "youtube.com", "--allowed-domain", "example.com", "--include-subdomains",
            "--expected-urls", "2", "--format", "json",
        ])
        out = json.loads(capsys.readouterr().out)
        assert code == 0 and out["all_passed"]
