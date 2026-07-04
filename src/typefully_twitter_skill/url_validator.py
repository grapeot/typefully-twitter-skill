"""URL and domain-like-text validator for Twitter/X post copy.

Twitter's card preview grabs the first URL-like token it finds. If the post
body contains an external domain (even without a protocol, e.g. ``Character.AI``
or ``openai.com``), Twitter may treat it as a URL and use that site's card as
the hero preview, overriding the intended yage.ai link.

This module scans post text for two categories of URL-like content:

1. Explicit URLs: ``https?://...``
2. Bare-domain tokens: text matching a domain pattern (``something.tld``)
   without a protocol prefix. This catches things like ``Character.AI``,
   ``thereallo.dev``, ``github.com``.

The validator enforces that the entire post body contains exactly one
URL-like token, and that token must be the yage.ai tracked URL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Explicit URL: http(s)://...
EXPLICIT_URL_RE = re.compile(r"https?://\S+")

# Bare-domain token: matches ``word.tld`` patterns where tld is a known
# short TLD (2-6 chars, letters only, including things like .ai, .dev,
# .com, .org, .io, .net, .so, .cn, .me, .app, .run, .sh, .py, .rs, .go,
# .js, .ts, .tv, .fm, .to, .cc, .ly, .gg, .sg, .hk, .tw, .jp, .uk, .eu,
# .ai, .dev, .app, .io, .so, .sh, .run, .go, .rs, .js, .ts, .py, .fm,
# .to, .cc, .ly, .gg, .me, .cn, .hk, .tw, .jp, .uk, .eu, .com, .org,
# .net, .info, .biz, .name, .pro, .mobi, .tv, .co)
# We intentionally keep this broad — better to over-match and let a human
# review than to miss a token that Twitter's card parser picks up.
BARE_DOMAIN_RE = re.compile(
    r"(?<![a-zA-Z0-9@/])"        # not preceded by word char, @, or /
    r"([a-zA-Z0-9]"              # first char: alnum
    r"(?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)"  # middle + last
    r"\."
    r"([a-zA-Z]{2,12})"          # TLD: 2-12 letters
    r"(?![a-zA-Z0-9])"           # not followed by alnum (avoid matching inside longer text)
)

# Known false-positive patterns that look like domains but aren't URLs.
# These are common in technical writing and should not be flagged.
NON_DOMAIN_PATTERNS = {
    # File extensions in prose: "file.py", "app.js", "config.ts"
    "file_extensions": frozenset({"py", "js", "ts", "go", "rs", "sh", "rb", "cpp", "c", "h",
        "java", "kt", "swift", "scala", "clj", "ex", "exs", "erl", "hs",
        "ml", "fs", "vb", "cs", "pl", "pm", "lua", "r", "m", "mm"}),
    # Common abbreviations that look like domains
    "abbreviations": frozenset({"e.g", "i.e", "vs", "etc", "fig", "tab", "eq", "no",
        "dr", "mr", "mrs", "ms", "prof", "st", "ave", "blvd", "dept",
        "approx", "min", "max", "avg", "std", "var", "len", "cnt",
        "obj", "arr", "idx", "val", "key", "num", "str", "bool",
        "int", "flt", "dbl", "chr", "buf", "ptr", "ref", "src",
        "dst", "tmp", "var", "ret", "req", "res", "err", "log",
        "dbg", "cfg", "env", "ctx", "app", "lib", "bin", "dev",
        "sys", "net", "api", "cli", "sdk", "uid", "gid", "pid",
        "tid", "mid", "sid", "did", "oid", "fid", "rid", "xid",
        "gid", "vid", "wid", "yid", "zid"}),
}


@dataclass
class UrlFinding:
    """A single URL-like token found in the text."""
    text: str
    start: int
    end_pos: int
    kind: str  # "explicit_url" or "bare_domain"
    domain: str = ""


@dataclass
class UrlCheckResult:
    """Result of checking a post body for URL uniqueness."""
    findings: list[UrlFinding] = field(default_factory=list)
    allowed_domain: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed: bool = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "allowed_domain": self.allowed_domain,
            "findings": [
                {"text": f.text, "kind": f.kind, "domain": f.domain}
                for f in self.findings
            ],
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _is_false_positive(label: str, tld: str) -> bool:
    """Check if a bare-domain match is a known false positive (e.g. file.py)."""
    tld_lower = tld.lower()
    if tld_lower in NON_DOMAIN_PATTERNS["file_extensions"]:
        return True
    if label.lower() in NON_DOMAIN_PATTERNS["abbreviations"]:
        return True
    return False


def find_url_like_tokens(text: str) -> list[UrlFinding]:
    """Find all URL-like tokens in the text.

    Returns explicit URLs first, then bare-domain tokens that don't
    overlap with any explicit URL.
    """
    findings: list[UrlFinding] = []

    # 1. Explicit URLs
    for m in EXPLICIT_URL_RE.finditer(text):
        findings.append(UrlFinding(
            text=m.group(),
            start=m.start(),
            end_pos=m.end(),
            kind="explicit_url",
            domain=_extract_domain(m.group()),
        ))

    # 2. Bare-domain tokens (skip those overlapping with explicit URLs)
    for m in BARE_DOMAIN_RE.finditer(text):
        # Check overlap with existing findings
        overlaps = any(
            m.start() < f.end_pos and m.end() > f.start
            for f in findings
        )
        if overlaps:
            continue

        label = m.group(1)
        tld = m.group(2)
        if _is_false_positive(label, tld):
            continue

        full = m.group()
        findings.append(UrlFinding(
            text=full,
            start=m.start(),
            end_pos=m.end(),
            kind="bare_domain",
            domain=full,
        ))

    return findings


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL like https://yage.ai/share/..."""
    m = re.match(r"https?://([^/\s]+)", url)
    return m.group(1) if m else ""


def check_post_urls(
    text: str,
    *,
    allowed_domain: str = "yage.ai",
) -> UrlCheckResult:
    """Check that a post body contains exactly one URL-like token,
    and that token's domain matches ``allowed_domain``.

    Args:
        text: The full post body (all tweets concatenated or a single tweet).
        allowed_domain: The domain that the single allowed URL must belong to.

    Returns:
        UrlCheckResult with findings, errors, warnings, and passed flag.
    """
    result = UrlCheckResult(allowed_domain=allowed_domain)
    findings = find_url_like_tokens(text)
    result.findings = findings

    if not findings:
        result.errors.append("No URL-like tokens found. T (traffic) posts must contain the yage.ai tracked URL.")
        result.passed = False
        return result

    # Filter: which findings are on the allowed domain?
    allowed_findings = [
        f for f in findings
        if f.domain.lower() == allowed_domain.lower()
    ]
    disallowed_findings = [
        f for f in findings
        if f.domain.lower() != allowed_domain.lower()
    ]

    if len(allowed_findings) == 0:
        result.errors.append(
            f"No URL on allowed domain ({allowed_domain}) found. "
            f"The post contains {len(findings)} URL-like token(s) but none on {allowed_domain}."
        )
        result.passed = False
        return result

    if len(allowed_findings) > 1:
        result.errors.append(
            f"Multiple URLs on allowed domain ({allowed_domain}) found: "
            f"{len(allowed_findings)}. Expected exactly 1."
        )
        result.passed = False
        return result

    if disallowed_findings:
        for f in disallowed_findings:
            kind_label = "external URL" if f.kind == "explicit_url" else "bare-domain token"
            result.errors.append(
                f"Disallowed {kind_label}: \"{f.text}\" "
                f"(domain: {f.domain}). "
                f"Twitter may use this as the card preview hero, "
                f"overriding the {allowed_domain} link. "
                f"Replace with a name-only mention (e.g. \"the Character.AI case\" "
                f"without the dot-TLD pattern, or rephrase to avoid the token)."
            )
        result.passed = False
        return result

    # Exactly 1 finding, on the allowed domain
    result.passed = True
    result.warnings.append(
        f"OK: exactly 1 URL-like token on allowed domain ({allowed_domain}): "
        f"\"{allowed_findings[0].text[:80]}...\" "
        f"kind={allowed_findings[0].kind}"
    )
    return result


def check_thread_file(
    path: str | Path,
    *,
    allowed_domain: str = "yage.ai",
) -> list[dict]:
    """Check a thread file (same format as typefully-twitter --thread-file).

    The file may contain multiple tweets separated by ``---``.
    Each tweet is checked individually, and the full concatenated text
    is also checked (bare-domain tokens can span tweet boundaries in
    Twitter's rendering).

    Returns a list of per-tweet results plus a combined check.
    """
    from .typefully_post import parse_thread_file

    posts = parse_thread_file(path)
    results: list[dict] = []

    for idx, post_text in enumerate(posts, start=1):
        r = check_post_urls(post_text, allowed_domain=allowed_domain)
        results.append({
            "tweet_index": idx,
            **r.to_dict(),
        })

    # Also check the full concatenated text
    full_text = "\n".join(posts)
    combined = check_post_urls(full_text, allowed_domain=allowed_domain)
    results.append({
        "tweet_index": "combined",
        **combined.to_dict(),
    })

    return results