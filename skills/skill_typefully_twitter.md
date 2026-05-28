# Typefully Twitter Skill — Agent Reference

## When To Use

Use this skill when the user asks an agent to work with X/Twitter through Typefully or analytics.x.com:

- Create, schedule, publish, list, inspect, or delete Typefully drafts for X.
- Validate tweet or thread length before publishing.
- Fetch Typefully account-level metrics such as impressions, followers, engagements, or engagement rate.
- Fetch X per-post analytics, hourly performance curves, audience breakdowns, or local analytics database status.
- Diagnose whether a post is a reach post, traffic driver, or follower-base post.

This skill is a root router. It combines three capabilities that are often separate in a private workspace: Typefully publishing, Typefully metrics, and X per-post analytics.

## Current Status

This repository contains a working `typefully-twitter` CLI plus the root skill contract. Use the CLI from the repository virtual environment after installation:

```bash
.venv/bin/typefully-twitter doctor config --format json
```

## Capability Families

### Typefully Publishing

Purpose: create drafts, schedule posts, publish posts, inspect drafts, and validate X length.

Credential family: `TYPEFULLY_API_KEY`, optional `TYPEFULLY_SOCIAL_SET_ID`.

Target commands:

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
```

Acceptance criteria:

- Standard posts are checked with X weighted length rules, not visible character count.
- URLs count as transformed X URL length.
- Long posts require explicit `--long-post`.
- Destructive actions require explicit confirmation flags.
- Machine-readable output is valid JSON when `--format json` is passed.

### Typefully Metrics

Purpose: fetch account-level growth metrics from Typefully's web metrics endpoints.

Credential family: `TYPEFULLY_AUTHORIZATION`, `TYPEFULLY_ACCOUNT`, `TYPEFULLY_SESSION`, optional `TYPEFULLY_COOKIE`.

Target commands:

```bash
typefully-twitter metrics accounts --format json
typefully-twitter metrics metric impressions --start-date 2026-01-01 --end-date 2026-01-14 --format json
typefully-twitter metrics metric followers --start-date 2026-01-01 --end-date 2026-01-14 --format json
typefully-twitter metrics snapshot --start-date 2026-01-01 --end-date 2026-01-14 --output data/typefully_snapshot.json
```

Supported metric names:

- `published_tweets`
- `impressions`
- `profile_clicks`
- `followers`
- `engagements`
- `engagement_rate`
- `engagement_heatmap`

Acceptance criteria:

- Agents must describe these as account-level metrics.
- Agents must not use these as per-post analytics.
- Snapshot output includes the requested date window and all metric payloads.

### X Per-Post Analytics

Purpose: fetch post-level analytics through analytics.x.com GraphQL endpoints and store longitudinal data locally.

Credential family: `X_AUTH_TOKEN`, `X_CSRF_TOKEN`, optional `X_USER_ID`.

Target commands:

```bash
typefully-twitter x fetch --days 28 --output-dir data/exports
typefully-twitter x summary --input data/exports/twitter_per_post_20260101_20260114.json
typefully-twitter x hourly --id 1234567890123456789 --from 2026-01-01 --to 2026-01-03 --format json
typefully-twitter x audience --id 1234567890123456789 --from 2026-01-01 --to 2026-01-03 --format json
typefully-twitter x db-sync --days 45 --db data/twitter_analytics.db
typefully-twitter x db-status --db data/twitter_analytics.db
```

Acceptance criteria:

- `fetch` writes raw JSON and a derived CSV artifact.
- `summary` reports totals, rates, top posts by impressions, and top posts by URL clicks.
- `hourly` returns a post-level time series.
- `audience` reports country, age/gender, and in-network vs out-of-network distribution when available.
- `db-sync` is idempotent and safe to rerun.

## Diagnostics

Before using any live workflow, run:

```bash
typefully-twitter doctor config --format json
```

Credential values may be literal strings or 1Password secret references beginning with `op://`. Public documentation must use fake references such as `op://your-vault/your-item/your-field`; keep real vault, item, cookie, and account details in private workspace `.env` files.

The diagnostic should report readiness for each credential family separately. If one family is missing, use the other configured families rather than failing the whole skill.

## Credential-Based Routing

Treat setup as layered:

- No credentials: provide installation/setup guidance and run local-only checks when implementation supports them.
- `TYPEFULLY_API_KEY` configured: publishing and draft management are available.
- `X_AUTH_TOKEN` and `X_CSRF_TOKEN` configured: X per-post analytics are available.
- `TYPEFULLY_AUTHORIZATION`, `TYPEFULLY_ACCOUNT`, and `TYPEFULLY_SESSION` configured: optional Typefully account-level metrics are available.

When a requested capability is unavailable, explain exactly which credential family is missing and what still works. Do not report the whole skill as broken.

Examples:

- Missing X cookies: "Per-post X analytics are not configured yet. I can still create and manage Typefully drafts because your Typefully API key is configured. To enable analytics, add the two X browser cookie values to `.env`."
- Missing Typefully API key: "Publishing is not configured yet. I can still read existing local analytics exports or use X analytics if cookies are configured. To enable publishing, create a Typefully API key from Typefully Settings -> API and add it to `.env`."
- Missing optional Typefully metrics session: "Typefully account-level metrics are not configured. This does not affect publishing or X per-post analytics."

## Safety Rules

- Do not publish, schedule, delete, or otherwise mutate external state unless the user's current message explicitly asks for that action.
- Prefer draft creation or dry-run/count validation when the user asks for review, wording, or analysis.
- Never invent analytics results. Every metric claim must come from command output, local SQLite, or a cited exported artifact.
- Keep private account policy outside this public skill. This root skill should stay technical and reusable.

## Public / Private Overlay

Public repo content should stay generic. Private workspaces may add a separate overlay skill for account-specific policy, such as preferred language, UTM conventions, campaign naming, known account IDs, or private report paths.

The public root skill remains the canonical technical contract. A private overlay should point to this file rather than duplicating the command contract.
