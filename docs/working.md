# Working Notes

## Changelog

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
