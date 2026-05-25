from __future__ import annotations

from pathlib import Path

from typefully_twitter_skill.x_analytics import db_status, extract_posts, open_db, summarize_rows, upsert_posts, window_from_args


RAW = {
    "data": {
        "viewer_v2": {
            "user_results": {
                "result": {
                    "tweets_results": [
                        {
                            "result": {
                                "__typename": "Tweet",
                                "rest_id": "1",
                                "legacy": {"created_at": "Fri Apr 17 14:44:03 +0000 2026", "full_text": "hello https://t.co/x"},
                                "organic_metrics_total": [
                                    {"metric_type": "Impressions", "metric_value": 100},
                                    {"metric_type": "Engagements", "metric_value": 10},
                                    {"metric_type": "UrlClicks", "metric_value": 5},
                                ],
                            }
                        }
                    ]
                }
            }
        }
    }
}


def test_extract_and_summarize_posts():
    rows = extract_posts(RAW)
    summary = summarize_rows(rows)
    assert rows[0]["rest_id"] == "1"
    assert summary["totals"]["impressions"] == 100
    assert summary["with_outbound_link"]["n"] == 1


def test_db_upsert_and_status(tmp_path: Path):
    db = tmp_path / "twitter.db"
    rows = extract_posts(RAW)
    conn = open_db(db)
    try:
        upsert_posts(conn, rows)
        upsert_posts(conn, rows)
    finally:
        conn.close()
    status = db_status(db)
    assert status["posts"] == 1
    assert status["total_impressions"] == 100


def test_window_from_args_explicit_dates():
    assert window_from_args(start="2026-01-01", end="2026-01-02") == ("2026-01-01T00:00:00.000Z", "2026-01-02T23:59:59.999Z")
