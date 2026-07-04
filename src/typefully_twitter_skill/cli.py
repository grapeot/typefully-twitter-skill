"""Command-line interface for the Typefully Twitter skill."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings, load_dotenv
from .errors import ApiError, ConfigError, TypefullyTwitterError
from .typefully_metrics import METRIC_ENDPOINTS, TypefullyMetricsClient
from .typefully_post import TypefullyPostClient, compact_draft_summary, count_posts, parse_thread_file, parse_thread_text, validate_posts
from .url_validator import check_thread_file, check_post_urls
from .x_analytics import XAnalyticsClient, db_status, extract_posts, open_db, summarize_rows, upsert_posts, window_from_args, write_fetch_outputs


def emit(data: Any, *, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        if isinstance(data, dict):
            for key, value in data.items():
                print(f"{key}: {value}")
        else:
            print(data)


def _settings(args: argparse.Namespace) -> Settings:
    load_dotenv(getattr(args, "env_file", None))
    return Settings.from_env()


def _long_post_enabled(args: argparse.Namespace, settings: Settings) -> bool:
    if getattr(args, "long_post", None) is not None:
        return bool(args.long_post)
    return settings.default_long_post


def _posts_from_args(args: argparse.Namespace) -> list[str]:
    if getattr(args, "thread_file", None):
        return parse_thread_file(args.thread_file)
    if getattr(args, "thread_stdin", False):
        return parse_thread_text(sys.stdin.read())
    if getattr(args, "text", None):
        return [args.text.replace("\\n", "\n")]
    raise SystemExit("provide --text, --thread-file, or --thread-stdin")


def cmd_doctor_config(args: argparse.Namespace) -> int:
    settings = _settings(args)
    emit(settings.doctor_payload(), as_json=args.format == "json")
    return 0


def cmd_post_count(args: argparse.Namespace) -> int:
    settings = _settings(args)
    posts = _posts_from_args(args)
    emit({"posts": count_posts(posts, long_post=_long_post_enabled(args, settings))}, as_json=args.format == "json")
    return 0


def cmd_post_draft_or_create(args: argparse.Namespace) -> int:
    settings = _settings(args)
    posts = _posts_from_args(args)
    validate_posts(posts, long_post=_long_post_enabled(args, settings))
    client = TypefullyPostClient(settings)
    result = client.create_draft(posts, publish_at=getattr(args, "publish_at", None), draft_title=args.draft_title)
    emit(compact_draft_summary(result), as_json=args.format == "json")
    return 0


def cmd_post_publish(args: argparse.Namespace) -> int:
    client = TypefullyPostClient(_settings(args))
    emit(compact_draft_summary(client.update_draft(args.draft_id, publish_at="now")), as_json=args.format == "json")
    return 0


def cmd_post_schedule(args: argparse.Namespace) -> int:
    publish_at = "next-free-slot" if args.next_free_slot else args.at
    if not publish_at:
        raise SystemExit("provide --at or --next-free-slot")
    client = TypefullyPostClient(_settings(args))
    emit(compact_draft_summary(client.update_draft(args.draft_id, publish_at=publish_at)), as_json=args.format == "json")
    return 0


def cmd_post_list(args: argparse.Namespace) -> int:
    client = TypefullyPostClient(_settings(args))
    emit(client.list_drafts(status=args.status, limit=args.limit, offset=args.offset), as_json=args.format == "json")
    return 0


def cmd_post_get(args: argparse.Namespace) -> int:
    client = TypefullyPostClient(_settings(args))
    emit(client.get_draft(args.draft_id), as_json=args.format == "json")
    return 0


def cmd_post_delete(args: argparse.Namespace) -> int:
    if not args.confirm_delete:
        raise SystemExit("delete requires --confirm-delete")
    client = TypefullyPostClient(_settings(args))
    result = client.delete_draft(args.draft_id)
    emit({"deleted": True, "draft_id": args.draft_id, "result": result}, as_json=args.format == "json")
    return 0


def cmd_post_check_urls(args: argparse.Namespace) -> int:
    """Check a thread file or text for URL uniqueness (only yage.ai allowed)."""
    allowed_domain = getattr(args, "allowed_domain", "yage.ai")
    if getattr(args, "thread_file", None):
        results = check_thread_file(args.thread_file, allowed_domain=allowed_domain)
    elif getattr(args, "thread_stdin", False):
        text = sys.stdin.read()
        r = check_post_urls(text, allowed_domain=allowed_domain)
        results = [{"tweet_index": 1, **r.to_dict()}]
    elif getattr(args, "text", None):
        r = check_post_urls(args.text.replace("\\n", "\n"), allowed_domain=allowed_domain)
        results = [{"tweet_index": 1, **r.to_dict()}]
    else:
        raise SystemExit("provide --thread-file, --thread-stdin, or --text")

    emit({"results": results, "all_passed": all(r.get("passed", False) for r in results)},
         as_json=args.format == "json")

    # Return non-zero if any check failed, so CI/scripts can gate on it
    if not all(r.get("passed", False) for r in results):
        return 1
    return 0


def _default_dates(args: argparse.Namespace) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=14)
    return args.start_date or start.isoformat(), args.end_date or end.isoformat()


def cmd_metrics_accounts(args: argparse.Namespace) -> int:
    client = TypefullyMetricsClient(_settings(args))
    emit(client.accounts(), as_json=args.format == "json")
    return 0


def cmd_metrics_metric(args: argparse.Namespace) -> int:
    start, end = _default_dates(args)
    client = TypefullyMetricsClient(_settings(args))
    emit({"metric": args.name, "start_date": start, "end_date": end, "data": client.metric(args.name, start, end)}, as_json=args.format == "json")
    return 0


def cmd_metrics_snapshot(args: argparse.Namespace) -> int:
    start, end = _default_dates(args)
    client = TypefullyMetricsClient(_settings(args))
    data = client.snapshot(start, end)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        emit({"saved": str(path), "start_date": start, "end_date": end}, as_json=args.format == "json")
    else:
        emit(data, as_json=args.format == "json")
    return 0


def cmd_x_fetch(args: argparse.Namespace) -> int:
    settings = _settings(args)
    from_iso, to_iso = window_from_args(args.days, args.from_, args.to)
    client = XAnalyticsClient(settings)
    raw = client.fetch_posts(from_iso, to_iso)
    rows = extract_posts(raw)
    output_dir = Path(args.output_dir) if args.output_dir else settings.data_dir / "exports"
    paths = write_fetch_outputs(rows, raw, from_iso, to_iso, output_dir)
    emit({"from": from_iso, "to": to_iso, "posts": len(rows), **paths}, as_json=args.format == "json")
    return 0


def cmd_x_summary(args: argparse.Namespace) -> int:
    path = Path(args.input)
    doc = json.loads(path.read_text(encoding="utf-8"))
    emit(summarize_rows(doc.get("posts", []), doc.get("meta", {})), as_json=args.format == "json")
    return 0


def cmd_x_hourly(args: argparse.Namespace) -> int:
    from_iso, to_iso = window_from_args(None, args.from_, args.to)
    client = XAnalyticsClient(_settings(args))
    emit({"rest_id": args.rest_id, "series": client.fetch_hourly(args.rest_id, from_iso, to_iso, granularity=args.granularity)}, as_json=args.format == "json")
    return 0


def cmd_x_audience(args: argparse.Namespace) -> int:
    from_iso, to_iso = window_from_args(None, args.from_, args.to)
    from_ms = int(datetime.fromisoformat(from_iso[:10]).replace(tzinfo=timezone.utc).timestamp() * 1000)
    to_ms = int((datetime.fromisoformat(to_iso[:10]).replace(tzinfo=timezone.utc) + timedelta(days=1)).timestamp() * 1000) - 1
    client = XAnalyticsClient(_settings(args))
    emit(client.fetch_audience(args.rest_id, from_ms, to_ms), as_json=args.format == "json")
    return 0


def cmd_x_db_sync(args: argparse.Namespace) -> int:
    settings = _settings(args)
    from_iso, to_iso = window_from_args(args.days, args.from_, args.to)
    client = XAnalyticsClient(settings)
    raw = client.fetch_posts(from_iso, to_iso)
    rows = extract_posts(raw)
    db_path = Path(args.db) if args.db else settings.db_path
    conn = open_db(db_path)
    try:
        upsert_posts(conn, rows)
    finally:
        conn.close()
    emit({"db_path": str(db_path), "from": from_iso, "to": to_iso, "upserted_posts": len(rows)}, as_json=args.format == "json")
    return 0


def cmd_x_db_status(args: argparse.Namespace) -> int:
    settings = _settings(args)
    path = Path(args.db) if args.db else settings.db_path
    emit(db_status(path), as_json=args.format == "json")
    return 0


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env-file")
    parser.add_argument("--format", choices=["json", "text"], default="json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="typefully-twitter")
    add_common(parser)
    sub = parser.add_subparsers(dest="group", required=True)

    doctor = sub.add_parser("doctor")
    doctor_sub = doctor.add_subparsers(dest="cmd", required=True)
    config = doctor_sub.add_parser("config")
    config.set_defaults(func=cmd_doctor_config)

    post = sub.add_parser("post")
    post_sub = post.add_subparsers(dest="cmd", required=True)
    for name, func in [("count", cmd_post_count), ("draft", cmd_post_draft_or_create), ("create", cmd_post_draft_or_create)]:
        p = post_sub.add_parser(name)
        p.add_argument("--text")
        p.add_argument("--thread-file")
        p.add_argument("--thread-stdin", action="store_true")
        p.add_argument("--draft-title")
        long_post = p.add_mutually_exclusive_group()
        long_post.add_argument("--long-post", dest="long_post", action="store_true", default=None)
        long_post.add_argument("--no-long-post", dest="long_post", action="store_false")
        if name == "create":
            p.add_argument("--publish-at")
        p.set_defaults(func=func)
    p = post_sub.add_parser("publish")
    p.add_argument("draft_id")
    p.set_defaults(func=cmd_post_publish)
    p = post_sub.add_parser("schedule")
    p.add_argument("draft_id")
    p.add_argument("--at")
    p.add_argument("--next-free-slot", action="store_true")
    p.set_defaults(func=cmd_post_schedule)
    p = post_sub.add_parser("list")
    p.add_argument("--status")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--offset", type=int, default=0)
    p.set_defaults(func=cmd_post_list)
    p = post_sub.add_parser("get")
    p.add_argument("draft_id")
    p.set_defaults(func=cmd_post_get)
    p = post_sub.add_parser("delete")
    p.add_argument("draft_id")
    p.add_argument("--confirm-delete", action="store_true")
    p.set_defaults(func=cmd_post_delete)
    p = post_sub.add_parser("check-urls")
    p.add_argument("--text")
    p.add_argument("--thread-file")
    p.add_argument("--thread-stdin", action="store_true")
    p.add_argument("--allowed-domain", default="example.com")
    p.set_defaults(func=cmd_post_check_urls)

    metrics = sub.add_parser("metrics")
    metrics_sub = metrics.add_subparsers(dest="cmd", required=True)
    p = metrics_sub.add_parser("accounts")
    p.set_defaults(func=cmd_metrics_accounts)
    p = metrics_sub.add_parser("metric")
    p.add_argument("name", choices=sorted(METRIC_ENDPOINTS))
    p.add_argument("--start-date")
    p.add_argument("--end-date")
    p.set_defaults(func=cmd_metrics_metric)
    p = metrics_sub.add_parser("snapshot")
    p.add_argument("--start-date")
    p.add_argument("--end-date")
    p.add_argument("--output")
    p.set_defaults(func=cmd_metrics_snapshot)

    x = sub.add_parser("x")
    x_sub = x.add_subparsers(dest="cmd", required=True)
    p = x_sub.add_parser("fetch")
    p.add_argument("--days", type=int)
    p.add_argument("--from", dest="from_")
    p.add_argument("--to")
    p.add_argument("--output-dir")
    p.set_defaults(func=cmd_x_fetch)
    p = x_sub.add_parser("summary")
    p.add_argument("--input", required=True)
    p.set_defaults(func=cmd_x_summary)
    p = x_sub.add_parser("hourly")
    p.add_argument("--id", dest="rest_id", required=True)
    p.add_argument("--from", dest="from_", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--granularity", choices=["Hourly", "Daily"], default="Hourly")
    p.set_defaults(func=cmd_x_hourly)
    p = x_sub.add_parser("audience")
    p.add_argument("--id", dest="rest_id", required=True)
    p.add_argument("--from", dest="from_", required=True)
    p.add_argument("--to", required=True)
    p.set_defaults(func=cmd_x_audience)
    p = x_sub.add_parser("db-sync")
    p.add_argument("--db")
    p.add_argument("--days", type=int)
    p.add_argument("--from", dest="from_")
    p.add_argument("--to")
    p.set_defaults(func=cmd_x_db_sync)
    p = x_sub.add_parser("db-status")
    p.add_argument("--db")
    p.set_defaults(func=cmd_x_db_status)
    return parser


def _normalize_global_options(argv: list[str]) -> list[str]:
    """Allow --format/--env-file after subcommands while using argparse subparsers."""
    extracted: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(argv):
        item = argv[i]
        if item in {"--format", "--env-file"} and i + 1 < len(argv):
            extracted.extend([item, argv[i + 1]])
            i += 2
        elif item.startswith("--format=") or item.startswith("--env-file="):
            extracted.append(item)
            i += 1
        else:
            rest.append(item)
            i += 1
    return [*extracted, *rest]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    normalized = _normalize_global_options(list(argv) if argv is not None else sys.argv[1:])
    args = parser.parse_args(normalized)
    try:
        return args.func(args)
    except ConfigError as exc:
        settings = Settings.from_env()
        emit(exc.to_payload(settings.available_workflows()), as_json=getattr(args, "format", "json") == "json")
        return 2
    except ApiError as exc:
        emit(exc.to_payload(), as_json=getattr(args, "format", "json") == "json")
        return 1
    except TypefullyTwitterError as exc:
        emit({"error": "typefully_twitter_error", "message": str(exc)}, as_json=getattr(args, "format", "json") == "json")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
