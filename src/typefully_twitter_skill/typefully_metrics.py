"""Typefully private web metrics client."""

from __future__ import annotations

from typing import Any

import requests

from .config import Settings
from .errors import ApiError


METRIC_ENDPOINTS = {
    "published_tweets": "published-tweets-count",
    "impressions": "impressions",
    "profile_clicks": "user-profile-clicks",
    "followers": "followers-count",
    "engagements": "engagements",
    "engagement_rate": "engagement-rate",
    "engagement_heatmap": "engagement-heatmap",
}


class TypefullyMetricsClient:
    def __init__(self, settings: Settings) -> None:
        settings.require_typefully_metrics()
        self.base_url = settings.typefully_base_url.rstrip("/")
        self.timeout = settings.typefully_timeout
        self.authorization = settings.typefully_authorization or ""
        self.account = settings.typefully_account or ""
        self.session = settings.typefully_session or ""
        self.cookie = settings.typefully_cookie or ""

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.base_url}/grow",
            "Session": self.session,
            "Account": self.account,
            "Authorization": self.authorization,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        response = requests.get(f"{self.base_url}{path}", headers=self._headers(), params=params, timeout=self.timeout)
        if response.status_code >= 400:
            raise ApiError("typefully_metrics", response.status_code, response.text)
        if not response.text.strip():
            return {}
        return response.json()

    def accounts(self) -> Any:
        return self._get("/api/backend/accounts-v2")

    def metric(self, name: str, start_date: str, end_date: str) -> Any:
        endpoint = METRIC_ENDPOINTS.get(name)
        if not endpoint:
            valid = ", ".join(sorted(METRIC_ENDPOINTS))
            raise ValueError(f"Unknown metric '{name}'. Valid metrics: {valid}")
        return self._get(f"/api/backend-alt/metric/{endpoint}", {"start_date": start_date, "end_date": end_date})

    def snapshot(self, start_date: str, end_date: str) -> dict[str, Any]:
        return {"start_date": start_date, "end_date": end_date, "metrics": {name: self.metric(name, start_date, end_date) for name in METRIC_ENDPOINTS}}
