# CLAUDE.md — rules for the coding agent

Read `docs/requirements.md`, `docs/spec.md` and `docs/tasks.md` before starting work. Implement one task from `docs/tasks.md` at a time, in order, unless told otherwise. If `docs/findings.md` exists, it overrides assumptions marked TBD in `docs/spec.md`.

## Language

All documentation, code comments, commit messages, and READMEs are written in English.

## Stack

- Python 3.14 (AWS Lambda managed runtime `python3.14`; see `docs/spec.md` §3). Pin it in `pyproject.toml` and `template.yaml`.
- Package/env manager: `uv`. Lint/format: `ruff`. Types: `mypy --strict`. Tests: `pytest`.
- Runtime: AWS Lambda (InteractionsFunction + WorkerFunction), Discord HTTP interactions, AWS SAM, region `eu-central-1`.
- Cache: Amazon S3 (shared): Cobra data 60 s, drawn images 10 min.
- Libraries: `httpx`, `PyNaCl`, `Pillow` (reply images; imported only by the Worker, never by InteractionsFunction); `boto3` is provided by the Lambda runtime (dev dependency for tests and types only).

## Layout

```
src/cobra_bot/
  handlers/     # Lambda entry points only; thin
  discord/      # signature verification, webhook client
  cobra/        # refs, HTTP client, cache logic, S3 store, JSON parser
  domain/       # models, round state, search — pure, no I/O
  formatting/   # reply images, their embed text, text helpers — pure, no I/O
  fonts/        # bundled Noto Sans for the images (SIL OFL)
  messages.py   # all user-facing strings
scripts/        # capture_snapshots.py, anonymize_fixture.py, register_commands.py,
                #   aws_ops.py, preview.py, generate_identities.py
tests/          # mirrors src/; anonymised fixtures in tests/fixtures/
docs/           # requirements.md, spec.md, tasks.md, findings.md, acceptance.md
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

Before finishing any task, run pytest, ruff check, ruff format --check and mypy (plus `sam validate --lint` once `template.yaml` exists). All must pass.

## Conventions

- `domain/` and `formatting/` are pure functions over frozen dataclasses; no network, clock, or filesystem access.
- I/O dependencies (HTTP client, clock, cache store, boto3 clients) are injected so they can be faked.
- Unit tests never touch the network or real AWS; use fixtures, mocked HTTP, the in-memory `CacheStore`, and botocore `Stubber`.
- Fixtures from real tournaments are committed only after anonymisation (`scripts/anonymize_fixture.py`). Tests refer to players by Cobra player ID, not by name.
- Every acceptance criterion (`AC-xx` in `docs/spec.md`) has at least one test; reference the AC ID in the test name or docstring.
- Every outgoing Discord payload sets `allowed_mentions: {"parse": []}`; player names are always made safe (`code_text` in images, `escape_markdown` in message text).
- User-facing text is in English and lives only in `messages.py`.
- Never log secrets, tokens, or full Cobra/Discord payloads.
- Type hints everywhere; no `Any` without a comment explaining why.
- Keep diffs small: one task per change; no unrelated refactors.

## Git

- `develop` is the integration branch. Work on a feature branch per task, created from `develop` and merged back into it, named after the change type and task (e.g. `feat/t02-repo-scaffold`, `docs/findings-update`); never commit directly to `main`.
- Commit messages follow Conventional Commits (`feat: add standings formatter`, `fix: …`, `test: …`, `docs: …`, `chore: …`).

## Do not change without asking

- Command names, options, visibility (public vs ephemeral), integration types and contexts — a public contract registered in Discord.
- Cache TTLs (Cobra data 60 s, images 10 min), the stale-data behaviour, and the 5-message cap.
- `template.yaml` resources, IAM permissions, retry settings, template parameters and environment variable names, region, budget.
- Python version; adding or replacing dependencies.
- Anything listed as Out of scope in `docs/requirements.md` (e.g. auto-publishing, `bot` scope, Gateway).
- Requirements, spec, or acceptance criteria — propose changes instead of editing silently.
- Anything marked TBD — ask the user rather than deciding.

## Never

- Commit secrets, tokens, `.env` files, or non-anonymised tournament data.
- Call Cobra, Discord or AWS from tests.
- Run `sam deploy` or modify AWS resources without explicit user approval.
