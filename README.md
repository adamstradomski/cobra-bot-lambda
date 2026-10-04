# cobra-bot-lambda

A Discord bot that shows [Cobra](https://tournaments.nullsignal.games/) Netrunner tournaments in Discord: pairings, standings, the top-cut ranking and bracket. It serves Cobra's data from a shared cache, so a busy event does not send everyone to Cobra. It runs on AWS Lambda.

## Contents

- [Using the bot](#using-the-bot)
  - [Commands](#commands)
  - [What the replies show](#what-the-replies-show)
- [Developing your own bot](#developing-your-own-bot)
  - [How it works](#how-it-works)
  - [Set up the project](#set-up-the-project)
  - [Everyday commands](#everyday-commands)
  - [Run your own bot](#run-your-own-bot)
  - [Operate the bot](#operate-the-bot)
  - [Automatic deployment from main](#automatic-deployment-from-main)
  - [Scripts](#scripts)
  - [Project documents](#project-documents)

## Using the bot

To add the bot to your server or to your Discord account, and for more about it, see **[jinteki.win/cobra-bot](https://jinteki.win/cobra-bot)**.

### Commands

Every command starts with `/cobra` and takes a `tournament`: the Cobra tournament ID (`4909`), a link to any of its pages (`https://tournaments.nullsignal.games/tournaments/4909/players/standings`) or its shortcode (`QNSF`).

| Command | Shows |
|---------|-------|
| `/cobra pairings tournament [round]` | The pairings of the latest round, Swiss or top cut, or of round `round`. Whether the round is complete or in progress; table, players, sides, IDs and results. A top-cut round shows game numbers and who won. |
| `/cobra standings tournament` | The Swiss standings: rank, player, Corp and Runner ID, points and SoS, and after which round they apply. Once Swiss is over, whether there is a top cut and how far it is. |
| `/cobra top-cut tournament` | The top-cut ranking: place, player, IDs, games won and lost in the cut, and seed. |
| `/cobra bracket tournament` | The top-cut bracket as one picture, laid out like the bracket page on Cobra. |
| `/cobra player tournament query` | Players whose name contains `query` (letter case and accents ignored), with their standing and their game in the latest round. Up to 10 names at once, separated by commas: `Alice, Bob`. |

### What the replies show

- Replies are public: everyone in the channel sees them.
- Tables are pictures, so they look the same on desktop and on phones. Long lists are split into up to 5 pictures; past that, the reply links to the full page on Cobra.
- Data comes from Cobra and is at most a minute old. Each reply says when it was fetched. If Cobra is down, or the organiser has made the tournament private, the bot shows the last copy it has and says so.
- IDs are shown by short name (`Nuvem`, `HB`, `Vic`).

## Developing your own bot

### How it works

Discord sends each `/cobra` command over HTTP to a small Lambda function (`InteractionsFunction`), which checks Discord's signature, acknowledges within Discord's 3-second limit and hands the work to a second function (`WorkerFunction`). The Worker reads the tournament from Cobra through a shared S3 cache (60 s for Cobra data, 10 minutes for drawn pictures), draws the reply and sends it back through Discord's webhook. The bot needs no bot user, no permissions and no Gateway connection; only the `applications.commands` scope. The full design is in [`docs/spec.md`](docs/spec.md).

```
src/cobra_bot/
  handlers/     Lambda entry points
  discord/      signature check, webhook client
  cobra/        tournament references, HTTP client, cache, S3 store, JSON parser
  domain/       rounds, search, top-cut bracket (pure, no I/O)
  formatting/   text, pictures, short ID names (pure, no I/O)
  messages.py   every user-facing sentence
scripts/        development and operations scripts (see Scripts)
tests/          mirrors src/; anonymised Cobra exports in tests/fixtures/
template.yaml   the AWS stack (SAM)
```

### Set up the project

You need [uv](https://docs.astral.sh/uv/); it installs Python 3.14 (pinned in `.python-version` and `pyproject.toml`) when needed.

```bash
uv sync
```

This creates `.venv` and installs the project (including Pillow, which draws the reply pictures) and its dev tools (pytest, ruff, mypy) at the versions locked in `uv.lock`.

To see a reply in Discord without deploying anything, create a webhook in a channel of your test server and use [`scripts/preview.py`](docs/scripts.md#scriptspreviewpy--see-a-reply-in-discord-without-deploying):

```bash
uv run scripts/preview.py tests/fixtures/single_sided_top8.json bracket
```

### Everyday commands

| Command | What it does |
|---------|--------------|
| `uv run pytest` | Runs the tests in `tests/`. Configured in `pyproject.toml`: warnings are errors, unknown markers and config keys fail the run. Exits non-zero if any test fails. |
| `uv run ruff check .` | Lints all Python files. Add `--fix` to apply safe fixes. |
| `uv run ruff format --check .` | Checks formatting without changing files. Run `uv run ruff format .` to reformat. Markdown files are excluded. |
| `uv run mypy src` | Type-checks `src/` in strict mode. |
| `uv run scripts/preview.py SOURCE COMMAND` | Posts a reply rendered from a local Cobra export to your Discord test channel, without deploying ([details](docs/scripts.md#scriptspreviewpy--see-a-reply-in-discord-without-deploying)). |
| `sam validate --lint` | Checks [`template.yaml`](template.yaml) with the SAM translator and cfn-lint. Needs no AWS credentials. |
| `sam build` | Builds both functions from `src/` into `.aws-sam/build/` (git-ignored). It installs `src/requirements.txt` with Linux wheels for the Lambda runtime and needs `python3.14` on `PATH`. |
| `uv export --frozen --no-dev --no-hashes --no-emit-project --no-header --format requirements.txt -o src/requirements.txt` | Regenerates the Lambda dependency list from `uv.lock`. Run it after changing runtime dependencies; `tests/test_template.py` fails while the file is out of date. |

The four checks (pytest, ruff check, ruff format, mypy) must pass before a change is merged. GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs them on every push and pull request, after `uv sync --locked`, which fails if `uv.lock` is out of date with `pyproject.toml`; it then runs `sam validate --lint` and `sam build`. On `main`, a successful CI run deploys the bot ([Automatic deployment from main](#automatic-deployment-from-main)).

SAM CLI can run without installing it, through `uvx --from aws-sam-cli==1.166.2 sam …`, as CI does. [`samconfig.toml`](samconfig.toml) holds the shared defaults: region `eu-central-1`, lint on validate, cached builds, and IAM capability with a change-set prompt on deploy. Set `SAM_CLI_TELEMETRY=0` to opt out of SAM's telemetry.

Work happens on a feature branch from `develop`, merged back into `develop`; `main` is only fast-forwarded to `develop` to release. Commit messages follow Conventional Commits. The rules for changes are in [`CLAUDE.md`](CLAUDE.md).

### Run your own bot

These steps take you from nothing to a working bot of your own: a Discord application, the AWS stack, the interactions endpoint, the slash command and install links. Every value specific to one bot goes in at deploy time, so you can run several bots, or deploy to another AWS account, from the same code.

#### 1. Prerequisites

- An AWS account and credentials for it on your machine: [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), then `aws configure` (or `aws configure sso`). The credentials need to be able to create the stack: CloudFormation, Lambda, IAM roles, S3, CloudWatch Logs and Budgets.
- [uv](https://docs.astral.sh/uv/). It provides Python 3.14 and runs SAM CLI without installing it (`uvx --from aws-sam-cli==1.166.2 sam …`). If you install [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) yourself, plain `sam …` works the same.
- `python3.14` on `PATH` for `sam build`. Check with `python3.14 --version`; `uv python install 3.14` provides it.

The commands below use `sam`. Replace it with `uvx --from aws-sam-cli==1.166.2 sam` if SAM CLI is not installed.

#### 2. Create the Discord application

In the [Discord Developer Portal](https://discord.com/developers/applications):

1. **New Application**, and give it a name.
2. **General Information**: copy the **Application ID** and the **Public Key**. You need both below.
3. **Installation**:
   - **Installation Contexts**: tick **User Install** and **Guild Install**.
   - **Install Link**: choose **Discord Provided Link**.
   - **Default Install Settings**: for both contexts, add only the scope `applications.commands`. Do not add `bot` and grant no permissions. The bot replies through interaction webhooks and needs neither (`docs/requirements.md`, Out of scope).
4. **Bot**: press **Reset Token** and copy the token. It is used only once per command change, by the registration script on your machine (step 5). Keep it in a password manager; it is never deployed.

#### 3. Deploy the stack

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

#### 4. Connect Discord to the endpoint

Developer Portal → **General Information** → **Interactions Endpoint URL**: paste `InteractionsEndpointUrl` and **Save Changes**. Discord sends a signed PING. The save only succeeds if the function verifies it with the public key you deployed, so a successful save means the deployment works.

#### 5. Register the `/cobra` command

Put the Application ID and the bot token into `.env` in the repository root (git-ignored; see [Local settings: `.env`](docs/scripts.md#local-settings-env)):

```
DISCORD_APPLICATION_ID=…
DISCORD_BOT_TOKEN=…
```

Then:

```bash
uv run scripts/register_commands.py
```

See [`register_commands.py`](docs/scripts.md#scriptsregister_commandspy--register-the-cobra-command-with-discord-t22) for options and exit codes. Global commands can take a while to show up in Discord clients. Run it again only when the command definition changes (it did on 2026-10-04: `top-cut` and `bracket` were added and descriptions changed).

#### 6. Install the bot

Developer Portal → **Installation** → copy the **Install Link**. Opening it lets you choose:

- **Add to server**: needs the Manage Server permission there. The commands then work for everyone in that server.
- **Add to my apps** (user install): the commands work for you in any server, DM or group DM (FR-18).

### Operate the bot

| Command | What it does |
|---------|--------------|
| `uv run scripts/aws_ops.py logs tail` / `logs 10m` | Shortcut for `sam logs` (and for `sam build` / `sam deploy`) that reads the stack name and region from `samconfig.local.toml`; see [`aws_ops.py`](docs/scripts.md#scriptsaws_opspy--build-deploy-and-read-logs-from-your-machine). |
| `sam logs --stack-name cobra-bot --name WorkerFunction --tail` | Streams the Worker's logs (use `InteractionsFunction` for the endpoint). Add `--config-file samconfig.local.toml` to pick up the region. |
| `sam delete --stack-name cobra-bot --config-file samconfig.local.toml` | Deletes the stack. CloudFormation cannot delete a bucket that still has objects. Cached objects expire within a day, or empty the bucket first with `aws s3 rm s3://<CacheBucketName> --recursive` (bucket name in the stack outputs). |

**Cost.** At the expected load the stack stays within the AWS free tier. The budget alert (USD 5/month) watches the whole account, not only this stack; with several bots in one account, each stack adds its own alert for the same total.

**Troubleshooting.**

- **Discord rejects the Interactions Endpoint URL:** the deployed `DiscordPublicKey` does not match the application. Redeploy with the right key, then save the URL again.
- **"The application did not respond":** the endpoint did not answer within 3 seconds. Check the `InteractionsFunction` logs.
- **The bot says "Something went wrong":** the Worker hit an unexpected error. Check the `WorkerFunction` logs.

### Automatic deployment from main

Once set up, every push to `main` deploys the `cobra-bot` stack through GitHub Actions after CI passes, signing in to AWS through OIDC with no stored keys. The workflow, the IAM roles it uses, and the one-time setup (roles, GitHub environment, branch protection, releasing) are in [`docs/automatic-deployment.md`](docs/automatic-deployment.md).

### Scripts

Options, inputs, outputs and exit codes of each script are in [`docs/scripts.md`](docs/scripts.md). `register_commands.py` and `preview.py` read credentials from `.env` in the repository root (git-ignored; [format](docs/scripts.md#local-settings-env)).

| Command | What it does |
|---------|--------------|
| `uv run scripts/preview.py SOURCE pairings\|standings\|top-cut\|bracket\|player …` | Renders a reply from a local Cobra export and posts it to your test channel through a webhook (or prints it with `--dry-run`). |
| `uv run scripts/register_commands.py [--dry-run]` | Registers the global `/cobra` command with Discord. Run it after a change to the commands. |
| `uv run scripts/aws_ops.py build\|deploy\|logs …` | `sam build`, `sam deploy` and `sam logs` with the stack name, region and config file filled in. |
| `uv run scripts/capture_snapshots.py ID … \| --probe PATH …` | Saves Cobra's raw JSON exports of live tournaments (or probes URLs) into `snapshots/`, to study Cobra's format. |
| `uv run scripts/anonymize_fixture.py INPUT OUTPUT […]` | Turns a raw export into a test fixture with every player renamed and renumbered. |
| `uv run scripts/generate_identities.py [--check]` | Regenerates the short ID names (`formatting/identities.py`) from NetrunnerDB. |

### Project documents

| Document | Contents |
|----------|----------|
| [`docs/requirements.md`](docs/requirements.md) | What the bot must do, and what is out of scope. |
| [`docs/spec.md`](docs/spec.md) | Design: commands, data model, cache, output, infrastructure, acceptance criteria. |
| [`docs/embeded_format.md`](docs/embeded_format.md) | The exact layout of every reply. |
| [`docs/findings.md`](docs/findings.md) | How Cobra's export actually behaves, from captured snapshots and Cobra's source. |
| [`docs/tasks.md`](docs/tasks.md) | The implementation plan, task by task. |
| [`docs/acceptance.md`](docs/acceptance.md) | The manual acceptance checklist for a deployed bot. |
| [`docs/scripts.md`](docs/scripts.md) | Every script in detail. |
| [`docs/automatic-deployment.md`](docs/automatic-deployment.md) | Deploying from `main` with GitHub Actions. |
