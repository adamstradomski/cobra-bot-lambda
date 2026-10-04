# Scripts

Every script in `scripts/`: what it does, its options, what it reads and writes, and its exit codes. The [README](../README.md#scripts) lists them in one table. Run them from the repository root.

## Contents

- [Local settings: `.env`](#local-settings-env)
- [`capture_snapshots.py`](#scriptscapture_snapshotspy--capture-raw-cobra-snapshots-t01): capture raw Cobra snapshots
- [`anonymize_fixture.py`](#scriptsanonymize_fixturepy--anonymise-a-cobra-export-into-a-test-fixture-t04): turn a snapshot into a test fixture
- [`register_commands.py`](#scriptsregister_commandspy--register-the-cobra-command-with-discord-t22): register `/cobra` with Discord
- [`aws_ops.py`](#scriptsaws_opspy--build-deploy-and-read-logs-from-your-machine): build, deploy and read logs
- [`preview.py`](#scriptspreviewpy--see-a-reply-in-discord-without-deploying): see a reply in Discord without deploying
- [`generate_identities.py`](#scriptsgenerate_identitiespy--short-id-names-from-netrunnerdb): short ID names from NetrunnerDB

## Local settings: `.env`

`scripts/register_commands.py` and `scripts/preview.py` read `.env` in the repository root (git-ignored, never deployed), so credentials stay out of the shell history:

```
DISCORD_APPLICATION_ID=123456789012345678
DISCORD_BOT_TOKEN=…
DISCORD_PREVIEW_WEBHOOK_URL=https://discord.com/api/webhooks/…
```

One `KEY=VALUE` per line; blank lines and lines starting with `#` are skipped; `export ` before the key and quotes around the value are allowed. `#` inside a value is part of it, and nothing is expanded. A variable set in the shell wins over the file. A missing file is fine; a line that is not `KEY=VALUE` is skipped with a warning naming its line number (never its content). Read by `src/cobra_bot/envfile.py`; the Lambda functions never read it.

## `scripts/capture_snapshots.py` — capture raw Cobra snapshots (T01)

A standalone discovery script that uses only the standard library. It records how Cobra's JSON export looks at different points in a tournament, and how Cobra answers shortcodes, missing tournaments and unpublished tournaments. Its output answers the SPEC open questions in [`findings.md`](findings.md).

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

## `scripts/anonymize_fixture.py` — anonymise a Cobra export into a test fixture (T04)

Turns a raw export from `snapshots/` into a committable fixture in `tests/fixtures/`, following [SPEC §12](spec.md). Standard library only, Python ≥ 3.14 via `uv run`.

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

## `scripts/register_commands.py` — register the `/cobra` command with Discord (T22)

Overwrites the application's **global** commands with the definition in [`src/cobra_bot/registration.py`](../src/cobra_bot/registration.py) (SPEC §2): `/cobra pairings`, `/cobra standings`, `/cobra top-cut`, `/cobra bracket` and `/cobra player`, installable to servers and to user accounts (`integration_types: [0, 1]`), usable in servers, the bot DM and private channels (`contexts: [0, 1, 2]`). It runs in the project environment, so it uses the project's `httpx` and `cobra_bot`.

```bash
uv run scripts/register_commands.py --dry-run
uv run scripts/register_commands.py
```

| Option / variable | Meaning |
|-------------------|---------|
| `--dry-run` | Print the JSON payload to stdout and exit. Sends nothing and needs no credentials. |
| `DISCORD_APPLICATION_ID` | Application ID (Developer Portal → General Information). Required without `--dry-run`. Read from the environment, else from `.env` ([Local settings](#local-settings-env)). |
| `DISCORD_BOT_TOKEN` | Bot token (Developer Portal → Bot), used only for this API call. Required without `--dry-run`. It is never printed and never deployed to AWS. Keep it out of shell history and the repository: put it in `.env` (git-ignored), which the script reads ([Local settings](#local-settings-env)). |

What it does: one `PUT https://discord.com/api/v10/applications/{id}/commands` request. Global commands can take a while to appear in Discord clients.

**Exit codes:** `0` registered, or payload printed with `--dry-run`; `1` request failed (network error or non-2xx; Discord's error message is printed); `2` invalid arguments or missing environment variables.

## `scripts/aws_ops.py` — build, deploy and read logs from your machine

Wraps the SAM CLI commands you run most often, so you don't have to type the stack name, region and config file each time. It uses only the standard library and runs from any directory; SAM always runs in the repository root.

```bash
uv run scripts/aws_ops.py build
uv run scripts/aws_ops.py deploy [--config-env ENV]
uv run scripts/aws_ops.py logs tail [--function worker|interactions|all] [--config-env ENV] [--stack-name NAME]
uv run scripts/aws_ops.py logs [WINDOW] [--function …] [--config-env ENV] [--stack-name NAME]
```

| Command | Runs |
|---------|------|
| `build` | `sam build`. Needs `python3.14` on `PATH`, as above. Writes `.aws-sam/build/`. |
| `deploy` | `sam deploy --config-file samconfig.local.toml --config-env ENV`. Deploys the last `build`, so run `build` first. SAM shows the change set and asks before applying it. |
| `logs tail` | `sam logs --stack-name … --region … --tail`: streams new log lines until Ctrl+C. |
| `logs WINDOW` | `sam logs --stack-name … --region … --start-time "<WINDOW> ago"`: prints the log lines of the last `WINDOW` and exits. `WINDOW` is a whole number followed by `s`, `m`, `h` or `d`, e.g. `30s`, `10m`, `2h`, `1d`; it defaults to `10m`. |

| Option | Default | Meaning |
|--------|---------|---------|
| `--config-env ENV` | `default` | Which section of `samconfig.local.toml` to use (`deploy`, `logs`). |
| `--function` | `all` | `logs` only: `worker` (`WorkerFunction`), `interactions` (`InteractionsFunction`) or `all` (every function in the stack). |
| `--stack-name NAME` | `stack_name` from the config | `logs` only: read another stack's logs. |
| anything else | — | Passed on to `sam` unchanged, e.g. `build --use-container` or `deploy --no-confirm-changeset`. |

**What it reads:** `samconfig.local.toml` in the repository root, written by the first `sam deploy --guided` ([step 3](../README.md#3-deploy-the-stack)). `deploy` and `logs` need it; `build` does not. `logs` takes `stack_name` and `region` from `[ENV.deploy.parameters]`, with the region falling back to `[ENV.global.parameters]`; without a region, SAM uses `eu-central-1` from `samconfig.toml`. AWS credentials come from your usual AWS CLI profile (`AWS_PROFILE` etc.).

**Which `sam`:** `sam` from `PATH` if installed, otherwise `uvx --from aws-sam-cli==1.166.2 sam`, the version CI uses (a test keeps them in step). It prints the command it runs to stderr before running it.

**Exit codes:** SAM's own exit code (`0` on success); `0` when Ctrl+C stops `logs tail`; `130` when Ctrl+C stops any other command; `2` invalid arguments, a bad `WINDOW`, neither `sam` nor `uvx` on `PATH`, or `samconfig.local.toml` missing, not valid TOML, without the chosen `--config-env`, or (for `logs`) without a stack name.

> **Running from the Claude desktop app on Windows:** the app is an MSIX package, so writes to `%APPDATA%\uv` are virtualised, and uv's Python install fails with `os error 17`. If you hit this, set `UV_PYTHON_INSTALL_DIR` to a directory outside `%APPDATA%`. uv run from a normal terminal is not affected.

## `scripts/preview.py` — see a reply in Discord without deploying

Renders a `/cobra` reply from a local Cobra export and posts it to a channel on your test server, in about a second. Use it when you change the layout (`formatting/`, `messages.py`, `discord/api.py`): no `sam build`, no deploy, no Cobra request. The reply goes through the Worker's own code (`commands.execute`, the cache, the parser, the image renderer and formatters, the payload builders), so the messages are the ones the bot sends: images for `pairings`, `standings`, `top-cut`, `bracket` and `player` (a one-sentence text embed when nothing matches or for an error). `tests/scripts/test_preview.py` checks that the Worker sends the same payloads. It runs in the project environment, so it uses your working copy of `cobra_bot`.

```bash
uv run scripts/preview.py SOURCE pairings [--round N] [OPTIONS]
uv run scripts/preview.py SOURCE standings [OPTIONS]
uv run scripts/preview.py SOURCE top-cut [OPTIONS]
uv run scripts/preview.py SOURCE bracket [OPTIONS]
uv run scripts/preview.py SOURCE player QUERY [OPTIONS]
```

Options go after the subcommand, e.g. `scripts/preview.py 5018 pairings --round 2 --stale`.

| Argument / option | Default | Meaning |
|-------------------|---------|---------|
| `SOURCE` | — | A tournament ID: the newest `snapshots/{ID}/{ts}.json` (not `*.meta.json`), written by `capture_snapshots.py`. Or a path to a Cobra export, e.g. `tests/fixtures/dss.json`. |
| `pairings [--round N]` / `standings` / `top-cut` / `bracket` / `player QUERY` | — | Same subcommands and options as `/cobra`. Without `--round`, the latest round, Swiss or top cut. `top-cut` and `bracket` need an export with a cut, e.g. `tests/fixtures/single_sided_top8.json`. |
| `--dry-run` | off | Print the JSON payloads to stdout (UTF-8) instead of posting them. Needs no webhook. Images are not printed; use `--save-images`. |
| `--stale` | off | Render as stale data with Cobra unavailable (the cached copy is 10 minutes old). |
| `--private` | off | Render as stale data because the tournament became private. Not with `--stale`. |
| `--id N` | from `SOURCE` | Tournament ID used in the Cobra links. Default: `SOURCE` itself, or the name of the export's directory if it is a number, else `1`. Must be positive. |
| `--save-images DIR` | — | Also write the PNGs into `DIR` (created if missing), also with `--dry-run`. |
| `--note TEXT` | — | Post `TEXT` as a plain message first (markdown works, mentions never ping), to label what follows. |
| `DISCORD_PREVIEW_WEBHOOK_URL` | — | Channel webhook URL, `https://discord.com/api/webhooks/<id>/<token>`. Required without `--dry-run`. It contains a secret token and is never printed. |

**Local data.** The snapshots of a single-sided (4909) and a double-sided (5018) tournament are in `snapshots/` (see `snapshots/README.md`); `5018 pairings --round 2` is a double-sided round with results. For another tournament, capture it once:

```bash
uv run scripts/capture_snapshots.py <ID> --once
```

**One-time setup.**

1. On your test server: **Server Settings → Integrations → Webhooks → New Webhook**, pick the channel, and optionally give it the bot's name and avatar so the messages look like the bot's. **Copy Webhook URL**.
2. Put it into `.env` in the repository root (git-ignored), one line: `DISCORD_PREVIEW_WEBHOOK_URL=https://discord.com/api/webhooks/…`. The script reads it ([Local settings](#local-settings-env)).

**How it differs from the bot.** Every message is a new post; the bot edits its "thinking…" reply for the first message and posts the rest as follow-ups, which looks the same. The author is the webhook's name and avatar. Discord applies the same embed and attachment rules to both.

It prints one line to stderr when done, e.g. `preview: standings of 20261001T160955Z.json sent as 2 message(s) in 420 ms` (the count includes the `--note` message). Warnings from the formatters (such as an identity missing from the short-name map) are printed too.

**Exit codes:** `0` posted, or printed with `--dry-run`; `1` Discord rejected a post or could not be reached (HTTP status or error type is printed, with the start of Discord's error body, never the URL); `2` invalid arguments, no snapshot for the ID, an unreadable `SOURCE`, or `DISCORD_PREVIEW_WEBHOOK_URL` missing or not a webhook URL.

## `scripts/generate_identities.py` — short ID names from NetrunnerDB

Regenerates [`src/cobra_bot/formatting/identities.py`](../src/cobra_bot/formatting/identities.py), the map from an identity to its short name (embed format A-1 to A-3), from every Corp and Runner identity on [NetrunnerDB](https://netrunnerdb.com). Run it when NetrunnerDB has new identities (a new set), or after changing a short name. Do not edit `identities.py` by hand. Runs in the project environment (it uses `httpx`).

```bash
uv run scripts/generate_identities.py
uv run scripts/generate_identities.py --check
uv run scripts/generate_identities.py --input cards.json --stdout
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--input FILE` | fetch | Read a saved NetrunnerDB v3 card list (JSON, one page) instead of fetching. |
| `--output PATH` | `src/cobra_bot/formatting/identities.py` | File to write. |
| `--check` | off | Write nothing; exit `1` if the file differs from what would be written (line endings ignored). |
| `--stdout` | off | Print the module to stdout (UTF-8) instead of writing it. Not with `--check`. |

**What it reads:** `GET https://api.netrunnerdb.com/api/v3/public/cards?filter[card_type_id]=corp_identity,runner_identity&page[size]=1000`, following `links.next` on the same host (at most 20 pages). No redirects are followed; 15 s timeout. A card that is not a well-formed identity is skipped on its own and counted.

**How a short name is chosen:**

- **Key:** the title before the first `:`, as Cobra writes it. NetrunnerDB has curly quotes where Cobra has straight ones (`René “Loup” Arcemont` → `René "Loup" Arcemont`), so curly quotes become straight; text is NFC-normalised.
- **Shared keys:** where several identities on one side share the key (Haas-Bioroid, Jinteki, NBN, Weyland Consortium), each also gets an entry under its full title (`NBN: Making News`), which the bot looks up first. Its short name is the override for the full title if there is one (`NBN R+`), else the key's short name and the initials of the rest, small words in lower case (`NBN CtM`), cut to 9. The key's own entry stays, for an identity released later.
- **Override:** if the key is in `OVERRIDES` in the script, that name. It holds the initial mapping (A-3) and IDs whose derived name is too long, ambiguous or not what players call them (`New Angeles Sol` → `NA Sol`, `Near-Earth Hub` → `NEH`, `Virtual Intelligence, P.I.` → `Vic`).
- **Derived otherwise:** Runner — the nickname in quotes, else the first word (after a leading `The `), comma dropped. Corp — the whole name if it fits in 9 columns, else without a leading `The `, else the first word. Anything still longer than 9 is cut with `…`.

It prints a warning (and still writes) for a name it had to cut, two IDs on one side sharing a short name, and an override for an ID NetrunnerDB does not have. Fix them in `OVERRIDES` and run it again. `tests/scripts/test_generate_identities.py` checks that every override is in the committed file.

**Exit codes:** `0` written, printed, or up to date with `--check`; `1` NetrunnerDB failed (network error, non-200, not JSON, a page without data, too many pages, a next page on another host), `--input` is not JSON, no identities found (the old file is kept), or `--check` found the file out of date; `2` invalid arguments or an unreadable `--input`.
