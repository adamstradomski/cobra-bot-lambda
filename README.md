# cobra-bot-lambda

Discord bot that shows pairings and standings of [Cobra](https://tournaments.nullsignal.games/) Netrunner tournaments, running on AWS Lambda. See [`docs/requirements.md`](docs/requirements.md), [`docs/spec.md`](docs/spec.md) and [`docs/tasks.md`](docs/tasks.md).

## Development

Requirements: [uv](https://docs.astral.sh/uv/). uv installs Python 3.14 (pinned in `.python-version` and `pyproject.toml`) when needed.

| Command | What it does |
|---------|--------------|
| `uv sync` | Creates `.venv` and installs the project and its dev tools (pytest, ruff, mypy) at the versions locked in `uv.lock`. |
| `uv run pytest` | Runs the tests in `tests/`. Configured in `pyproject.toml`: warnings are errors, unknown markers and config keys fail the run. Exits non-zero if any test fails. |
| `uv run ruff check .` | Lints all Python files. Add `--fix` to apply safe fixes. |
| `uv run ruff format --check .` | Checks formatting without changing files. Run `uv run ruff format .` to reformat. Markdown files are excluded. |
| `uv run mypy src` | Type-checks `src/` in strict mode. |

All four checks must pass before a change is merged. GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs them on every push and pull request, after `uv sync --locked`, which fails if `uv.lock` is out of date with `pyproject.toml`.

## Scripts

### `scripts/capture_snapshots.py` — capture raw Cobra snapshots (T01)

A standalone discovery script that uses only the standard library. It records how Cobra's JSON export looks at different points in a tournament, and how Cobra answers shortcodes, missing tournaments and unpublished tournaments. Its output answers the SPEC open questions in `docs/findings.md`.

It needs Python ≥ 3.14, declared in the script's inline metadata (PEP 723). `uv run` downloads that Python version if needed:

```bash
uv run scripts/capture_snapshots.py ID [ID ...] [--interval SECONDS] [--count N | --once] [--out DIR] [--base-url URL]
uv run scripts/capture_snapshots.py --probe PATH [PATH ...] [--out DIR] [--base-url URL]
```

Pass either tournament IDs (poll mode) or `--probe` (probe mode), not both.

| Option | Default | Meaning |
|--------|---------|---------|
| `ID …` | — | Tournament IDs to poll. Each cycle fetches `/tournaments/{id}.json` for each ID in turn. |
| `--interval SECONDS` | `120` | Seconds between the starts of poll cycles. Must be at least `60`, to keep load on Cobra low. |
| `--count N` | run until Ctrl+C | Stop after N poll cycles. |
| `--once` | — | One poll cycle; same as `--count 1`. |
| `--probe PATH …` | — | Fetch each path once **without following redirects**, e.g. `tournaments/HBYM`. A leading `/` is optional. In Git Bash leave it out, because MSYS rewrites `/tournaments/…` into a Windows path. When there is a redirect to the same host, the script follows one hop and records it too. |
| `--out DIR` | `snapshots` | Output directory. `snapshots/` is git-ignored. |
| `--base-url URL` | `https://tournaments.nullsignal.games` | Cobra base URL. Override it to test against a local server. |

**What it writes**

- Poll mode, in `DIR/{id}/`, with UTC timestamps such as `20261003T141502Z`:
  - `{ts}.json`: the raw export, byte for byte (gunzipped). It is written only when the body differs from the newest snapshot already in that directory, so unchanged polls just log `unchanged`. The comparison also works after a restart.
  - `{ts}.meta.json`: fetch details (URL, final URL after redirects, status, selected headers, duration, size, SHA-256) and a structural summary (player count, round count, and pairings and elimination games per round).
  - `{ts}.body.txt` + `{ts}.meta.json`: written instead of the above when the status is not 200 or the body is not valid JSON.
- Probe mode, in `DIR/probes/`:
  - `{ts}_{path-slug}.meta.json`: status, headers (including `Location`), the first 500 characters of the body, the redirect target, and the response of the one hop it followed.
  - `{ts}_{path-slug}.body.json` / `.body.txt`: the full response body, if there is one.

It logs one line per request to stderr. It never logs response bodies.

**Behaviour toward Cobra:** it sends the User-Agent `cobra-bot-lambda-snapshots/0.1 (+https://github.com/adamstradomski/cobra-bot-lambda)`, uses an 8 s timeout and never retries. A failed poll is logged and the script waits for the next cycle.

**Exit codes**

| Code | Meaning |
|------|---------|
| `0` | Finished normally: Ctrl+C, `--count` reached, or every probe got an HTTP response (whatever its status). |
| `1` | With `--once` / `--count 1`: a fetch failed (network error, non-200, or invalid JSON). In probe mode: at least one probe got no HTTP response. |
| `2` | Invalid arguments. |

**T01 checklist (World Championship weekend)**

```bash
uv run scripts/capture_snapshots.py <worlds-id> --interval 120
uv run scripts/capture_snapshots.py --probe tournaments/<SHORTCODE> tournaments/<SHORTCODE>.json tournaments/99999999.json
uv run scripts/capture_snapshots.py --probe tournaments/<unpublished-id>.json
uv run scripts/capture_snapshots.py <double-sided-id> --once
```

Keep representative snapshots: round start, mid-round, round complete, round 1 with no results, and cut start. Snapshots contain real player names. Anonymise them with `scripts/anonymize_fixture.py` (T04) before anything goes into `tests/fixtures/`.

### `scripts/anonymize_fixture.py` — anonymise a Cobra export into a test fixture (T04)

Turns a raw export from `snapshots/` into a committable fixture in `tests/fixtures/`, following [SPEC §12](docs/spec.md). Standard library only, Python ≥ 3.14 via `uv run`.

```bash
uv run scripts/anonymize_fixture.py INPUT OUTPUT [--title TEXT] [--date YYYY-MM-DD] [--inject-edge-case-names]
```

| Argument / option | Default | Meaning |
|-------------------|---------|---------|
| `INPUT` | — | Raw Cobra export (JSON) to read. |
| `OUTPUT` | — | Fixture to write: UTF-8, 2-space indented, LF line endings. Parent directories are created and an existing file is replaced. |
| `--title TEXT` | `Fixture Tournament` | Tournament `name` in the fixture. |
| `--date YYYY-MM-DD` | `2000-01-01` | Tournament `date` in the fixture. |
| `--inject-edge-case-names` | off | Gives the four lowest-ranked players the names `@Mention`, `*bold_name~`, `Maëlig` and `Żółw`, starting from the last rank, so tests cover escaping and diacritics. |

**What changes and what is kept**

- **Player IDs:** remapped everywhere (`players`, `rounds`, `eliminationPlayers`): new ID = 1000 + position (1-based) in the sorted original IDs. `null` (bye) stays `null`.
- **Names:** become `Player{new ID − 1000:04d}`, in `players` and `eliminationPlayers`.
- **Pronouns:** `pronouns` becomes `""`.
- **Other identifying fields:** `tournamentOrganiser` becomes `{"nrdbId": 1, "nrdbUsername": "fixture-organiser"}`, and the shortcode link (`uploadedfrom`) becomes `…/tournaments/FXTR`.
- **Kept unchanged:** ranks, points, SoS/eSoS, scores, tables, flags, factions and identities.

**Unknown keys** anywhere in the export make the script stop with an error. A new Cobra field must be reviewed and added to the allowlist in the script before it can reach a fixture.

**Exit codes:** `0` fixture written; `1` input unreadable, not JSON, or rejected (unknown key, unknown player ID); `2` invalid arguments.

The commands that regenerate the committed fixtures are kept with the local snapshots, in `snapshots/README.md`.

### `scripts/register_commands.py` — register the `/cobra` command with Discord (T22)

Overwrites the application's **global** commands with the definition in [`src/cobra_bot/registration.py`](src/cobra_bot/registration.py) (SPEC §2): `/cobra pairings`, `/cobra standings` and `/cobra player`, installable to servers and to user accounts (`integration_types: [0, 1]`), usable in servers, the bot DM and private channels (`contexts: [0, 1, 2]`). It runs in the project environment, so it uses the project's `httpx` and `cobra_bot`.

```bash
uv run scripts/register_commands.py --dry-run
uv run scripts/register_commands.py
```

| Option / variable | Meaning |
|-------------------|---------|
| `--dry-run` | Print the JSON payload to stdout and exit. Sends nothing and needs no credentials. |
| `DISCORD_APPLICATION_ID` | Application ID (Developer Portal → General Information). Required without `--dry-run`. |
| `DISCORD_BOT_TOKEN` | Bot token (Developer Portal → Bot), used only for this API call. Required without `--dry-run`. It is never printed. Keep it out of shell history, e.g. read it from SSM `/cobra-bot/discord/bot-token`. |

What it does: one `PUT https://discord.com/api/v10/applications/{id}/commands` request. Global commands can take a while to appear in Discord clients.

**Exit codes:** `0` registered, or payload printed with `--dry-run`; `1` request failed (network error or non-2xx; Discord's error message is printed); `2` invalid arguments or missing environment variables.

> **Running from the Claude desktop app on Windows:** the app is an MSIX package, so writes to `%APPDATA%\uv` are virtualised, and uv's Python install fails with `os error 17`. If you hit this, set `UV_PYTHON_INSTALL_DIR` to a directory outside `%APPDATA%`. uv run from a normal terminal is not affected.
