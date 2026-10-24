# Typefully Twitter Skill — Test Strategy

## Current Phase

The CLI is implemented. Offline tests run with `pytest`; live tests are opt-in. Media coverage lives in `tests/test_typefully_media.py` and multi-domain URL checks in `tests/test_url_validator.py`:

- Local media checks: filename sanitizing, ffprobe parsing, the 10-minute / fps / bitrate / aspect limits, unsupported or missing files, and the no-ffprobe warning.
- Payloads: no-media drafts are unchanged; media IDs and the AI label land on the right post; out-of-range indexes are rejected.
- Client flow (mocked `requests`): the upload request body, a presigned `PUT` without headers, polling from `processing` to `ready`, `failed` with its reason, timeouts, and redaction of the upload URL in errors.
- CLI: drafts re-check that media is ready, reject two videos on one post, reject bad indexes, and fail local file checks before any request.
- URL checks: several allowed domains, subdomain matching (a lookalike such as `badexample.com` must not match `example.com`), expected counts per post, and the combined thread count.

The original design-phase checks still apply to the docs:

- Required design files exist.
- Public docs contain fake credentials and fake examples only.
- The root skill routes the three capability families clearly.
- The RFC defines a future CLI contract specific enough to implement.

## Future Offline Tests

Offline tests should be the default test suite and must not require network access or credentials.

They should cover:

- `.env` loading and masked `doctor config` output.
- X weighted character counting, including CJK characters, URLs, and long-post limits.
- Env-controlled default long-post mode, including explicit `--no-long-post` override.
- Thread parsing from `---` separators.
- CLI argument parsing for each command group.
- JSON output shaping.
- SQLite schema creation, upsert behavior, idempotent sync behavior, and `db-status` aggregation.
- Error formatting with HTTP status and response body.

## Future Mocked Integration Tests

Mocked integration tests should simulate HTTP responses from Typefully and x.com without touching live services.

They should cover:

- Typefully draft creation, scheduling, list, get, publish, and delete responses.
- Typefully metric endpoint responses for every supported metric name.
- X `fetch`, `hourly`, and `audience` response shapes.
- Rate limit handling for X analytics, including retry/backoff behavior.
- Malformed response handling that preserves enough detail for an agent to debug.

## Future Live Tests

Live tests must be opt-in and disabled by default.

Suggested gates:

```bash
TYPEFULLY_TWITTER_ENABLE_LIVE_TESTS=1
TYPEFULLY_TWITTER_LIVE_ALLOW_WRITE=1
TYPEFULLY_TWITTER_LIVE_ALLOW_DELETE=1
```

Read-only live tests may call diagnostics, Typefully account endpoints, Typefully metrics, X fetch for a tiny window, and X `db-status` on a temporary database.

Write live tests must require an additional allow flag. Draft creation should use clearly fake text and must clean up only drafts it created in the same test run. Immediate publish should not be part of the default live suite.

## Manual QA

Before declaring the implementation ready, a maintainer or agent should manually verify:

- `doctor config --format json` reports all credential families correctly.
- `post count` matches known X weighted-length examples.
- `post draft` creates a draft in Typefully and does not publish it.
- `metrics snapshot` returns a date-windowed payload.
- `x fetch --days 1` writes JSON and CSV to a temporary output directory.
- `x db-sync --days 1 --skip-hourly --skip-audience` writes a temporary SQLite database.

## Privacy Checks

Run a repository privacy scan before publishing. The scan should look for browser cookie names and values, bearer-token looking strings, real Typefully API key prefixes, private handles, private domains, private absolute home paths, and non-placeholder 1Password references.

```bash
rg -n "<project-specific-private-patterns>" .
```

Any match should be reviewed. Public files should use fake domains, fake handles, fake account IDs, and fake 1Password paths.
