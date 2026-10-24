# Typefully Twitter Skill — Agent Reference

## When To Use

Use this skill when the user asks an agent to work with X/Twitter through Typefully or analytics.x.com:

- Create, schedule, publish, list, inspect, or delete Typefully drafts for X.
- Upload images or a video clip and attach them to specific posts in a draft.
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
typefully-twitter post count --thread-file thread.md --long-post
typefully-twitter post draft --text "Post text" --draft-title "Internal title"
typefully-twitter post draft --thread-file thread.md
typefully-twitter post create --text "Post text" --publish-at "2026-01-01T18:00:00Z"
typefully-twitter post publish <draft_id>
typefully-twitter post schedule <draft_id> --at "2026-01-01T18:00:00Z"
typefully-twitter post list --status scheduled --limit 20 --format json
typefully-twitter post get <draft_id> --format json
typefully-twitter post delete <draft_id> --confirm-delete
typefully-twitter post check-urls --thread-file thread.md --allowed-domain example.com
typefully-twitter post check-urls --text "Post text https://example.com/post" --format json
typefully-twitter post check-urls --thread-file thread.md --allowed-domain example.com --allowed-domain example.org --include-subdomains --post-expected-urls 2=2
```

Acceptance criteria:

- Standard posts are checked with X weighted length rules, not visible character count.
- URLs count as transformed X URL length.
- `--thread-file` is treated as publishable post body, not as a Markdown document with metadata. The CLI preserves Markdown headings, labels, comments, and frontmatter as literal post text unless the implementation explicitly says otherwise.
- Before any live `post draft`, `post create`, `post publish`, or `post schedule`, inspect the exact outgoing `text` from `post count` or `post get`. The first visible line must be reader-facing copy. Reject files whose first line is an internal label such as `# Twitter copy`, `# Twitter 文案`, `Typefully long post`, `T 导流帖`, `R/T/N`, draft notes, agent instructions, or channel metadata.
- If a prepared copy file contains internal notes plus public copy, create a separate sanitized publish file or use `--text` / `--thread-stdin` with only the public copy. Do not assume Markdown headings or frontmatter will be stripped.
- Long-post behavior is account-dependent. During setup, ask whether the user's Typefully/X account can publish long posts. If yes, set `TYPEFULLY_TWITTER_DEFAULT_LONG_POST=true` in local `.env`; if no, leave it unset or false.
- If `TYPEFULLY_TWITTER_DEFAULT_LONG_POST=true`, `post count`, `post draft`, and `post create` use long-post validation by default. Use `--no-long-post` only when the user explicitly wants normal X length limits for a command.
- If the env default is disabled, use `--long-post` for substantive threads such as analytical articles, deep research summaries, and surveys. When `post count` returns `TOO_LONG` for inherently analytical writing, do not shorten the content to fit unless the user explicitly asks for a single-tweet summary. `post count` is a diagnostic tool; `TOO_LONG` often means the content belongs in long-post mode.
- For article distribution posts (e.g. from a content platform), default to Typefully long post. A "single Twitter post" means one Typefully post, not a 280-character normal X post. Do not impose the 280-character limit unless the user explicitly says "普通推文", "280 字内", "short tweet", or uses `--no-long-post`.
- Destructive actions require explicit confirmation flags.
- `post check-urls --allowed-domain` is repeatable. With `--include-subdomains`, `www.example.com` matches `example.com` but `badexample.com` does not. `--expected-urls N` sets how many URL-like tokens each post must hold (default 1); `--post-expected-urls N=COUNT` overrides it for one post, for example a reply that carries two links. Every token must be on an allowed domain.
- `post check-urls` validates that the post body contains exactly one URL-like token on the allowed domain. It catches both explicit URLs (`https://...`) and bare-domain tokens that Twitter's card preview may grab (e.g. `Character.AI`, `thereallo.dev`). The default allowed domain is `example.com`; override with `--allowed-domain`. Returns exit code 1 on failure, so it can be used as a pre-publish gate in CI or agent workflows. Run `post check-urls` on every `--thread-file` before `post draft` or `post create`.
- Machine-readable output is valid JSON when `--format json` is passed.

### Media (Images and Video)

Purpose: upload images or a video clip and attach them to posts in a draft.

Credential family: `TYPEFULLY_API_KEY` (same as publishing).

Target commands:

```bash
typefully-twitter media check clip.mp4
typefully-twitter media upload clip.mp4 --alt-text "Short description" --format json
typefully-twitter media status <media_id> --format json
typefully-twitter post draft --thread-file thread.md --media <media_id> --made-with-ai-post 1 --format json
typefully-twitter post draft --thread-file thread.md --media-file clip.mp4 --alt-text "Short description"
typefully-twitter post draft --thread-file thread.md --post-media 2=<media_id>
```

Acceptance criteria:

- Run `media check` before uploading. It is local only and rejects files outside Typefully's X limits: video MP4 or MOV, at most 512 MB, 10 minutes, 60 fps, 30 Mbps, aspect ratio 1:2.39 to 2.39:1; images 5 MB (20 MB with `TYPEFULLY_MEDIA_IMAGE_MAX_MB=20` on paid plans); GIFs 15 MB. Source: https://support.typefully.com/en/articles/8717768-supported-media-formats
- Videos longer than 10 minutes cannot go through Typefully, even on X Premium. Cut a clip and link to the full video, or ask the user to upload natively on x.com.
- `media upload` waits until the media status is `ready` and prints `media_id`; it never prints the presigned upload URL.
- `--media` and `--media-file` attach to post 1; `--post-media N=...` and `--post-media-file N=...` attach to post N (1-based). Before creating the draft, the CLI re-reads every media ID and refuses media that is not `ready`, two videos on one post, video mixed with images, or more than four images.
- `--made-with-ai-post N` sets Typefully's per-post `made_with_ai` label; `--made-with-ai` labels every post. Use it when the attached media is AI-generated, such as an AI avatar presenter.
- Uploading media and creating an unscheduled draft are remote writes but are not public. Scheduling and publishing follow the Safety Rules below.
- After creating a draft with media, run `post get <draft_id> --format json` and confirm `platforms.x.posts[i].media_ids` on the intended posts before scheduling. Typefully has no thumbnail parameter; X shows the first frame, so start clips on a frame that works as a cover.
- API reference: https://typefully.com/docs/api ; OpenAPI spec: https://api.typefully.com/v2/openapi.json

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
- `TYPEFULLY_TWITTER_DEFAULT_LONG_POST=true`: long-post validation is the default for local count, draft, and create commands.
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
