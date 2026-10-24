"""Typefully v2 publishing client and X weighted length helpers."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

import requests

from .config import Settings
from .errors import ApiError, MediaProcessingError


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

    def create_draft(
        self,
        posts: list[str],
        *,
        publish_at: str | None = None,
        draft_title: str | None = None,
        media: dict[int, list[str]] | None = None,
        made_with_ai: set[int] | None = None,
    ) -> Any:
        """Create an X draft.

        ``media`` maps a zero-based post index to the media IDs attached to
        that post. ``made_with_ai`` is the set of zero-based post indexes
        labeled as made with AI. Without either argument the payload is the
        same as before media support existed.
        """
        x_posts = build_x_posts(posts, media=media, made_with_ai=made_with_ai)
        payload: dict[str, Any] = {"platforms": {"x": {"enabled": True, "posts": x_posts}}}
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

    # Media -----------------------------------------------------------------

    def create_media_upload(self, file_name: str, *, alt_text: str | None = None) -> dict[str, Any]:
        """Ask Typefully for a presigned upload URL. Returns media_id and upload_url."""
        body: dict[str, Any] = {"file_name": file_name}
        if alt_text:
            body["alt_text"] = alt_text
        return self._request("POST", self._social_url("/media/upload"), json=body)

    def put_presigned(self, upload_url: str, path: str | Path, *, timeout: float | None = None) -> int:
        """PUT raw file bytes to the presigned URL.

        The presigned signature was computed without headers, so this request
        must not send Authorization or Content-Type (S3 answers 403
        SignatureDoesNotMatch otherwise). The URL carries a signature and is
        never echoed in errors.
        """
        file_path = Path(path)
        try:
            with file_path.open("rb") as handle:
                response = requests.put(upload_url, data=handle, timeout=timeout or max(self.timeout, 600))
        except requests.RequestException as exc:
            # The exception text embeds the signed URL; report only the error type.
            raise ApiError("typefully_media_upload", 0, f"network error: {type(exc).__name__}") from None
        if response.status_code not in (200, 204):
            raise ApiError("typefully_media_upload", response.status_code, _storage_error_summary(response.text))
        return response.status_code

    def get_media(self, media_id: str) -> dict[str, Any]:
        return self._request("GET", self._social_url(f"/media/{media_id}"))

    def wait_media_ready(
        self,
        media_id: str,
        *,
        timeout: float = 600,
        interval: float = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> dict[str, Any]:
        """Poll media status until ready; raise MediaProcessingError on failed or timeout."""
        deadline = clock() + timeout
        while True:
            info = self.get_media(media_id)
            status = info.get("status")
            if status == "ready":
                return info
            if status == "failed":
                raise MediaProcessingError(media_id, "failed", info.get("error_reason"))
            if clock() >= deadline:
                raise MediaProcessingError(media_id, status or "unknown", f"not ready after {timeout:.0f} s")
            sleep(interval)

    def upload_media(
        self,
        path: str | Path,
        *,
        file_name: str,
        alt_text: str | None = None,
        wait: bool = True,
        timeout: float = 600,
        interval: float = 3,
    ) -> dict[str, Any]:
        """Run the three-step upload and return a summary without the upload URL."""
        created = self.create_media_upload(file_name, alt_text=alt_text)
        media_id = str(created["media_id"])
        self.put_presigned(created["upload_url"], path)
        if not wait:
            return {"media_id": media_id, "file_name": file_name, "status": "uploaded"}
        info = self.wait_media_ready(media_id, timeout=timeout, interval=interval)
        return {**info, "media_id": media_id}


def build_x_posts(
    posts: list[str],
    *,
    media: dict[int, list[str]] | None = None,
    made_with_ai: set[int] | None = None,
) -> list[dict[str, Any]]:
    media = media or {}
    made_with_ai = made_with_ai or set()
    bad = sorted(i for i in [*media, *made_with_ai] if i < 0 or i >= len(posts))
    if bad:
        raise ValueError(f"Post index out of range for a {len(posts)}-post draft: {[i + 1 for i in bad]}")
    x_posts: list[dict[str, Any]] = []
    for idx, text in enumerate(posts):
        item: dict[str, Any] = {"text": text}
        if media.get(idx):
            item["media_ids"] = list(media[idx])
        if idx in made_with_ai:
            item["made_with_ai"] = True
        x_posts.append(item)
    return x_posts


_XML_CODE_RE = re.compile(r"<Code>([^<]{1,100})</Code>")
_XML_MESSAGE_RE = re.compile(r"<Message>([^<]{1,300})</Message>")


def _storage_error_summary(body: str) -> str:
    """Keep only the storage error code and message.

    S3 error bodies can echo the access key ID, string-to-sign, and canonical
    request, so the raw body is never passed through.
    """
    code = _XML_CODE_RE.search(body or "")
    message = _XML_MESSAGE_RE.search(body or "")
    if code or message:
        return ": ".join(m.group(1) for m in (code, message) if m)
    return "upload rejected by storage (body withheld)"


def compact_draft_summary(draft: dict[str, Any]) -> dict[str, Any]:
    x_posts = (((draft.get("platforms") or {}).get("x") or {}).get("posts")) or []
    return {
        "id": draft.get("id"),
        "status": draft.get("status"),
        "scheduled_date": draft.get("scheduled_date"),
        "published_at": draft.get("published_at"),
        "x_published_url": draft.get("x_published_url"),
        "preview": draft.get("preview"),
        "posts": [
            {
                "index": idx,
                "first_line": (post.get("text") or "").split("\n", 1)[0],
                "media_ids": post.get("media_ids") or [],
                "made_with_ai": bool(post.get("made_with_ai")),
            }
            for idx, post in enumerate(x_posts, start=1)
        ],
        "raw": draft,
    }


def print_jsonable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
