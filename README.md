# cobra-bot-lambda

Discord bot that shows pairings and standings of [Cobra](https://tournaments.nullsignal.games/) Netrunner tournaments, running on AWS Lambda. See [`docs/requirements.md`](docs/requirements.md), [`docs/spec.md`](docs/spec.md) and [`docs/tasks.md`](docs/tasks.md).

## Development

Requirements: [uv](https://docs.astral.sh/uv/). uv installs Python 3.14 (pinned in `.python-version` and `pyproject.toml`) when needed.

| Command | What it does |
|---------|--------------|
| `uv sync` | Creates `.venv` and installs the project and its dev tools (pytest, ruff, mypy, and Pillow for `scripts/preview.py`) at the versions locked in `uv.lock`. |
| `uv run pytest` | Runs the tests in `tests/`. Configured in `pyproject.toml`: warnings are errors, unknown markers and config keys fail the run. Exits non-zero if any test fails. |
| `UPDATE_GOLDEN=1 uv run pytest tests/formatting/test_golden.py` | Rewrites the golden files in `tests/golden/` (the full Discord payloads for the `single_sided_top8` and `dss` fixtures) from the current renderer instead of comparing against them. Review the diff before committing; without the variable the test fails on any difference. |
| `uv run ruff check .` | Lints all Python files. Add `--fix` to apply safe fixes. |
| `uv run ruff format --check .` | Checks formatting without changing files. Run `uv run ruff format .` to reformat. Markdown files are excluded. |
| `uv run mypy src` | Type-checks `src/` in strict mode. |
| `uv run --env-file .env scripts/preview.py 5018 pairings` | Posts a reply rendered from a local export to your Discord test channel, without deploying; see [`preview.py`](#scriptspreviewpy--see-a-reply-in-discord-without-deploying). |

All four checks must pass before a change is merged. GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs them on every push and pull request, after `uv sync --locked`, which fails if `uv.lock` is out of date with `pyproject.toml`; it then runs `sam validate --lint` and `sam build`. On `main`, a successful CI run triggers the deploy workflow ([Automatic deployment from main](#automatic-deployment-from-main)).

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
| `uv run scripts/aws_ops.py logs tail` / `logs 10m` | Shortcut for `sam logs` (and for `sam build` / `sam deploy`) that reads the stack name and region from `samconfig.local.toml`; see [`aws_ops.py`](#scriptsaws_opspy--build-deploy-and-read-logs-from-your-machine). |
| `sam logs --stack-name cobra-bot --name WorkerFunction --tail` | Streams the Worker's logs (use `InteractionsFunction` for the endpoint). Add `--config-file samconfig.local.toml` to pick up the region. |
| `sam delete --stack-name cobra-bot --config-file samconfig.local.toml` | Deletes the stack. CloudFormation cannot delete a bucket that still has objects. Cached objects expire within a day, or empty the bucket first with `aws s3 rm s3://<CacheBucketName> --recursive` (bucket name in the stack outputs). |

**Cost.** At the expected load the stack stays within the AWS free tier. The budget alert (USD 5/month) watches the whole account, not only this stack; with several bots in one account, each stack adds its own alert for the same total.

**Troubleshooting.**

- **Discord rejects the Interactions Endpoint URL:** the deployed `DiscordPublicKey` does not match the application. Redeploy with the right key, then save the URL again.
- **"The application did not respond":** the endpoint did not answer within 3 seconds. Check the `InteractionsFunction` logs.
- **The bot says "Something went wrong":** the Worker hit an unexpected error. Check the `WorkerFunction` logs.

### Automatic deployment from main

Every push to `main` (normally a merge from `develop`) deploys the `cobra-bot` stack once CI passes. [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) starts when the CI workflow finishes successfully for a push to `main`. It checks out the commit CI tested, runs `sam build`, then `sam deploy` without a change-set prompt. A push that changes nothing in the stack still succeeds (`--no-fail-on-empty-changeset`). Only one deploy runs at a time and none is cancelled halfway. A failed CloudFormation update rolls back to the previous version and fails the job.

GitHub Actions holds no AWS keys. It signs in through OIDC as the role `github-deploy-cobra-bot`, which can only upload the build to SAM's artifact bucket and run change sets on the `cobra-bot` stack. CloudFormation applies them as `cfn-exec-cobra-bot`, which can only manage resources whose names start with `cobra-bot-`: functions, their roles, the cache bucket, log groups and the budget. Both roles are defined in [`bootstrap/github-deploy.yaml`](bootstrap/github-deploy.yaml). `tests/test_deploy_setup.py` checks that the roles stay scoped and agree with the workflow. Anyone who can push to `main` can change the inline policies of the `cobra-bot-*` function roles, so protect `main`.

One-time setup:

1. **Deploy the roles** with administrator credentials. `SamArtifactBucket` is the `SamCliSourceBucket` output of the `aws-sam-cli-managed-default` stack, created by the first manual `sam deploy`. Pass `CreateOidcProvider=false` if the account already has an identity provider for `token.actions.githubusercontent.com`. The role trusts only the `production` environment of the repository named by `GitHubRepository`, written as GitHub's OIDC subject prefix shows it under repository **Settings → Actions → OIDC** (`owner@owner-id/name@repo-id`). Override it if that prefix differs; a mismatch fails the deploy with `Not authorized to perform sts:AssumeRoleWithWebIdentity`.

   ```bash
   aws cloudformation deploy --region eu-central-1 --stack-name github-deploy-cobra-bot --template-file bootstrap/github-deploy.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides SamArtifactBucket=<SamCliSourceBucket>
   ```

   Then print the two role ARNs:

   ```bash
   aws cloudformation describe-stacks --region eu-central-1 --stack-name github-deploy-cobra-bot --query "Stacks[0].Outputs" --output table
   ```

   Do not name this stack `cobra-bot-…`: the execution role may modify anything with that prefix.

   **Updating the roles later.** On an existing stack, `aws cloudformation deploy` keeps the stored value of every parameter you don't pass, even when the template's default has changed; if nothing else changed it reports `No changes to deploy`. Pass any parameter whose new value you want explicitly, for example after changing the `GitHubRepository` default:

   ```bash
   aws cloudformation deploy --region eu-central-1 --stack-name github-deploy-cobra-bot --template-file bootstrap/github-deploy.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides GitHubRepository=adamstradomski@83371226/cobra-bot-lambda@1400117730
   ```

   Check the subject the role now trusts:

   ```bash
   aws iam get-role --role-name github-deploy-cobra-bot --query "Role.AssumeRolePolicyDocument.Statement[0].Condition"
   ```

2. **Create the GitHub environment.** Repository **Settings → Environments → New environment** `production`. Under **Deployment branches and tags**, choose **Selected branches and tags** and add `main`. Leave **Required reviewers** off for fully automatic deploys.

3. **Add the environment's values** (same page):

   | Kind | Name | Value |
   |------|------|-------|
   | Variable | `AWS_DEPLOY_ROLE_ARN` | `GitHubDeployRoleArn` output |
   | Variable | `AWS_CFN_EXECUTION_ROLE_ARN` | `CloudFormationExecutionRoleArn` output |
   | Variable | `DISCORD_PUBLIC_KEY` | The deployed `DiscordPublicKey` (in `samconfig.local.toml` under `parameter_overrides`) |
   | Secret | `BUDGET_EMAIL` | The deployed `BudgetEmail` |

   Use the values already deployed. A different public key breaks the Discord endpoint, and a different e-mail moves the budget alert.

4. **Protect `main`** (**Settings → Rules → Rulesets → New branch ruleset**, target `main`, enforcement **Active**, empty bypass list). Select **Restrict deletions**, **Block force pushes** and **Require status checks to pass** with the check `Lint, type-check, test`. Leave **Require a pull request before merging** and **Require linear history** off: `main` is updated by pushing `develop`, which contains merge commits.

5. **Release:** once CI is green on `develop`, fast-forward `main` to it:

   ```bash
   git push origin develop:main
   ```

   The required status check accepts only a commit that already passed CI, so wait for the `develop` run to finish. A merge commit made locally has no checks yet and is rejected, which is why `main` is only ever fast-forwarded. Follow the deploy under **Actions → Deploy**. The first run also records `cfn-exec-cobra-bot` as the stack's CloudFormation role.

Manual `sam deploy` from your machine still works. After step 5 the stack uses `cfn-exec-cobra-bot` for every update, so your own deploys also need permission to pass that role (`iam:PassRole`). An administrator has it.

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

### `scripts/aws_ops.py` — build, deploy and read logs from your machine

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

**What it reads:** `samconfig.local.toml` in the repository root, written by the first `sam deploy --guided` ([step 3](#3-deploy-the-stack)). `deploy` and `logs` need it; `build` does not. `logs` takes `stack_name` and `region` from `[ENV.deploy.parameters]`, with the region falling back to `[ENV.global.parameters]`; without a region, SAM uses `eu-central-1` from `samconfig.toml`. AWS credentials come from your usual AWS CLI profile (`AWS_PROFILE` etc.).

**Which `sam`:** `sam` from `PATH` if installed, otherwise `uvx --from aws-sam-cli==1.166.2 sam`, the version CI uses (a test keeps them in step). It prints the command it runs to stderr before running it.

**Exit codes:** SAM's own exit code (`0` on success); `0` when Ctrl+C stops `logs tail`; `130` when Ctrl+C stops any other command; `2` invalid arguments, a bad `WINDOW`, neither `sam` nor `uvx` on `PATH`, or `samconfig.local.toml` missing, not valid TOML, without the chosen `--config-env`, or (for `logs`) without a stack name.

> **Running from the Claude desktop app on Windows:** the app is an MSIX package, so writes to `%APPDATA%\uv` are virtualised, and uv's Python install fails with `os error 17`. If you hit this, set `UV_PYTHON_INSTALL_DIR` to a directory outside `%APPDATA%`. uv run from a normal terminal is not affected.

### `scripts/preview.py` — see a reply in Discord without deploying

Renders a `/cobra` reply from a local Cobra export and posts it to a channel on your test server, in about a second. Use it when you change the layout (`formatting/`, `messages.py`, `discord/api.py`): no `sam build`, no deploy, no Cobra request. The reply goes through the Worker's own code (`commands.execute`, the cache, the parser, the formatters, `message_payload`), so the embeds are byte for byte the ones the bot sends; `tests/scripts/test_preview.py` checks them against the golden files. It runs in the project environment, so it uses your working copy of `cobra_bot`.

```bash
uv run --env-file .env scripts/preview.py SOURCE pairings [--round N] [OPTIONS]
uv run --env-file .env scripts/preview.py SOURCE standings [OPTIONS]
uv run --env-file .env scripts/preview.py SOURCE player QUERY [OPTIONS]
```

Options go after the subcommand, e.g. `scripts/preview.py 5018 pairings --round 2 --stale`.

| Argument / option | Default | Meaning |
|-------------------|---------|---------|
| `SOURCE` | — | A tournament ID: the newest `snapshots/{ID}/{ts}.json` (not `*.meta.json`), written by `capture_snapshots.py`. Or a path to a Cobra export, e.g. `tests/fixtures/dss.json`. |
| `pairings [--round N]` / `standings` / `player QUERY` | — | Same subcommands and options as `/cobra`. Without `--round`, the latest round. |
| `--dry-run` | off | Print the JSON payloads to stdout (UTF-8) instead of posting them. Needs no webhook. |
| `--stale` | off | Render as stale data with Cobra unavailable (the cached copy is 10 minutes old). |
| `--private` | off | Render as stale data because the tournament became private. Not with `--stale`. |
| `--id N` | from `SOURCE` | Tournament ID used in the Cobra links. Default: `SOURCE` itself, or the name of the export's directory if it is a number, else `1`. Must be positive. |
| `--format a\|b2\|c` | `a` | Reply layout; see [Layouts under test](#layouts-under-test) below. `a` is the bot's reply. |
| `--page N` | `1` | `b2`, `c`: which page to post. A page past the last is an error (exit `2`). |
| `--all-pages` | off | `b2`, `c`: post every page. Not with `--page`. |
| `--no-mockup` | off | `b2`: keep the real buttons and select. A channel webhook rejects them (exit `1`, `Discord: {"components": …}`); useful with `--dry-run`. |
| `--font PATH` / `--bold-font PATH` | a system font | `c`: TrueType fonts for the image. Default: Segoe UI (Windows), DejaVu Sans (Linux), Arial (macOS). `--bold-font` defaults to `--font`. |
| `--save-images DIR` | — | `c`: also write the PNGs into `DIR` (created if missing), also with `--dry-run`. |
| `--note TEXT` | — | Post `TEXT` as a plain message first (markdown works, mentions never ping), to label what follows. |
| `DISCORD_PREVIEW_WEBHOOK_URL` | — | Channel webhook URL, `https://discord.com/api/webhooks/<id>/<token>`. Required without `--dry-run`. It contains a secret token and is never printed. |

**Local data.** The snapshots of a single-sided (4909) and a double-sided (5018) tournament are in `snapshots/` (see `snapshots/README.md`). For another tournament, capture it once:

```bash
uv run scripts/capture_snapshots.py <ID> --once
```

**One-time setup.**

1. On your test server: **Server Settings → Integrations → Webhooks → New Webhook**, pick the channel, and optionally give it the bot's name and avatar so the messages look like the bot's. **Copy Webhook URL**.
2. Put it into `.env` in the repository root (git-ignored), one line: `DISCORD_PREVIEW_WEBHOOK_URL=https://discord.com/api/webhooks/…`. `uv run --env-file .env` loads it, and stops with `No environment file found` if the file is missing. Setting the variable in your shell and dropping `--env-file .env` works too.

**How it differs from the bot.** Every message is a new post; the bot edits its "thinking…" reply for the first message and posts the rest as follow-ups, which looks the same. The author is the webhook's name and avatar. Channel webhooks cannot post ephemeral messages, so `player` replies are public in the preview (the script says so on stderr). Discord applies the same embed limits and rendering to both.

It prints one line to stderr when done, e.g. `preview: standings of 20261001T160955Z.json in format A sent as 2 message(s) in 420 ms` (the count includes the `--note` message). Warnings from the formatters (such as an identity missing from the short-name map) are printed too.

**Exit codes:** `0` posted, or printed with `--dry-run`; `1` Discord rejected a post or could not be reached (HTTP status or error type is printed, with the start of Discord's error body, never the URL); `2` invalid arguments, no snapshot for the ID, an unreadable `SOURCE`, `DISCORD_PREVIEW_WEBHOOK_URL` missing or not a webhook URL, a `--page` past the last page, `--format b2`/`c` with `player`, or no usable font for `c`.

#### Layouts under test

`--format` picks how the reply looks. Only `a` is what the bot sends; the others live in [`src/cobra_bot/preview/`](src/cobra_bot/preview/), which the bot never imports (`tests/preview/test_isolation.py`), and are shown only here until one is chosen.

| Format | What it posts | Commands |
|--------|---------------|----------|
| `a` | The bot's embeds: a table in an `ansi` code block, coloured on desktop, plain on mobile (Discord's mobile app drops ANSI colours). | all |
| `b2` | A Components V2 container in the bot colour, in plain markdown that looks the same on desktop and mobile (no code block, no ANSI colours). Built to look like `c`: 🔵 / 🟣 mark the Corp and Runner IDs; ranks and table numbers sit in padded inline code, like a column; in standings a divider separates the points groups. Standings: the rank and name in bold, then a small grey line with the IDs, the points and the SoS. Pairings: one line per player, the Corp first, the winner in bold, with the ID and points; double-sided, the round total, then a grey line with both games. Below: **Prev / 1 / 3 / Next / Refresh** and, for pairings, a round select. Pages keep to Discord's 4000 characters and 40 components. | pairings, standings |
| `c` | The table as a PNG in an embed: full colours, real columns with headings (standings: #, player, Corp, Runner, points, SoS), no cut names; the text cannot be selected. At most 40 rows per image, one message per page. | pairings, standings |

**The controls are a mockup.** Channel webhooks may post only non-interactive components (Discord answers `HTTP 400 {"components": ["0"]}` otherwise), and nothing handles clicks yet. The preview therefore turns every button into a link button with the same label (it opens the tournament on Cobra), and the round select into one link button showing the chosen round, `Round 2 ▾`. The mockup keeps the real message's component count, so a page that fits the 40-component cap still fits. `--no-mockup --dry-run` prints the real components the bot would send.

**Requirements for `c`:** [Pillow](https://pypi.org/project/pillow/), a dev dependency (`uv sync` installs it; it is not in `src/requirements.txt`, so it never reaches Lambda), and a font with Latin Extended glyphs; Pillow's built-in font has none of `Żółw`.

To compare all layouts in one go, label each with `--note`:

```bash
uv run --env-file .env scripts/preview.py 5018 pairings --round 2 --format b2 --note "## B2 · DSS pairings, round 2"
```

### `scripts/generate_identities.py` — short ID names from NetrunnerDB

Regenerates [`src/cobra_bot/formatting/identities.py`](src/cobra_bot/formatting/identities.py), the map from an identity to its short name (embed format A-1 to A-3), from every Corp and Runner identity on [NetrunnerDB](https://netrunnerdb.com). Run it when NetrunnerDB has new identities (a new set), or after changing a short name. Do not edit `identities.py` by hand. Runs in the project environment (it uses `httpx`).

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
- **Override:** if the key is in `OVERRIDES` in the script, that name. It holds the initial mapping (A-3) and IDs whose derived name is too long, ambiguous or not what players call them (`New Angeles Sol` → `NA Sol`, `Near-Earth Hub` → `NEH`, `Virtual Intelligence, P.I.` → `Vic`).
- **Derived otherwise:** Runner — the nickname in quotes, else the first word (after a leading `The `), comma dropped. Corp — the whole name if it fits in 9 columns, else without a leading `The `, else the first word. Anything still longer than 9 is cut with `…`.

It prints a warning (and still writes) for a name it had to cut, two IDs on one side sharing a short name, and an override for an ID NetrunnerDB does not have. Fix them in `OVERRIDES` and run it again. `tests/scripts/test_generate_identities.py` checks that every override is in the committed file.

**Exit codes:** `0` written, printed, or up to date with `--check`; `1` NetrunnerDB failed (network error, non-200, not JSON, a page without data, too many pages, a next page on another host), `--input` is not JSON, no identities found (the old file is kept), or `--check` found the file out of date; `2` invalid arguments or an unreadable `--input`.
