# Typefully Twitter Skill — RFC

## Scope

This project should turn three working internal scripts into one public, library-first skill:

- Typefully publishing and draft management.
- Typefully private account metrics.
- X/Twitter per-post analytics through analytics.x.com GraphQL endpoints.

The project should preserve the practical behavior already proven by the internal tools while replacing scattered entry points with one coherent package, one CLI, one root skill, and one documentation contract.

## Design Principle

The skill should optimize for agent reliability. That means explicit credential-family diagnostics, JSON output for all machine workflows, stderr/stdout separation, idempotent local sync, and narrow command groups that map to real user jobs.

It should not optimize for API surface completeness. A small, stable command set is more useful to agents than a broad passthrough that requires the agent to understand Typefully and X internals on every run.

## Proposed Package Layout

```text
src/typefully_twitter_skill/
├── config.py            # env loading, paths, masked diagnostics
├── errors.py            # typed exceptions with raw HTTP details
├── typefully_post.py    # Typefully v2 draft/post client and weighted count helpers
├── typefully_metrics.py # Typefully web metrics client
├── x_analytics.py       # analytics.x.com GraphQL client
├── store.py             # SQLite schema for post, hourly, audience, fetch log
├── models.py            # dataclasses / typed result objects
├── cli.py               # argparse shell, output formatting, safety gates
└── __init__.py
```

The CLI should be a consumer of the library, not the implementation. Existing standalone scripts should be migrated into these modules rather than copied as independent command files.

## CLI Contract

The future executable name should be `typefully-twitter`.

### Diagnostics

```bash
typefully-twitter doctor config --format json
```

Reports which credential families are configured. Sensitive values must be masked. The command must not perform network calls by default.

Example shape:

```json
{
  "typefully_api": {"configured": true, "social_set_id": "123456"},
  "typefully_metrics": {"configured": true, "has_cookie": false},
  "x_analytics": {"configured": true, "has_user_id": true},
  "data": {"data_dir": "data", "db_path": "data/twitter_analytics.db"}
}
```

The diagnostic command is a capability map, not a global gate. If one credential family is missing, commands from other configured families should still work.

Suggested text-mode output:

```text
Typefully API: configured -> publishing enabled
X analytics cookies: missing -> x fetch/hourly/audience disabled; see README setup section
Typefully web metrics: missing -> metrics commands disabled; publishing is unaffected
```

### Publishing Commands

```bash
typefully-twitter post count --text "Post text https://example.com/post"
typefully-twitter post count --thread-file thread.md
typefully-twitter post draft --text "Post text" --draft-title "Internal title"
typefully-twitter post draft --thread-file thread.md
typefully-twitter post create --text "Post text" --publish-at "2026-01-01T18:00:00Z"
typefully-twitter post publish <draft_id>
typefully-twitter post schedule <draft_id> --at "2026-01-01T18:00:00Z"
typefully-twitter post list --status scheduled --limit 20 --format json
typefully-twitter post get <draft_id> --format json
typefully-twitter post delete <draft_id> --confirm-delete
typefully-twitter post draft --thread-file thread.md --media <media_id> --made-with-ai-post 1
typefully-twitter post check-urls --thread-file thread.md --allowed-domain example.com --allowed-domain example.org --include-subdomains --post-expected-urls 2=2
```

Publishing commands use the Typefully v2 API credential family. They must validate weighted length before draft creation unless `--long-post` is explicitly passed. Deletion must require `--confirm-delete`.

### Media Commands

```bash
typefully-twitter media check <path>
typefully-twitter media upload <path> [--alt-text TEXT] [--no-wait] [--timeout 600] [--interval 3]
typefully-twitter media status <media_id>
```

`post draft` and `post create` accept `--media MEDIA_ID` (post 1), `--post-media N=MEDIA_ID`, `--media-file PATH` (post 1), `--post-media-file N=PATH`, `--alt-text` (for uploaded files), `--made-with-ai` (every post), and `--made-with-ai-post N`. All flags are repeatable except `--alt-text` and `--made-with-ai`.

Flow, following the Typefully v2 API: `POST /v2/social-sets/{id}/media/upload` with `file_name` (must match `^[a-zA-Z0-9_.()-]+\.(jpg|jpeg|png|webp|gif|mp4|mov|pdf)$`, so local names are sanitized) returns `media_id` and a presigned `upload_url`; the client `PUT`s the raw bytes to that URL; `GET /v2/social-sets/{id}/media/{media_id}` is polled until `status` is `ready` (or `failed`, with `error_reason`). Draft posts then carry `media_ids` and optionally `made_with_ai: true` in `platforms.x.posts[i]`. Scheduling is unchanged.

Invariants:

1. A draft never references media whose status is not `ready`; the CLI re-reads every media ID before creating the draft.
2. The presigned `PUT` sends no `Authorization` or `Content-Type` header (the signature was computed without them), and the upload URL never appears in output or error messages: network errors report only the exception type, and storage error bodies are reduced to their `Code` and `Message`.
3. Each X post holds at most one video or GIF, does not mix video with images, and holds at most four images. Media kind comes from the MIME type, falling back to the file name; an undeterminable kind is an error. This is checked before any upload starts.
4. Local files that break Typefully's X limits fail in `media check` before any network request.
5. Uploading media and creating a draft are remote writes that are not publicly visible; scheduling and publishing keep the existing safety rules.
6. Without media flags, draft payloads are byte-for-byte what they were before media support.

### URL Checks

`post check-urls` accepts repeatable `--allowed-domain`, `--include-subdomains` (for explicit http(s) URLs, a host matches when it equals an allowed domain or ends with `.` plus it; bare-domain tokens are matched exactly), `--expected-urls N` (default 1, per post), and `--post-expected-urls N=COUNT`. Every URL-like token must be on an allowed domain, and each post must hold exactly its expected count; the combined thread check expects the sum.

### Typefully Metrics Commands

```bash
typefully-twitter metrics accounts --format json
typefully-twitter metrics metric impressions --start-date 2026-01-01 --end-date 2026-01-14 --format json
typefully-twitter metrics snapshot --start-date 2026-01-01 --end-date 2026-01-14 --output data/typefully_snapshot.json
```

Metrics commands use the Typefully web-session credential family. They return account-level time series. The CLI and skill must explicitly warn agents not to interpret these as per-post analytics.

### X Analytics Commands

```bash
typefully-twitter x fetch --days 28 --output-dir data/exports
typefully-twitter x summary --input data/exports/twitter_per_post_20260101_20260114.json
typefully-twitter x hourly --id 1234567890123456789 --from 2026-01-01 --to 2026-01-03 --format json
typefully-twitter x audience --id 1234567890123456789 --from 2026-01-01 --to 2026-01-03 --format json
typefully-twitter x db-sync --days 45 --db data/twitter_analytics.db
typefully-twitter x db-status --db data/twitter_analytics.db
```

X analytics commands use browser cookies from the analytics.x.com surface. They should preserve raw JSON exports and write CSV only as a convenience artifact. SQLite is the long-term query layer.

## Output Rules

- `--format json` writes valid JSON to stdout and progress to stderr.
- HTTP errors must include status code and response body where safe.
- Write operations should print the external object ID, status, scheduled time, and URL if available.
- Analytics exports should include metadata: query window, fetch timestamp, post count, and command version.

## Graceful Failure Rules

Each command group should check only the credentials it needs.

- `post *` requires Typefully v2 API credentials. If missing, return a setup-focused error that points to `Settings -> API` in Typefully.
- `metrics *` requires Typefully web metrics credentials if the optional metrics module is implemented. If missing, say that Typefully account-level metrics are not configured and do not imply publishing is unavailable.
- `x *` requires X browser cookies. If missing, say that per-post analytics are unavailable and point to the README cookie setup section.
- Local commands such as `doctor config`, `post count`, and future local summaries should not require network credentials.

Error payloads in JSON mode should include `capability`, `missing_env`, `available_workflows`, and `setup_hint` fields.

Example:

```json
{
  "error": "x_analytics_not_configured",
  "capability": "x_analytics",
  "missing_env": ["X_AUTH_TOKEN", "X_CSRF_TOKEN"],
  "available_workflows": ["post.count", "post.draft", "post.schedule"],
  "setup_hint": "Configure X browser cookies in .env; see README: Get X Cookies for Advanced Analytics."
}
```

## Local Storage

The future implementation should use `data/` by default and keep it out of git.

```text
data/
├── exports/                    # raw JSON + CSV fetch outputs
├── twitter_analytics.db         # SQLite longitudinal database
└── logs/                         # optional local operation logs
```

SQLite should contain four tables:

- `posts`: one row per X post, including `rest_id`, `created_at_utc`, text, permalink, outbound-link flag, and cumulative metrics.
- `hourly_metrics`: one row per `(rest_id, ts)`, storing post-level hourly metric values.
- `audience_snapshots`: one row per audience dimension row, preserving fetch time and dimension values.
- `fetch_log`: one row per fetch/sync operation, including status and error text.

## Migration Plan

The existing internal tools provide the implementation source material:

- `tools/typefully_post.py` -> `typefully_post.py` module and `post` command group.
- `tools/typefully_metrics.py` -> `typefully_metrics.py` module and `metrics` command group.
- `tools/twitter_analytics.py` -> `x_analytics.py`, `store.py`, and `x` command group.

Migration should happen in small phases:

1. Port pure logic first: env loading, weighted count, thread parsing, output shaping, SQLite schema.
2. Add HTTP clients with mocked tests.
3. Add CLI wrappers around library calls.
4. Add opt-in live tests.
5. Replace workspace-specific private skills with one private overlay that points to this public root skill.

## Public / Private Split

The public repo contains the technical skill contract and fake examples. Workspace-specific overlays should live outside this repo and may define private defaults such as account IDs, preferred campaign naming, content-language rules, URL tracking conventions, or private report locations.

The public root skill should be installable on its own. Private overlays may add policy, but the public skill must remain useful without them.

## Resolved Decisions

- Media upload is supported (see Media Commands). Videos longer than Typefully's 10-minute limit stay out of scope; they can only be uploaded natively on x.com.

## Deferred Decisions

- Whether to include a built-in report generator or keep reporting outside the package.
- Whether to expose SQL helper commands beyond `db-status`.
- Whether to provide shell wrappers in `scripts/` after the Python console script exists.
