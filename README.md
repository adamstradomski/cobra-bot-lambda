# cobra-bot-lambda

Discord bot that shows pairings and standings of [Cobra](https://tournaments.nullsignal.games/) Netrunner tournaments, running on AWS Lambda. See [`docs/requirements.md`](docs/requirements.md), [`docs/spec.md`](docs/spec.md) and [`docs/tasks.md`](docs/tasks.md).

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

> **Running from the Claude desktop app on Windows:** the app is an MSIX package, so writes to `%APPDATA%\uv` are virtualised, and uv's Python install fails with `os error 17`. If you hit this, set `UV_PYTHON_INSTALL_DIR` to a directory outside `%APPDATA%`. uv run from a normal terminal is not affected.
