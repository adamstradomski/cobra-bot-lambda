# Tasks — Cobra Discord Bot

Order = execution order. Each task should fit in one reviewable diff (one PR). "DoD" = definition of done. From T02 on, every task also requires CI green (lint, format check, type-check, tests).

## Phase 0 — Discovery

### T01 — Capture live tournament snapshots (World Championship weekend)
Exception: runs before the repo scaffold, as a standalone script; not covered by CI.
- `scripts/capture_snapshots.py <id> --interval 120` saves `/tournaments/{id}.json` with a timestamp into `snapshots/` (git-ignored).
- Run during live rounds; keep representative files: round start, mid-round, round complete, round 1 with no results, cut start.
- Find and save one double-sided Swiss tournament export.
- Record responses for `/tournaments/{SHORTCODE}` (status, redirect target), a non-existent ID, and (if available) an unpublished tournament.
- **DoD:** raw snapshots stored locally; `docs/findings.md` answers SPEC open questions 1–5.

## Phase 1 — Project skeleton

### T02 — Repository scaffold
- `pyproject.toml` (uv, Python 3.14 pinned), `src/cobra_bot/`, `tests/`, ruff + mypy (strict) + pytest config, `.gitignore`, `README.md` stub.
- **DoD:** `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` pass on an empty test.

### T03 — CI workflow
- `.github/workflows/ci.yml`: install uv, run lint, format check, mypy, pytest on push and PR.
- **DoD:** workflow green on GitHub.

### T04 — Fixture anonymiser
- `scripts/anonymize_fixture.py` per SPEC §12 (deterministic pseudonyms, optional injection of edge-case names).
- Anonymise and commit fixtures: `single_sided_top8` (4909), `large_top_cut` (4990), `dss` (5018, live double-sided), `not_started` (5125, an empty real export instead of a synthetic one).
- **DoD:** tests prove player IDs are remapped consistently, ranks and scores are unchanged, and no original name or other personal data remains; fixtures committed.

## Phase 2 — Domain (pure, no I/O)

### T05 — Domain models and JSON parser
- `domain/models.py`, `cobra/parser.py` per SPEC §4, including double-sided seats.
- **DoD:** parser tests for all fixtures (player count, round count, a bye, an elimination game, a double-sided pairing).

### T06 — Round-state derivation
- `domain/rounds.py` per SPEC §5, adjusted to `docs/findings.md`.
- **DoD:** AC-03–AC-08 and the round-completion part of AC-22 covered at logic level.

### T07 — Tournament reference parser
- `cobra/refs.py` per SPEC §6 (ID and URL; shortcode token recognised only if T01 found a method).
- **DoD:** AC-13 passes.

### T08 — Player search
- `domain/search.py` per SPEC §8.
- **DoD:** AC-09, AC-10, AC-11, AC-12 pass.

## Phase 3 — Formatting

### T09 — Text helpers and messages module
- `messages.py` (all user-facing strings), markdown escaping, ID shortening, Discord timestamp helper.
- **DoD:** unit tests incl. names with `@`, `*`, `_`, `~`.

### T10 — Pairings formatter
- Header, single-sided, double-sided, bye, intentional draw, notes (in progress / top cut).
- **DoD:** AC-02, AC-03 and the display part of AC-22 pass at output level.

### T11 — Standings formatter
- **DoD:** AC-01 and AC-08 pass at output level.

### T12 — Player card formatter
- **DoD:** tests for: player with opponent, player with bye, player during top cut (note shown).

### T13 — Embed chunking
- `formatting/chunking.py` per SPEC §9 (limits + 5-message cap + "…and N more" line).
- **DoD:** AC-14 and AC-15 pass.

## Phase 4 — I/O

### T14 — Cobra HTTP client
- `cobra/client.py`: fetch JSON, 8 s timeout, User-Agent, error mapping (404 → NotFound, 5xx/timeout/connection → Unavailable); shortcode resolution if FR-12 is in.
- **DoD:** tests with mocked HTTP (no network) for 200, 404, 500, timeout.

### T15 — Cache logic with in-memory store
- `cobra/cache.py` over a `CacheStore` protocol; TTL 60 s, stale fallback; injectable clock; in-memory fake for tests.
- **DoD:** AC-16 and AC-17 pass.

### T16 — S3 cache store
- `cobra/s3_store.py`: get/put object with `fetched-at` metadata.
- **DoD:** unit tests with a stubbed boto3 client (botocore Stubber) for hit, miss, put.

### T17 — Single-flight lock (Should)
- Conditional-write lock per SPEC §7 in both the protocol and S3 store.
- **DoD:** AC-18 passes with the in-memory fake; S3 conditional-write calls covered with Stubber.

### T18 — Discord signature verification
- `discord/verify.py` using PyNaCl.
- **DoD:** tests with a generated key pair: valid, invalid, missing headers.

### T19 — Discord webhook client
- `discord/api.py`: edit original, follow-ups, ephemeral flag, `allowed_mentions` always empty, honour `Retry-After`.
- **DoD:** AC-21 passes with mocked HTTP; 429 handling tested.

## Phase 5 — Handlers

### T20 — Interactions handler
- PING, routing, deferred ack (ephemeral for `player`), async invoke of Worker (boto3 client injected).
- **DoD:** AC-19 passes.

### T21 — Worker handler
- Wire refs → cache/client → domain → formatting → chunking → webhook client; map errors to messages (FR-16).
- **DoD:** end-to-end test per command with fixtures, fake store and mocked HTTP; error-path tests.

### T22 — Command registration script
- `scripts/register_commands.py` (global commands per SPEC §2; app ID and token from env; `--dry-run`).
- **DoD:** AC-24 passes.

## Phase 6 — Infrastructure and release

### T23 — SAM template
- `template.yaml` per SPEC §11: two functions, Function URL, `EventInvokeConfig` (no retries), S3 bucket with lifecycle, IAM least privilege, 14-day log retention, SSM parameter names as parameters, budget USD 5 with email parameter.
- Add `sam validate --lint` to CI.
- **DoD:** `sam validate --lint` and `sam build` pass locally and in CI; AC-23 passes.

### T24 — Deployment guide
- `README.md`: Discord application setup (guild + user install, no bot permissions), SSM parameters, `sam deploy --guided`, Interactions Endpoint URL, command registration, install links.
- **DoD:** the author deploys to a fresh AWS account by following the README only.

### T25 — Manual acceptance test
- Run AC-20 on a test server and via user install; record results in `docs/acceptance.md`.
- **DoD:** all checklist items pass or have issues filed.
