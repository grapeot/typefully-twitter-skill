# Typefully Twitter Skill

An AI-first CLI and skill for publishing to X through Typefully, reading Typefully account-level growth metrics, and reading X per-post analytics through the analytics.x.com web endpoints.

This repository provides a plain Markdown agent skill plus a Python package and CLI. It is built for local coding agents that can read workspace instructions, edit `.env`, run commands, and report results without exposing secrets in chat.

This is not a social media dashboard. It is not a general X API wrapper. It is a narrow agent-facing interface for three workflows that agents repeatedly need: publish, measure, and diagnose.

GitHub repository: `https://github.com/grapeot/typefully-twitter-skill`

## What It Will Do

- Create, schedule, publish, list, inspect, and delete Typefully drafts for X.
- Validate X weighted character counts before publishing, including URL handling and long-post mode.
- Upload images and videos to Typefully, wait until processing finishes, and attach them to specific posts in a draft, with an optional per-post "made with AI" label.
- Check post copy so each post carries exactly the expected number of links, all on domains you allow.
- Fetch Typefully account-level metrics such as impressions, followers, engagements, engagement rate, and profile clicks.
- Fetch X per-post analytics, including cumulative post metrics, hourly curves, audience breakdowns, and local SQLite sync.
- Provide one root Markdown skill contract that routes agents to the correct command family.

## Repository Status

The current version contains a working CLI plus design docs:

```text
docs/prd.md                 Product scope and success criteria
docs/rfc.md                 Architecture and CLI design
docs/test.md                Test and validation strategy
docs/working.md             Changelog and lessons learned
skills/skill_typefully_twitter.md  Canonical agent skill contract
src/typefully_twitter_skill/        Python package and CLI implementation
tests/                             Offline tests plus opt-in read-only live tests
```

## Install the Agent Skill

This project uses a plain Markdown skill contract, not a vendor-specific packaged skill format.

The intended installation path is AI-assisted: give the GitHub URL to your local coding agent and let it install the skill into your workspace.

Use a prompt like this:

```text
Please install this Typefully Twitter skill into my workspace:

https://github.com/grapeot/typefully-twitter-skill

Read the repository README first. Then inspect my workspace's AGENTS.md, CLAUDE.md, or skill index, add the root skill to the right discovery location, create a local .env from .env.example, and guide me through filling the required credentials. Ask whether my Typefully/X account can publish long posts; if yes, set TYPEFULLY_TWITTER_DEFAULT_LONG_POST=true in local .env. Do not paste secrets into the chat; ask me to put them into .env locally.
```

That is the normal path for Codex, Claude Code, Cursor, OpenCode, and similar local agents. The skill is written for agents that can read Markdown instructions and edit files in your local workspace.

Manual installation is still possible:

1. Clone this repository into a stable location such as `adhoc_jobs/typefully_twitter_skill/`.
2. Put `skills/skill_typefully_twitter.md` somewhere your agent can discover, or point your workspace-level skill index to this file.
3. Start from the target workspace's `AGENTS.md`, `CLAUDE.md`, or equivalent root guidance file.
4. If the workspace has `rules/skills/INDEX.md` or `skills/INDEX.md`, add one entry for this root skill. If no index exists, add a short pointer to the root guidance file.

Example workspace guidance:

```text
For Typefully publishing, Typefully metrics, or X/Twitter per-post analytics, read adhoc_jobs/typefully_twitter_skill/skills/skill_typefully_twitter.md and follow its CLI contract.
```

Expose only this root skill at the workspace level. Do not globally register separate publish, metrics, and analytics skills; the root skill handles routing.

## Media (Images and Video)

Typefully's API uploads media in three steps: ask for a presigned upload URL, `PUT` the raw file bytes to it with no extra headers, then poll the media status until it is `ready`. The CLI wraps this:

```bash
typefully-twitter media check clip.mp4                 # local only: format, size, duration, fps, bitrate, aspect
typefully-twitter media upload clip.mp4 --alt-text "Short description" --format json
typefully-twitter media status <media_id> --format json
typefully-twitter post draft --thread-file thread.md --media <media_id> --made-with-ai-post 1
typefully-twitter post draft --thread-file thread.md --media-file clip.mp4      # check, upload, wait, attach
typefully-twitter post draft --thread-file thread.md --post-media 2=<media_id>  # attach to post 2
```

Limits for X through Typefully (from Typefully's [Supported Media Formats](https://support.typefully.com/en/articles/8717768-supported-media-formats)): video MP4 or MOV, at most 512 MB and 10 minutes, at most 60 fps and 30 Mbps, aspect ratio between 1:2.39 and 2.39:1; images 5 MB on free plans and 20 MB on paid plans (set `TYPEFULLY_MEDIA_IMAGE_MAX_MB=20`); GIFs 15 MB. One X post holds one video or GIF, or up to four images. X Premium allows much longer videos, but only when uploaded natively on x.com; for long videos, cut a clip and link to the full version. Files that break these limits are rejected locally before any request is sent, and the per-post mix (one video, or up to four images) is checked before any upload starts. `media check` uses `ffprobe` when it is installed; without it, duration, frame rate, bitrate, and aspect ratio are not checked. `--alt-text` applies to every file uploaded in that command, not to `--media` IDs.

The API reference is at `https://typefully.com/docs/api` and the OpenAPI spec at `https://api.typefully.com/v2/openapi.json`.

## Setup Credentials

The CLI accepts either literal values or 1Password secret references for credential values. Public examples use placeholder references such as `op://your-vault/your-item/your-field`; keep real vault and item names in your private workspace `.env`, not in this public repository.

The skill should work in layers. You do not need every credential on day one.

| Setup level | Credentials | What works |
|---|---|---|
| No credentials | none | Local docs, command help, length counting once implemented |
| Basic Typefully | `TYPEFULLY_API_KEY` | Create drafts, schedule, publish, list, inspect, and delete Typefully drafts |
| Advanced X analytics | `X_AUTH_TOKEN`, `X_CSRF_TOKEN` | Fetch X per-post analytics, hourly curves, audience breakdowns, and local SQLite sync |
| Optional Typefully web metrics | `TYPEFULLY_AUTHORIZATION`, `TYPEFULLY_ACCOUNT`, `TYPEFULLY_SESSION` | Fetch Typefully account-level web metrics if this optional module is implemented |

The first implementation should treat missing optional credentials as reduced capability, not as global failure. `doctor config` should explain what is available and what is skipped.

### 1. Get a Typefully API Key

Use this for publishing and draft management.

1. Create or log in to a Typefully account at `https://typefully.com`.
2. Connect your X account inside Typefully. Typefully uses social sets to represent connected accounts.
3. Open Typefully settings and go to `Settings -> API`, or visit `https://typefully.com/?settings=api`.
4. Click `Create new API key`.
5. Copy the key into your local `.env`:

```bash
TYPEFULLY_API_KEY=op://your-vault/your-item/typefully-api-key
```

Do not paste the real key into a remote chat. If your AI agent runs locally, ask it to open or edit `.env` and then paste the key into that local file yourself.

The future CLI should be able to discover your social set ID by calling the Typefully API. If auto-discovery is not implemented yet, set it manually:

```bash
TYPEFULLY_SOCIAL_SET_ID=123456
```

Typefully API v2 uses the `Authorization: Bearer <key>` header. Old v1 keys and old `x-api-key` examples are not interchangeable with v2.

### Long-Post Default

Long posts require a Typefully/X account that can publish long-form posts, usually via a Premium-capable account. The CLI keeps the public default conservative: without configuration, `post count`, `post draft`, and `post create` validate against normal X weighted length limits.

During setup, the installing agent should ask whether the user can publish long posts. If the answer is yes, set this in the local `.env`:

```bash
TYPEFULLY_TWITTER_DEFAULT_LONG_POST=true
```

This makes long-post validation the default for that workspace, so agents do not have to remember `--long-post` every time. Callers can still override it per command with `--no-long-post`; users without long-post support should leave the variable unset or set it to `false`.

### 2. Get X Cookies for Advanced Analytics

Use this only if you want per-post X analytics. Publishing through Typefully does not require these cookies.

The analytics module reads the same browser session that analytics.x.com uses. You need two cookie values from a browser where you are already logged into X:

```bash
X_AUTH_TOKEN=op://your-vault/your-item/x-auth-token
X_CSRF_TOKEN=op://your-vault/your-item/x-csrf-token
```

Manual Chrome path:

1. Open `https://x.com` and confirm you are logged in.
2. Open Chrome DevTools.
3. Go to `Application -> Storage -> Cookies -> https://x.com`.
4. Copy the value for the X session cookie into `X_AUTH_TOKEN`.
5. Copy the value for the X CSRF cookie into `X_CSRF_TOKEN`.
6. Save `.env` and run the future diagnostic command:

```bash
typefully-twitter doctor config --format json
```

Manual Firefox path:

1. Open `https://x.com` and confirm you are logged in.
2. Open Developer Tools.
3. Go to `Storage -> Cookies -> https://x.com`.
4. Copy the same two cookie values into `.env`.

AI-assisted path:

```text
Please help me configure X analytics cookies for this skill. Use browser automation if your environment supports it. If you cannot safely read browser cookies directly, guide me to DevTools -> Application/Storage -> Cookies for x.com and tell me exactly which two values to paste into my local .env. Do not ask me to paste cookie values into the chat transcript.
```

Cookies are equivalent to a logged-in browser session. Keep them local, do not commit them, and refresh them if `doctor config` or an analytics command reports that the X session is no longer valid.

### 3. Optional Typefully Web Metrics

The current design includes an optional Typefully web metrics family for account-level time series such as followers and engagement rate. This is separate from the official Typefully API key. Configure it only if the implemented version still needs private Typefully web metrics:

```bash
TYPEFULLY_AUTHORIZATION=op://your-vault/your-item/typefully-authorization
TYPEFULLY_ACCOUNT=op://your-vault/your-item/typefully-account
TYPEFULLY_SESSION=op://your-vault/your-item/typefully-session
```

If these are missing, the skill should still publish through Typefully and fetch X per-post analytics when the relevant credentials are present.

## Graceful Degradation

The skill should never fail the whole tool just because one credential family is missing.

Expected behavior:

- If `TYPEFULLY_API_KEY` is missing, publishing commands are unavailable. The agent can still explain setup, validate local files, and use X analytics if X cookies are configured.
- If X cookies are missing, `x fetch`, `x hourly`, `x audience`, and `x db-sync` are unavailable. The agent can still create and manage Typefully drafts.
- If optional Typefully web metrics credentials are missing, `metrics` commands are unavailable. The agent should say account-level Typefully metrics are not configured rather than guessing.
- If only local artifacts exist, the agent may summarize existing exports or SQLite data without making network calls.

The future diagnostic command should make this explicit:

```bash
typefully-twitter doctor config --format json
```

It should return a capability map instead of a single pass/fail result.

## Future Install for Developers

From this repository root:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e '.[dev]'
```

The CLI exposes:

```bash
typefully-twitter doctor config --format json
typefully-twitter post count --text "Draft text https://example.com/post"
typefully-twitter post count --text "Long-form draft text" --long-post
typefully-twitter post count --text "Normal post text" --no-long-post
typefully-twitter post draft --text "Draft text"
typefully-twitter metrics snapshot --start-date 2026-01-01 --end-date 2026-01-14
typefully-twitter x fetch --days 28
typefully-twitter x db-status
```

Run offline tests:

```bash
.venv/bin/python -m pytest -v
```

Run read-only live tests only after `.env` is configured:

```bash
TYPEFULLY_TWITTER_ENABLE_LIVE_TESTS=1 .venv/bin/python -m pytest -v -m live_integration
```

The live tests validate Typefully API connectivity and X analytics fetch. They do not publish, schedule, or delete posts.

## Configure

Copy `.env.example` to `.env`. All examples use fake values and are safe for a public repository.

The future configuration has three credential families:

- `TYPEFULLY_API_KEY`: Typefully v2 API token for publishing and draft management.
- `TYPEFULLY_TWITTER_DEFAULT_LONG_POST`: optional boolean; set to `true` only when the account can publish long posts.
- `TYPEFULLY_AUTHORIZATION`, `TYPEFULLY_ACCOUNT`, `TYPEFULLY_SESSION`, optional `TYPEFULLY_COOKIE`: Typefully web-session credentials for account-level metrics.
- `X_AUTH_TOKEN`, `X_CSRF_TOKEN`, optional `X_USER_ID`: x.com cookies for analytics.x.com GraphQL endpoints.

These credentials are intentionally separate. Do not reuse one family for another.

## Privacy

This repository is designed to be publishable with only fake examples.

Do not commit `.env`, API keys, browser cookies, X auth tokens, Typefully session headers, private handles, local analytics databases, raw exports, generated reports, or logs. Public docs must use fake domains, fake handles, fake account IDs, and fake 1Password references.
