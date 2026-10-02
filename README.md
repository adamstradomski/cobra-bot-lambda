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

All four checks must pass before a change is merged. GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs them on every push and pull request, after `uv sync --locked`, which fails if `uv.lock` is out of date with `pyproject.toml`; it then runs `sam validate --lint` and `sam build`.

### Infrastructure (AWS SAM)

[`template.yaml`](template.yaml) defines the stack (SPEC §11). [`samconfig.toml`](samconfig.toml) holds the shared defaults: region `eu-central-1`, lint on validate, cached builds, and IAM capability with a change-set prompt on deploy. SAM CLI can run without installing it, through `uvx --from aws-sam-cli==1.166.2 sam …`, as CI does. Set `SAM_CLI_TELEMETRY=0` to opt out of SAM's telemetry.

| Command | What it does |
|---------|--------------|
| `sam validate --lint` | Checks the template with the SAM translator and cfn-lint. Needs no AWS credentials. |
| `sam build` | Builds both functions from `src/` into `.aws-sam/build/` (git-ignored). It installs `src/requirements.txt` with Linux wheels for the Lambda runtime and needs `python3.14` on `PATH`. |
| `uv export --frozen --no-dev --no-hashes --no-emit-project --no-header --format requirements.txt -o src/requirements.txt` | Regenerates the Lambda dependency list from `uv.lock`. Run it after changing runtime dependencies; `tests/test_template.py` fails while the file is out of date. |

Deployment (`sam deploy`) is covered in [Deployment](#deployment).

## Deployment

This section takes you from nothing to a working bot: a Discord application, the AWS stack, the interactions endpoint, the slash command and install links. Every value specific to one bot goes in at deploy time, so you can run several bots, or deploy to another AWS account, from the same code.

### 1. Prerequisites

- An AWS account and credentials for it on your machine: [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), then `aws configure` (or `aws configure sso`). The credentials need to be able to create the stack: CloudFormation, Lambda, IAM roles, S3, CloudWatch Logs and Budgets.
- [uv](https://docs.astral.sh/uv/). It provides Python 3.14 and runs SAM CLI without installing it (`uvx --from aws-sam-cli==1.166.2 sam …`). If you install [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) yourself, plain `sam …` works the same.
- `python3.14` on `PATH` for `sam build`. Check with `python3.14 --version`; `uv python install 3.14` provides it.

The commands below use `sam`. Replace it with `uvx --from aws-sam-cli==1.166.2 sam` if SAM CLI is not installed.

### 2. Create the Discord application

In the [Discord Developer Portal](https://discord.com/developers/applications):

1. **New Application**, and give it a name.
2. **General Information**: copy the **Application ID** and the **Public Key**. You need both below.
3. **Installation**:
   - **Installation Contexts**: tick **User Install** and **Guild Install**.
   - **Install Link**: choose **Discord Provided Link**.
   - **Default Install Settings**: for both contexts, add only the scope `applications.commands`. Do not add `bot` and grant no permissions. The bot replies through interaction webhooks and needs neither (`docs/requirements.md`, Out of scope).
4. **Bot**: press **Reset Token** and copy the token. It is used only once per command change, by the registration script on your machine (step 5). Keep it in a password manager; it is never deployed.

### 3. Deploy the stack

```bash
sam build
```

```bash
sam deploy --guided
```

`sam deploy --guided` asks for:

| Prompt | Answer |
|--------|--------|
| Stack Name | A name for this bot, e.g. `cobra-bot`. Use a different name per bot. |
| AWS Region | `eu-central-1` |
| Parameter DiscordPublicKey | The **Public Key** from step 2 (64 hex characters). |
| Parameter BudgetEmail | Where the monthly budget alert goes. |
| Confirm changes before deploy | `Y` |
| Allow SAM CLI IAM role creation | `Y` (the functions need their own roles) |
| Disable rollback | `N` |
| InteractionsFunction Function Url has no authentication. Is this okay? | `Y`. Discord must reach it; every request is checked against the public key instead (NFR-07). |
| Save arguments to configuration file | `Y` |
| SAM configuration file | **`samconfig.local.toml`**, not the default `samconfig.toml`: git ignores it, so your email never reaches the repository. (`--config-file` cannot point at it yet; SAM requires the file to exist.) |
| SAM configuration environment | `default`, or one name per bot, e.g. `mybot` |

SAM shows the change set; confirm it. When the deploy finishes, copy the output **`InteractionsEndpointUrl`**.

Later deploys of the same bot reuse the saved answers:

```bash
sam build
```

```bash
sam deploy --config-file samconfig.local.toml
```

Add `--config-env mybot` if you saved the settings under a name other than `default`.

### 4. Connect Discord to the endpoint

Developer Portal → **General Information** → **Interactions Endpoint URL**: paste `InteractionsEndpointUrl` and **Save Changes**. Discord sends a signed PING. The save only succeeds if the function verifies it with the public key you deployed, so a successful save means the deployment works.

### 5. Register the `/cobra` command

```bash
DISCORD_APPLICATION_ID=… DISCORD_BOT_TOKEN=… uv run scripts/register_commands.py
```

PowerShell:

```powershell
$env:DISCORD_APPLICATION_ID = "…"; $env:DISCORD_BOT_TOKEN = "…"; uv run scripts/register_commands.py
```

See [`register_commands.py`](#scriptsregister_commandspy--register-the-cobra-command-with-discord-t22) for options and exit codes. Global commands can take a while to show up in Discord clients. Run it again only when the command definition changes.

### 6. Install the bot

Developer Portal → **Installation** → copy the **Install Link**. Opening it lets you choose:

- **Add to server**: needs the Manage Server permission there. The commands then work for everyone in that server.
- **Add to my apps** (user install): the commands work for you in any server, DM or group DM (FR-18).

### Operating the bot

| Command | What it does |
|---------|--------------|
| `sam logs --stack-name cobra-bot --name WorkerFunction --tail` | Streams the Worker's logs (use `InteractionsFunction` for the endpoint). Add `--config-file samconfig.local.toml` to pick up the region. |
| `sam delete --stack-name cobra-bot --config-file samconfig.local.toml` | Deletes the stack. CloudFormation cannot delete a bucket that still has objects. Cached objects expire within a day, or empty the bucket first with `aws s3 rm s3://<CacheBucketName> --recursive` (bucket name in the stack outputs). |

**Cost.** At the expected load the stack stays within the AWS free tier. The budget alert (USD 5/month) watches the whole account, not only this stack; with several bots in one account, each stack adds its own alert for the same total.

**Troubleshooting.**

- **Discord rejects the Interactions Endpoint URL:** the deployed `DiscordPublicKey` does not match the application. Redeploy with the right key, then save the URL again.
- **"The application did not respond":** the endpoint did not answer within 3 seconds. Check the `InteractionsFunction` logs.
- **The bot says "Something went wrong":** the Worker hit an unexpected error. Check the `WorkerFunction` logs.

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
| `DISCORD_BOT_TOKEN` | Bot token (Developer Portal → Bot), used only for this API call. Required without `--dry-run`. It is never printed and never deployed to AWS. Keep it out of shell history and the repository, e.g. in a password manager or a local `.env` file (git-ignored). |

What it does: one `PUT https://discord.com/api/v10/applications/{id}/commands` request. Global commands can take a while to appear in Discord clients.

**Exit codes:** `0` registered, or payload printed with `--dry-run`; `1` request failed (network error or non-2xx; Discord's error message is printed); `2` invalid arguments or missing environment variables.

> **Running from the Claude desktop app on Windows:** the app is an MSIX package, so writes to `%APPDATA%\uv` are virtualised, and uv's Python install fails with `os error 17`. If you hit this, set `UV_PYTHON_INSTALL_DIR` to a directory outside `%APPDATA%`. uv run from a normal terminal is not affected.
