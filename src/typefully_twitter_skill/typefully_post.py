"""Typefully v2 publishing client and X weighted length helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

from .config import Settings
from .errors import ApiError


DEFAULT_API_BASE = "https://api.typefully.com/v2"
MAX_WEIGHTED_TWEET_LENGTH = 280
MAX_WEIGHTED_LONG_POST_LENGTH = 25_000
TRANSFORMED_URL_LENGTH = 23
URL_RE = re.compile(r"https?://\S+")
WEIGHT_ONE_RANGES: tuple[tuple[int, int], ...] = (
    (0, 4351),
    (8192, 8205),
    (8208, 8223),
    (8242, 8247),
)


def parse_thread_text(text: str) -> list[str]:
    if "---" in text:
        return [part.strip() for part in text.split("---") if part.strip()]
    stripped = text.strip()
    return [stripped] if stripped else []


def parse_thread_file(path: str | Path) -> list[str]:
    return parse_thread_text(Path(path).read_text(encoding="utf-8"))


def _char_weight(char: str) -> int:
    code = ord(char)
    for start, end in WEIGHT_ONE_RANGES:
        if start <= code <= end:
            return 1
    return 2


def weighted_tweet_length(text: str) -> int:
    total = 0
    pos = 0
    for match in URL_RE.finditer(text):
        total += sum(_char_weight(ch) for ch in text[pos:match.start()])
        total += TRANSFORMED_URL_LENGTH
        pos = match.end()
    total += sum(_char_weight(ch) for ch in text[pos:])
    return total


def count_posts(posts: list[str], *, long_post: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    limit = MAX_WEIGHTED_LONG_POST_LENGTH if long_post else MAX_WEIGHTED_TWEET_LENGTH
    for idx, text in enumerate(posts, start=1):
        weighted = weighted_tweet_length(text)
        rows.append({
            "index": idx,
            "weighted_length": weighted,
            "limit": limit,
            "long_post": long_post,
            "status": "OK" if weighted <= limit else "TOO_LONG",
            "text": text,
        })
    return rows


def validate_posts(posts: list[str], *, long_post: bool = False) -> None:
    limit = MAX_WEIGHTED_LONG_POST_LENGTH if long_post else MAX_WEIGHTED_TWEET_LENGTH
    failures = [(idx, weighted_tweet_length(text)) for idx, text in enumerate(posts, start=1) if weighted_tweet_length(text) > limit]
    if failures:
        details = ", ".join(f"tweet {idx}={length}/{limit}" for idx, length in failures)
        raise ValueError(f"Post length validation failed: {details}")


class TypefullyPostClient:
    def __init__(self, settings: Settings) -> None:
        settings.require_typefully_api()
        self.api_key = settings.typefully_api_key or ""
        self.social_set_id = settings.typefully_social_set_id
        self.timeout = settings.typefully_timeout
        self.base_url = DEFAULT_API_BASE

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        response = requests.request(method, url, headers=self._headers(), timeout=self.timeout, **kwargs)
        if response.status_code >= 400:
            raise ApiError("typefully", response.status_code, response.text)
        if not response.text.strip():
            return {}
        return response.json()

    def me(self) -> Any:
        return self._request("GET", f"{self.base_url}/me")

    def social_sets(self) -> Any:
        return self._request("GET", f"{self.base_url}/social-sets")

    def resolve_social_set_id(self) -> str:
        if self.social_set_id:
            return self.social_set_id
        data = self.social_sets()
        results = data.get("results", data if isinstance(data, list) else [])
        if not results:
            raise ApiError("typefully", 404, "No social sets found for this API key")
        self.social_set_id = str(results[0]["id"])
        return self.social_set_id

    def _social_url(self, path: str) -> str:
        return f"{self.base_url}/social-sets/{self.resolve_social_set_id()}{path}"

    def create_draft(self, posts: list[str], *, publish_at: str | None = None, draft_title: str | None = None) -> Any:
        payload: dict[str, Any] = {"platforms": {"x": {"enabled": True, "posts": [{"text": text} for text in posts]}}}
        if publish_at:
            payload["publish_at"] = publish_at
        if draft_title:
            payload["draft_title"] = draft_title
        return self._request("POST", self._social_url("/drafts"), json=payload)

    def update_draft(self, draft_id: str, *, publish_at: str) -> Any:
        return self._request("PATCH", self._social_url(f"/drafts/{draft_id}"), json={"publish_at": publish_at})

    def list_drafts(self, *, status: str | None = None, limit: int = 10, offset: int = 0) -> Any:
        params: dict[str, object] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        return self._request("GET", self._social_url("/drafts"), params=params)

    def get_draft(self, draft_id: str) -> Any:
        return self._request("GET", self._social_url(f"/drafts/{draft_id}"))

    def delete_draft(self, draft_id: str) -> Any:
        return self._request("DELETE", self._social_url(f"/drafts/{draft_id}"))


def compact_draft_summary(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": draft.get("id"),
        "status": draft.get("status"),
        "scheduled_date": draft.get("scheduled_date"),
        "published_at": draft.get("published_at"),
        "x_published_url": draft.get("x_published_url"),
        "preview": draft.get("preview"),
        "raw": draft,
    }


def print_jsonable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
