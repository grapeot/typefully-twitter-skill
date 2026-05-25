# Typefully Twitter Skill — Product Requirements

## What This Is

`typefully_twitter_skill` is a public, AI-first skill for working with X/Twitter through two practical surfaces: Typefully and the analytics.x.com web analytics endpoints.

The skill unifies three existing workflows into one agent-facing contract:

1. Publish or schedule X posts and threads through Typefully.
2. Read Typefully account-level growth metrics.
3. Read X per-post analytics, hourly curves, audience breakdowns, and local longitudinal data.

The first implementation provides the core package, CLI, offline tests, mocked tests, and read-only live tests. Posting write commands exist, but live tests deliberately avoid publishing, scheduling, or deleting posts.

## Users

The primary users are AI agents operating in a developer's local workspace. They need a stable, documented command surface for publishing and measuring social posts without re-discovering private APIs or writing ad hoc scripts each time.

Human operators are secondary users. They need one clear README, one `.env.example`, and a predictable CLI contract they can run or hand to an agent.

Maintainers are the third user type. They need a public-ready repo that separates reusable technical implementation from private workspace-specific strategy, aliases, handles, and report conventions.

## Jobs To Be Done

### Publish

An agent can create drafts, schedule posts, publish immediately when safe, list drafts, inspect existing drafts, delete drafts, and validate X weighted character counts before publishing.

Success means the agent can answer: "Can this post be published as a normal post, does it need long-post mode, or should it be split into a thread?" The answer must be based on X weighted length rules, not visible character count.

### Measure Account Momentum

An agent can fetch Typefully account-level metrics over a date window: impressions, followers, engagements, engagement rate, profile clicks, heatmap, and published tweet count.

Success means the agent can report platform-level trend lines without confusing account-level metrics with per-post metrics.

### Diagnose Post Performance

An agent can fetch per-post X analytics for a date window, summarize posts by impressions and URL clicks, fetch one post's hourly curve, fetch one post's audience breakdown, and sync longitudinal data into SQLite.

Success means the agent can distinguish reach posts from traffic-driving posts and can explain whether a post reached existing followers or out-of-network users.

## Non-Goals

- Generic X API v2 wrapper.
- Generic Typefully API passthrough.
- Automated liking, replying, following, DM handling, or engagement farming.
- Content-generation workflow for writing posts.
- Social media dashboard or web UI.
- Hosted service, webhook receiver, or background daemon.
- Private content strategy rules, account handles, campaign naming conventions, or workspace-specific aliases.

## Credential Families

The three credential families must stay separate because they authenticate different surfaces:

| Family | Purpose | Example variables |
|---|---|---|
| Typefully v2 API | Publishing and draft management | `TYPEFULLY_API_KEY`, `TYPEFULLY_SOCIAL_SET_ID` |
| Typefully web session | Account-level metrics | `TYPEFULLY_AUTHORIZATION`, `TYPEFULLY_ACCOUNT`, `TYPEFULLY_SESSION`, `TYPEFULLY_COOKIE` |
| X web cookies | analytics.x.com per-post analytics | `X_AUTH_TOKEN`, `X_CSRF_TOKEN`, `X_USER_ID` |

The CLI should expose diagnostics that clearly report which family is configured and which workflows are available.

## Availability Model

The product must support partial setup. A user may install the skill with only a Typefully API key, only X cookies, or no credentials yet. The agent-facing behavior should be capability-based rather than binary.

| Available credentials | Enabled workflows | Disabled workflows |
|---|---|---|
| none | docs, setup guidance, local-only validation | publishing, live metrics, live X analytics |
| Typefully v2 API only | publishing and draft management | X per-post analytics, optional Typefully web metrics |
| X cookies only | X per-post analytics and local sync | Typefully publishing, optional Typefully web metrics |
| Typefully web session only | optional account-level metrics | publishing, X per-post analytics |
| all families | full publish, metrics, and diagnostics workflows | none |

Missing credentials should produce a specific explanation and setup instruction. They should not produce a generic failure.

## Acceptance Criteria

The implementation phase is complete when:

- The public repo scaffold exists under `adhoc_jobs/typefully_twitter_skill/`.
- `README.md` explains the purpose, install model, CLI shape, configuration, and privacy posture.
- `skills/skill_typefully_twitter.md` defines one root skill that routes agents across publish, metrics, and analytics workflows.
- `docs/rfc.md` defines module boundaries, CLI contract, output contracts, local storage, and migration strategy.
- `docs/test.md` defines offline, mocked, live, and safety tests for the future implementation.
- No public file contains real API keys, cookies, private handles, private domains, private account IDs, or internal report paths beyond this local scaffold path.

- A package exposes a stable `typefully-twitter` CLI.
- Existing proven scripts have been migrated into library modules with tests.
- `doctor config` reports credential-family readiness in JSON.
- Missing optional credentials degrade gracefully with command-specific explanations.
- All publishing write operations require explicit user intent and support safe review paths.
- Live tests are opt-in and never publish, schedule, or delete real content unless separately allowed.
