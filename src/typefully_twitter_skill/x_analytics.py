"""Read-only X analytics client using analytics.x.com GraphQL endpoints."""

from __future__ import annotations

import csv
import gzip
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import Settings


WEB_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
QUERY_LIST = "8GMAigEhA0xy4rCM1_p7Fw"
QUERY_48H = "-h2rBNSpdLAFEA4VY9iSig"
QUERY_AUDIENCE = "Vq7rpcVS4EwY8Cz_S_KAyQ"
URL_LIST = f"https://x.com/i/api/graphql/{QUERY_LIST}/ContentPostListQuery"
URL_48H = f"https://x.com/i/api/graphql/{QUERY_48H}/PostDetailsProviderFirst48HoursDataQuery"
URL_AUDIENCE = f"https://x.com/i/api/graphql/{QUERY_AUDIENCE}/PostDetailsProviderAudienceQuery"

DEFAULT_METRICS = [
    "Impressions", "Likes", "Engagements", "Bookmark", "Share", "Follows",
    "Replies", "Retweets", "ProfileVisits", "DetailExpands", "UrlClicks",
    "HashtagClicks", "PermalinkClicks",
]
HOURLY_METRICS = [
    "Impressions", "Engagements", "ProfileVisits", "Follows", "Replies",
    "Likes", "Retweets", "Bookmark", "Share", "MediaViews", "VideoViews",
]


def _parse_twitter_date(value: str) -> datetime:
    return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")


class XAnalyticsClient:
    def __init__(self, settings: Settings) -> None:
        settings.require_x_analytics()
        self.auth_token = settings.x_auth_token or ""
        self.csrf_token = settings.x_csrf_token or ""

    def _graphql_get(self, url: str, variables: dict[str, Any], *, max_retries: int = 5) -> dict[str, Any]:
        full_url = url + "?variables=" + urllib.parse.quote(json.dumps(variables, separators=(",", ":")))
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://x.com/i/account_analytics/content",
            "content-type": "application/json",
            "x-twitter-auth-type": "OAuth2Session",
            "x-csrf-token": self.csrf_token,
            "x-twitter-client-language": "en",
            "x-twitter-active-user": "yes",
            "authorization": f"Bearer {WEB_BEARER}",
            "Cookie": f"auth_token={self.auth_token}; ct0={self.csrf_token}; lang=en",
            "Connection": "keep-alive",
        }
        request = urllib.request.Request(full_url, headers=headers)
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    raw = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    data = json.loads(raw.decode("utf-8"))
                if "errors" in data:
                    raise RuntimeError(f"GraphQL errors: {data['errors']}")
                return data
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries:
                    time.sleep(30 * (2**attempt))
                    attempt += 1
                    continue
                body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"X analytics HTTP {exc.code}: {body}") from exc

    def fetch_posts(self, from_iso: str, to_iso: str, *, max_results: int = 1000, page_size: int = 100) -> dict[str, Any]:
        return self._graphql_get(URL_LIST, {
            "from_time": from_iso,
            "to_time": to_iso,
            "max_results": max_results,
            "query_page_size": page_size,
            "requested_metrics": DEFAULT_METRICS,
        })

    def fetch_hourly(self, rest_id: str, from_iso: str, to_iso: str, *, granularity: str = "Hourly") -> list[dict[str, Any]]:
        data = self._graphql_get(URL_48H, {
            "rest_id": rest_id,
            "requested_metrics": HOURLY_METRICS,
            "to_time": to_iso,
            "from_time": from_iso,
            "granularity": granularity,
        })
        series = data["data"]["tweet_result_by_rest_id"]["result"]["organic_metrics_time_series"]
        rows: list[dict[str, Any]] = []
        for entry in series:
            row = {"ts": entry["timestamp"]["iso8601_time"]}
            for metric in entry.get("metric_values", []):
                row[metric["metric_type"]] = int(metric.get("metric_value", 0) or 0)
            rows.append(row)
        return sorted(rows, key=lambda row: str(row["ts"]))

    def fetch_audience(self, rest_id: str, from_ms: int, to_ms: int) -> dict[str, Any]:
        data = self._graphql_get(URL_AUDIENCE, {
            "rest_id": rest_id,
            "from_time_incl": from_ms,
            "to_time_excl": to_ms,
            "dimensions": ["Age", "Gender", "EngagementType", "ClientAppId", "IsInNetwork"],
        })
        result = data["data"]["tweet_result_by_rest_id"]["result"]
        return {
            "rest_id": result.get("rest_id"),
            "country_series": result.get("uec_country_metrics_daily_time_series_count", []),
            "uec_series": result.get("uec_metrics_daily_time_series_count", []),
        }


def window_from_args(days: int | None = None, start: str | None = None, end: str | None = None) -> tuple[str, str]:
    if start and end:
        return f"{start}T00:00:00.000Z", f"{end}T23:59:59.999Z"
    today = datetime.now(timezone.utc).date()
    lookback = days or 28
    return f"{(today - timedelta(days=lookback)).isoformat()}T00:00:00.000Z", f"{today.isoformat()}T23:59:59.999Z"


def extract_posts(raw: dict[str, Any]) -> list[dict[str, Any]]:
    tweets = raw["data"]["viewer_v2"]["user_results"]["result"]["tweets_results"]
    rows: list[dict[str, Any]] = []
    for entry in tweets:
        tweet = entry.get("result", {})
        if tweet.get("__typename") != "Tweet":
            continue
        legacy = tweet.get("legacy", {})
        metrics = {metric["metric_type"]: metric.get("metric_value", 0) for metric in tweet.get("organic_metrics_total", [])}
        rows.append({
            "rest_id": tweet.get("rest_id"),
            "created_at": legacy.get("created_at"),
            "full_text": legacy.get("full_text", ""),
            "permalink": f"https://x.com/i/status/{tweet.get('rest_id')}",
            **{name: int(metrics.get(name, 0) or 0) for name in DEFAULT_METRICS},
        })
    rows.sort(key=lambda row: _parse_twitter_date(row["created_at"]), reverse=True)
    return rows


def write_fetch_outputs(rows: list[dict[str, Any]], raw: dict[str, Any], from_iso: str, to_iso: str, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    start = from_iso[:10].replace("-", "")
    end = to_iso[:10].replace("-", "")
    stem = f"twitter_per_post_{start}_{end}"
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    doc = {"meta": {"from": from_iso, "to": to_iso, "fetched_at": datetime.now(timezone.utc).isoformat(), "n_posts": len(rows)}, "posts": rows, "raw": raw}
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        csv_path.write_text("", encoding="utf-8")
    return {"json_path": str(json_path), "csv_path": str(csv_path)}


def summarize_rows(rows: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    impressions = sum(row["Impressions"] for row in rows)
    engagements = sum(row["Engagements"] for row in rows)
    url_clicks = sum(row["UrlClicks"] for row in rows)
    follows = sum(row["Follows"] for row in rows)
    with_link = [row for row in rows if "https://t.co" in row["full_text"]]
    no_link = [row for row in rows if "https://t.co" not in row["full_text"]]
    def group_stats(group: list[dict[str, Any]]) -> dict[str, Any]:
        imp = sum(row["Impressions"] for row in group)
        clicks = sum(row["UrlClicks"] for row in group)
        return {"n": len(group), "impressions": imp, "url_clicks": clicks, "url_ctr": clicks / max(imp, 1)}
    return {
        "meta": meta or {},
        "totals": {"posts": len(rows), "impressions": impressions, "engagements": engagements, "url_clicks": url_clicks, "follows": follows},
        "rates": {"engagement_rate": engagements / max(impressions, 1), "url_ctr": url_clicks / max(impressions, 1)},
        "with_outbound_link": group_stats(with_link),
        "body_only": group_stats(no_link),
        "top_by_impressions": sorted(rows, key=lambda row: -row["Impressions"])[:10],
        "top_by_url_clicks": sorted(rows, key=lambda row: -row["UrlClicks"])[:10],
    }


SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
  rest_id TEXT PRIMARY KEY,
  created_at_utc TEXT,
  full_text TEXT,
  permalink TEXT,
  has_outbound_link INTEGER,
  impressions INTEGER,
  likes INTEGER,
  engagements INTEGER,
  bookmark INTEGER,
  share INTEGER,
  follows INTEGER,
  replies INTEGER,
  retweets INTEGER,
  profile_visits INTEGER,
  detail_expands INTEGER,
  url_clicks INTEGER,
  hashtag_clicks INTEGER,
  permalink_clicks INTEGER,
  fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS fetch_log (
  run_ts TEXT,
  command TEXT,
  target TEXT,
  status TEXT,
  message TEXT
);
"""


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def upsert_posts(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        created = _parse_twitter_date(row["created_at"]).astimezone(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO posts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rest_id) DO UPDATE SET
              created_at_utc=excluded.created_at_utc, full_text=excluded.full_text, permalink=excluded.permalink,
              has_outbound_link=excluded.has_outbound_link, impressions=excluded.impressions, likes=excluded.likes,
              engagements=excluded.engagements, bookmark=excluded.bookmark, share=excluded.share, follows=excluded.follows,
              replies=excluded.replies, retweets=excluded.retweets, profile_visits=excluded.profile_visits,
              detail_expands=excluded.detail_expands, url_clicks=excluded.url_clicks, hashtag_clicks=excluded.hashtag_clicks,
              permalink_clicks=excluded.permalink_clicks, fetched_at=excluded.fetched_at
            """,
            (
                row["rest_id"], created, row["full_text"], row["permalink"], int("https://t.co" in row["full_text"]),
                row["Impressions"], row["Likes"], row["Engagements"], row["Bookmark"], row["Share"], row["Follows"],
                row["Replies"], row["Retweets"], row["ProfileVisits"], row["DetailExpands"], row["UrlClicks"],
                row["HashtagClicks"], row["PermalinkClicks"], now,
            ),
        )
    conn.commit()


def db_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "db_path": str(path)}
    conn = open_db(path)
    try:
        n_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        date_range = conn.execute("SELECT MIN(created_at_utc), MAX(created_at_utc) FROM posts").fetchone()
        impressions = conn.execute("SELECT COALESCE(SUM(impressions), 0) FROM posts").fetchone()[0]
        return {"exists": True, "db_path": str(path), "posts": n_posts, "date_range": list(date_range), "total_impressions": impressions}
    finally:
        conn.close()
