# Typefully Twitter Skill

## Project Role

This repository designs an AI-first skill for Typefully publishing, Typefully account-level metrics, and X/Twitter per-post analytics. The CLI is implemented; keep the docs, tests, and skill contract aligned when the command contract changes.

The repository is intended to become a public GitHub repo. Keep all examples fake and publishable.

## Project Structure

- `README.md`: public installation and usage overview.
- `.env.example`: fake credential template for future implementation.
- `docs/prd.md`: product scope, user stories, success criteria, and non-goals.
- `docs/rfc.md`: architecture, module boundaries, CLI design, data model, and migration plan.
- `docs/test.md`: offline, mocked integration, live integration, and safety validation strategy.
- `docs/working.md`: changelog and lessons learned.
- `skills/skill_typefully_twitter.md`: canonical root skill document for agents.
- `src/typefully_twitter_skill/`: future Python package placeholder.
- `scripts/`: future stable CLI wrapper placeholder.
- `tests/`: future test placeholder.

## Public Repo Rules

- Never commit `.env`, API keys, browser cookies, session headers, local databases, analytics exports, generated reports, or logs.
- Public examples must use fake values: `example.com`, `@example_user`, `replace-with-your-real-key`, and `op://your-vault/your-item/your-field`.
- Keep private workspace overlays outside this repo. Workspace-specific handles, account IDs, campaign conventions, or content strategy rules belong in a private global skill file.
- Expose exactly one root skill globally: `skills/skill_typefully_twitter.md`.

## Design Boundary

This project should unify three capabilities into one contract:

1. Typefully publishing and draft management.
2. Typefully account-level metrics.
3. X per-post analytics and local analytics storage.

It should not become a generic Typefully API passthrough, a full social media dashboard, a content-generation system, or an engagement automation tool.

## Maintenance

- Update `docs/working.md` after meaningful design or implementation changes.
- Keep `README.md`, `docs/rfc.md`, `docs/test.md`, and `skills/skill_typefully_twitter.md` aligned when the CLI contract changes.
- Use the project `.venv` when Python code is eventually added. Create it with `uv venv .venv` and install dependencies with `uv pip install -e '.[dev]'`.
