# Architecture, commands, security, infrastructure

Code: `handlers/`, `discord/`, `commands.py`, `registration.py`, `template.yaml`. Why it is built this way: `docs/decisions.md`.

## Flow

```
Discord ──signed POST──▶ InteractionsFunction (Lambda + Function URL)
                          verify Ed25519 · PING → PONG · deferred ack (type 5)
                          · async invoke Worker (Event, no retries)
                                   │
                                   ▼
                         WorkerFunction ──GET /tournaments/{id}.json──▶ Cobra
                          resolve ref · shared S3 cache (≤ 60 s) · round state
                          · draw images · edit the original response ──▶ Discord
```

Both functions share one code package. Discord scope `applications.commands` only: replies go through interaction webhooks, so there is no bot user and no channel permission. Integration types: guild install and user install.

The Worker receives only a `Job` (application ID, interaction token, the parsed command), never the whole interaction. It never raises: every failure ends in a logged error and, where possible, an error reply.

## Commands

| Command | Options | Visibility |
|---------|---------|------------|
| `/cobra pairings` | `tournament` (string, required), `round` (integer ≥ 1, optional) | Public |
| `/cobra standings` | `tournament` (string, required) | Public |
| `/cobra top-cut` | `tournament` (string, required) | Public |
| `/cobra bracket` | `tournament` (string, required) | Public |
| `/cobra player` | `tournament` (string, required), `query` (string, required, 1–200 chars; up to 10 names separated by `,` or `;`) | Public |

Registered globally by `scripts/register_commands.py`: `integration_types: [0, 1]` (guild, user), `contexts: [0, 1, 2]` (guild, bot DM, private channel), no `default_member_permissions`. Every deferred response is public (no flags).

## Components

| Module | Responsibility |
|--------|----------------|
| `handlers/interactions.py` | Signature check, PING, deferred response, async invoke of the Worker. Never imports Pillow. |
| `handlers/worker.py` | Runs the command (`commands.execute`), sends the reply, logs timings and `images cached=N drawn=M`. |
| `commands.py` | Parses the interaction into a `Command`; runs it and maps every expected failure to a message (FR-16). |
| `discord/verify.py` | Ed25519 check of `X-Signature-Ed25519` + `X-Signature-Timestamp`. |
| `discord/api.py` | Edits the original response (text, an embed, or image pages as one multipart message); `allowed_mentions: {"parse": []}` always; retries only HTTP 429 after `Retry-After` (≤ 3 times, ≤ 10 s each). |
| `cobra/` | References, HTTP client, parser, cache, S3 store: `docs/spec/cobra.md`, `docs/spec/cache.md`. |
| `domain/` | Round state, top cut, search: `docs/spec/domain.md`. |
| `formatting/`, `messages.py` | Images, embed text, all user-facing strings: `docs/spec/output.md`. |
| `image_cache.py` | Drawn images in S3: `docs/spec/cache.md`. |

Libraries: `httpx` (HTTP), `PyNaCl` (Ed25519), `Pillow` (Worker only), `boto3` (provided by the Lambda runtime). Runtime: Python 3.14 (`python3.14`, x86_64).

## Security

- Signature verified before any processing; missing or invalid headers → 401.
- Configuration from environment variables set by template parameters, read once per cold start: InteractionsFunction `DISCORD_PUBLIC_KEY` (hex, not a secret) and `WORKER_FUNCTION_NAME`; WorkerFunction `CACHE_BUCKET`. Missing, blank or invalid values fail at startup. Nothing account- or bot-specific is hard-coded.
- The bot token is never deployed: only `scripts/register_commands.py` uses it, locally, from `DISCORD_BOT_TOKEN` (with `DISCORD_APPLICATION_ID`). The functions need no secrets.
- IAM least privilege: InteractionsFunction may invoke WorkerFunction. WorkerFunction may read, write, delete and list objects in the cache bucket (list, so a missing key is a 404, not a 403). No SSM.
- Outbound calls only to `tournaments.nullsignal.games` and `discord.com`.
- No user data persisted; the cache holds public tournament data and expires.
- Logs: command name, tournament ID, cache hit/miss/stale, durations, errors. Never tokens, interaction payloads or full Cobra exports.

## Infrastructure (AWS SAM, `eu-central-1`)

| Resource | Settings |
|----------|----------|
| `InteractionsFunction` | Function URL, auth NONE (protected by the signature check); 512 MB, timeout 10 s (a cold start must stay under Discord's 3 s). |
| `WorkerFunction` | 1769 MB (one full vCPU, for drawing), timeout 60 s; `EventInvokeConfig`: `MaximumRetryAttempts: 0`, `MaximumEventAgeInSeconds: 600` (interaction tokens expire after 15 min). |
| `CacheBucket` | Private, public access blocked, bucket-owner object ownership, SSE-S3; lifecycle deletes objects after 1 day and aborts incomplete multipart uploads after 1 day. |
| Log groups | One per function (`LoggingConfig`), 14-day retention. |
| `AWS::Budgets::Budget` | USD 5/month, email alert on actual and forecasted cost above 100 % (covers the whole account). |

Parameters: `DiscordPublicKey` → `DISCORD_PUBLIC_KEY`, `BudgetEmail`. Output: `InteractionsEndpointUrl` (the Function URL for the Developer Portal). `samconfig.toml` pins the region. Deployment: `README.md` (manual), `docs/automatic-deployment.md` (GitHub Actions on `main`).
