# CLAUDE.md — rules for the coding agent

A Discord bot (`/cobra …`) that shows pairings, standings and the top cut of Cobra tournaments, on AWS Lambda. Read only the documents the change touches (table below), not all of `docs/`.

## Where to look

| Change in… | Read |
|------------|------|
| `handlers/`, `discord/`, `commands.py`, `registration.py`, `template.yaml` | `docs/spec/architecture.md` |
| `cobra/refs.py`, `client.py`, `parser.py`, `domain/models.py` | `docs/spec/cobra.md` |
| `cobra/cache.py`, `s3_store.py`, `image_cache.py` | `docs/spec/cache.md` |
| `domain/` | `docs/spec/domain.md` |
| `formatting/`, `messages.py` | `docs/spec/output.md` |
| `scripts/` | `docs/scripts.md` (and `docs/spec/fixtures.md` for the anonymiser) |
| `tests/fixtures/`, test data | `docs/spec/fixtures.md` |
| A new or changed behaviour | `docs/requirements.md`, `docs/spec/acceptance-criteria.md`, and the area above |
| Why something is the way it is | `docs/decisions.md` |

`docs/archive/` is history (old spec, findings, tasks): do not read it unless asked. Do not read `tests/fixtures/*.json` whole (up to 600 KB); query them (`uv run python -c "…"`).

Keep the documents current in the same change: update the spec file of the area you touched, `docs/requirements.md` (Status) when a requirement changes, `docs/scripts.md` and `README.md` when a command or option changes. Record why in `docs/decisions.md`, one row; keep dates and history out of the spec.

## Stack

- Python 3.14 (Lambda `python3.14`), pinned in `.python-version`, `pyproject.toml` and `template.yaml`. `uv`, `ruff`, `mypy --strict`, `pytest`.
- AWS Lambda (InteractionsFunction + WorkerFunction), Discord HTTP interactions, AWS SAM, region `eu-central-1`. Shared S3 cache: Cobra data 60 s, drawn images 10 min.
- Libraries: `httpx`, `PyNaCl`, `Pillow` (Worker only, never imported by InteractionsFunction); `boto3` comes with the Lambda runtime (dev dependency only).

## Layout

```
src/cobra_bot/
  handlers/     # Lambda entry points only; thin
  discord/      # signature verification, webhook client
  cobra/        # refs, HTTP client, cache logic, S3 store, JSON parser
  domain/       # models, round state, top cut, search — pure, no I/O
  formatting/   # reply images, their embed text, text helpers — pure, no I/O
  fonts/        # bundled Noto Sans for the images (SIL OFL)
  messages.py   # all user-facing strings
scripts/        # capture_snapshots, anonymize_fixture, register_commands, aws_ops,
                #   preview, generate_identities
tests/          # mirrors src/; anonymised fixtures in tests/fixtures/
template.yaml   # AWS SAM
```

## Commands

```bash
uv sync                          # install dependencies
uv run pytest                    # tests
uv run ruff check .              # lint
uv run ruff format --check .     # format check (`uv run ruff format .` to fix)
uv run mypy src                  # type-check
sam validate --lint              # validate template
sam build                        # build Lambda package
```

Before finishing, run pytest, ruff check, ruff format --check, mypy and `sam validate --lint`. All must pass.

## Conventions

- `domain/` and `formatting/` are pure functions over frozen dataclasses; no network, clock, or filesystem access.
- I/O dependencies (HTTP client, clock, cache store, boto3 clients) are injected so they can be faked.
- Every outgoing Discord payload sets `allowed_mentions: {"parse": []}`; player names are made safe (`code_text` in images, `escape_markdown` in message text).
- User-facing text is in English and lives only in `messages.py`.
- Never log secrets, tokens, or full Cobra/Discord payloads.
- Type hints everywhere; no `Any` without a comment explaining why.
- Keep diffs small: one change per branch; no unrelated refactors.
- All documentation, comments and commit messages are in English.
- Tests: `tests/CLAUDE.md`.

## Git

- `develop` is the integration branch. Work on a feature branch from `develop`, merged back into it, named after the change type (`feat/top-cut`, `fix/…`, `docs/…`); never commit directly to `main`.
- Conventional Commits (`feat: …`, `fix: …`, `test: …`, `docs: …`, `chore: …`).

## Do not change without asking

- Command names, options, visibility, integration types and contexts — a public contract registered in Discord.
- Cache TTLs (Cobra data 60 s, images 10 min), the stale-data behaviour, and the 5-page cap.
- `template.yaml` resources, IAM permissions, retry settings, template parameters and environment variable names, region, budget.
- Python version; adding or replacing dependencies.
- Anything Out of scope in `docs/requirements.md` (auto-publishing, `bot` scope, Gateway, …).
- Requirements, spec, or acceptance criteria — propose changes instead of editing silently.
- Anything marked TBD — ask rather than decide.

## Never

- Commit secrets, tokens, `.env` files, or non-anonymised tournament data.
- Call Cobra, Discord or AWS from tests.
- Run `sam deploy` or modify AWS resources without explicit user approval.
