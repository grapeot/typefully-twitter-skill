# Working Notes

## Changelog

### 2026-10-23

- Added media support: `media check|upload|status`, and `--media`, `--post-media`, `--media-file`, `--post-media-file`, `--alt-text`, `--made-with-ai`, `--made-with-ai-post` on `post draft|create`. The upload follows Typefully v2's presign, header-less `PUT`, and status-polling flow, and a draft is created only after every attached media ID reads back as `ready`.
- `post check-urls` now takes repeatable `--allowed-domain`, `--include-subdomains`, `--expected-urls`, and `--post-expected-urls`. For thread files, the combined check now expects the sum of the per-post counts instead of exactly one URL across the whole thread.
- `post draft|create` summaries now list `media_ids` and the AI label per post.
- Closed the deferred media-upload decision in the RFC.
- Lesson: Typefully caps X video at 10 minutes and 512 MB even for Premium accounts; long videos need a clip plus a link.

### 2026-06-06

- Added `TYPEFULLY_TWITTER_DEFAULT_LONG_POST` so Premium-capable workspaces can default local count/draft/create validation to long-post limits while preserving normal limits for other users.
- Added `--no-long-post` as an explicit per-command override when the env default is enabled.
- Updated setup instructions so installing agents ask whether the account can publish long posts and set the env default only when appropriate.

### 2026-05-25

- Created the public-ready design scaffold for `typefully_twitter_skill`.
- Added README, AGENTS, `.gitignore`, `.env.example`, PRD, RFC, test strategy, working notes, and root skill document.
- Deferred implementation code by design; this phase only defines the project and skill contract.
- Initialized this directory as an independent nested git repository.
- Ran an initial public-repo privacy scan and cleaned self-matching placeholder text from the docs and env example.
- Created the empty public GitHub repository at `https://github.com/grapeot/typefully-twitter-skill` without pushing local files.
- Confirmed the local git symbolic branch is `master`.
- Expanded README setup instructions around AI-assisted installation, Typefully API key setup, X browser cookie setup, and credential-based graceful degradation.
- Implemented the `typefully-twitter` Python package and CLI.
- Added offline unit tests, mocked client tests, SQLite tests, CLI tests, and opt-in read-only live tests.
- Configured local `.env` from existing private workspace values without printing secrets.
- Verified offline tests: 14 passed, 2 live tests skipped by default.
- Verified live tests with `TYPEFULLY_TWITTER_ENABLE_LIVE_TESTS=1`: Typefully API readonly and X analytics readonly tests both passed.

## Lessons Learned

- Keep public technical skill contracts separate from private workspace strategy. The public repo should explain how to publish, measure, and fetch analytics, while account-specific policy belongs in a private overlay.
- Typefully publishing credentials, Typefully metrics credentials, and X analytics cookies are three separate credential families. Mixing them is the most likely implementation error.
- Installation should assume the user gives the GitHub URL to a local agent. The README must tell the agent to inspect workspace guidance, install the root skill, and guide `.env` setup without asking the user to paste secrets into the chat.
- Missing optional analytics credentials should reduce available commands, not make the whole skill fail.
