# Specification — Cobra Discord Bot

Status: Draft v0.2 · 2026-10-01 · Requirements: see `requirements.md`

## 1. Architecture overview

```
Discord user ──/cobra …──▶ Discord
                              │ POST (signed interaction)
                              ▼
                 ┌───────────────────────────┐
                 │ InteractionsFunction       │  Lambda + Function URL
                 │ - verify Ed25519 signature │
                 │ - PING → PONG              │
                 │ - deferred ack (type 5)    │
                 │ - async invoke Worker      │
                 └─────────────┬─────────────┘
                               │ Lambda async invoke (Event, no retries)
                               ▼
                 ┌───────────────────────────┐   GET /tournaments/{id}.json
                 │ WorkerFunction             │ ───────────────────────────▶ Cobra
                 │ - resolve tournament ref   │
                 │ - shared cache (≤60 s) ────┼──▶ S3 bucket (cache + locks)
                 │ - derive round state       │
                 │ - format embeds, chunk     │
                 │ - edit original + followups│ ──PATCH/POST webhooks──▶ Discord
                 └───────────────────────────┘
```

Why two functions: a Lambda Function URL returns its response only when the invocation ends. Fetching a large tournament (e.g. Worlds, ~235 players) may exceed Discord's 3-second ack limit, so the first function acknowledges immediately and hands work to the second. Both share one code package.

Why S3: Lambda scales out under load; a per-instance `/tmp` cache would let every new instance fetch from Cobra, defeating the purpose of the bot. S3 gives one cache for all instances at negligible cost.

Discord: scope `applications.commands` only; replies go through interaction webhooks, so no bot user or channel permissions are needed (verify in T23). Integration types: guild install and user install.

## 2. Commands

| Command | Options | Visibility |
|---------|---------|------------|
| `/cobra pairings` | `tournament` (string, required), `round` (integer ≥ 1, optional) | Public |
| `/cobra standings` | `tournament` (string, required) | Public |
| `/cobra player` | `tournament` (string, required), `query` (string, required, 1–32 chars) | Ephemeral |

Registered globally by a script: `integration_types: [0, 1]` (guild, user), `contexts: [0, 1, 2]` (guild, bot DM, private channel).

## 3. Components

| Module | Responsibility |
|--------|----------------|
| `handlers/interactions.py` | Lambda entry point: signature check, PING, deferred response (ephemeral flag for `player`), async invoke of Worker. |
| `handlers/worker.py` | Lambda entry point: run command, send responses. |
| `discord/verify.py` | Ed25519 verification of `X-Signature-Ed25519` + `X-Signature-Timestamp`. |
| `discord/api.py` | Edit original response, post follow-ups; always `allowed_mentions: {"parse": []}`. |
| `cobra/refs.py` | Parse `tournament` input into an ID (or shortcode, if FR-12 is implemented). |
| `cobra/client.py` | HTTP fetch of `/tournaments/{id}.json`; timeout, User-Agent; error mapping. |
| `cobra/cache.py` | Cache logic over a `CacheStore` interface: TTL, stale fallback, single-flight. |
| `cobra/s3_store.py` | `CacheStore` implementation on S3 (objects + conditional writes). |
| `cobra/parser.py` | Raw JSON → domain models. |
| `domain/models.py` | Dataclasses (section 4). |
| `domain/rounds.py` | Round-state derivation (section 5). |
| `domain/search.py` | Player name search (section 8). |
| `formatting/*.py` | Lines for pairings, standings, player cards; markdown escaping; ID shortening. |
| `formatting/chunking.py` | Split lines into embeds and messages within Discord limits and the 5-message cap. |
| `messages.py` | All user-facing strings. |

Runtime: Python 3.14 (AWS Lambda managed runtime `python3.14`; decided 2026-10-01).

Libraries: `httpx` (HTTP), `PyNaCl` (Ed25519), `boto3` (provided by Lambda runtime; S3, SSM, Lambda invoke). Tests use an in-memory `CacheStore` fake — no AWS mocking library.

## 4. Data model

Source: Cobra export `GET https://tournaments.nullsignal.games/tournaments/{id}.json` (schema link inside the export: `/schemas/tournament-schema.json`).

```python
@dataclass(frozen=True)
class Player:
    id: int
    name: str
    rank: int
    match_points: int
    sos: Decimal                 # from string "strengthOfSchedule"
    esos: Decimal
    corp_faction: str | None
    corp_identity: str | None
    runner_faction: str | None
    runner_identity: str | None

@dataclass(frozen=True)
class Seat:
    player_id: int | None        # None = bye
    role: Literal["corp", "runner"] | None   # None in byes and (TBD) double-sided pairings
    combined_score: int | None   # None = not reported (TBD)
    corp_score: int | None
    runner_score: int | None
    winner: bool | None          # elimination games only

@dataclass(frozen=True)
class Pairing:
    table: int
    seat1: Seat
    seat2: Seat
    intentional_draw: bool
    two_for_one: bool
    elimination: bool

@dataclass(frozen=True)
class Tournament:
    id: int
    name: str
    date: date
    cut_to_top: int
    preliminary_rounds: int
    players: tuple[Player, ...]
    rounds: tuple[tuple[Pairing, ...], ...]   # index 0 = round 1
    fetched_at: datetime
    stale: bool                               # served from cache after a failed fetch
```

Observed in real exports (4909, 4990, both single-sided):
- Single-sided Swiss: each pairing has one Corp and one Runner seat.
- A bye is a pairing whose `player2.id` is `null`; roles are `null`.
- Elimination rounds follow Swiss rounds in the same `rounds` array, with `eliminationGame: true` and `winner` instead of scores.
- Table numbers may have gaps.
- Some numeric fields arrive as strings (`strengthOfSchedule`), some as numbers.
- Double-sided structure is not yet observed — TBD, fixture required (T01).

## 5. Round-state derivation

- **Swiss rounds** = rounds whose pairings all have `eliminationGame == false`.
- **Not started**: no rounds → "Tournament has not started yet."
- **Round complete**: every non-bye pairing has all results reported (single-sided: both combined scores; double-sided: both games). *Assumption (TBD, verify with live snapshots): unreported scores are `null`.*
- **Latest Swiss round** = last Swiss round in the array (complete or not).
- **Standings "after round N"**: N = number of the last complete Swiss round; if N = 0 → "No completed rounds yet", followed by the player list in Cobra's `rank` order. Cobra's `rank` is used as-is. *TBD: confirm `rank` reflects only completed rounds.*
- **Top cut present**: default `pairings` shows the latest Swiss round with the note "Top cut in progress — not supported yet"; `round` pointing at an elimination round → "Top cut is not supported yet."; `player` adds the same note.

## 6. Tournament reference parsing

| Input | Result |
|-------|--------|
| `4909` | ID 4909 |
| `https://tournaments.nullsignal.games/tournaments/4977/players/standings` | ID 4977 |
| Shortcode, e.g. `HBYM` | FR-12 (Should): resolved via Cobra if T01 finds a reliable method; otherwise "Invalid tournament reference" |
| Other hosts, other input | "Invalid tournament reference" |

## 7. Cache (S3)

- Bucket created by the SAM template; private; lifecycle rule deletes objects after 1 day.
- `cache/{id}.json` — raw Cobra JSON; object metadata `fetched-at` (UTC epoch).
- `codes/{CODE}.json` — shortcode → tournament ID, written whenever a shortcode resolves to `/tournaments/{id}`. Codes never change, so there is no TTL; the object expires with the bucket's 1-day lifecycle rule and is refreshed on every successful resolution. When a shortcode redirects to `/` (private tournament), the Worker looks the code up here; on a hit it continues with that ID (FR-21 applies), on a miss it replies "This tournament is private."
- Fresh (age ≤ 60 s): served without contacting Cobra.
- Expired or missing: fetch from Cobra, write to S3, serve.
- Fetch failure (timeout, 5xx, connection error): serve the cached copy marked stale, any age; footer "Cobra unavailable — data from <t:UNIX:R>". No cached copy → "Cobra is unavailable, try again later."
- 404 from Cobra → "Tournament not found." (not cached).
- 401 from Cobra (private tournament, see `docs/findings.md` Q5; FR-21): the cache is not overwritten. Serve the cached copy marked stale, any age (up to the 1-day bucket lifecycle); footer "Tournament is now private — data from <t:UNIX:R>". No cached copy → "This tournament is private."
- **Single-flight (Should, NFR-03):** before fetching, the Worker creates `locks/{id}` with a conditional write (`If-None-Match: *`) containing a timestamp. The winner fetches and deletes the lock. Others wait up to 2 s polling for a fresh cache object, then serve stale data if available, else fetch themselves. A lock older than 15 s is treated as abandoned and replaced (conditional on its ETag).

## 8. Player search

- Normalisation of both name and query: Unicode NFKD, remove combining marks, `casefold()`, plus an explicit map for letters that do not decompose (`ł→l`, `ø→o`, `đ→d`, `ß→ss`, `æ→ae`, `œ→oe`).
- Substring match on normalised strings; results ordered by rank; first 3 returned plus count of the rest.

## 9. Output format

- Every message: embeds only, `allowed_mentions: {"parse": []}`; player names escaped for markdown.
- First embed title: tournament name. First description line: e.g. "Round 5 pairings — in progress" or "Standings after round 8".
- Footer: "Data from <t:UNIX:R>" (+ stale notice), and a link to the tournament on Cobra.
- ID display: text before the first `:`.
- Single-sided pairing: `T3 · Alice (Corp, Nuvem SA) 3–0 Bob (Runner, Arissana)`; unreported result: `vs`; intentional draw: `ID` instead of the score; bye: `T21 · Carol — BYE`.
- Double-sided pairing (proposed, refine after fixture): `T3 · Alice 4–2 Bob` followed by both games, each in the single-sided form.
- Standings line: `1. Alice — 22 pts — SoS 1.821 — Nuvem SA / Arissana`.
- Player card: rank, points, SoS, IDs, latest Swiss round pairing or bye, top cut note if applicable.
- Chunking: embed description ≤ 4096 chars; ≤ 10 embeds and ≤ 6000 total chars per message; at most 5 messages. Lines are never split. If the content does not fit, the last line of the last message reads "…and N more — full list on Cobra" with a link. First message edits the original response; the rest are follow-ups (ephemeral for `player`).

## 10. Security

- Signature verification before any processing; reject on missing/invalid headers.
- Secrets read from SSM at cold start; cached in memory.
- IAM least privilege: InteractionsFunction — invoke WorkerFunction, read its SSM parameters. WorkerFunction — read/write/delete in the cache bucket, read its SSM parameters.
- Outbound calls limited in code to `tournaments.nullsignal.games` and `discord.com`.
- No user data persisted; cache holds only public tournament data and expires.
- Logs: command name, tournament ID, cache hit/miss/stale, durations, errors — never tokens or full payloads.

## 11. Infrastructure (AWS SAM, `eu-central-1`)

- `InteractionsFunction` + Function URL (auth NONE; protected by signature check).
- `WorkerFunction`: timeout 30 s, memory 256 MB; `EventInvokeConfig` with `MaximumRetryAttempts: 0` and `MaximumEventAgeInSeconds: 600` (interaction tokens expire after 15 min).
- `CacheBucket` (S3, private, lifecycle 1 day).
- Log groups with 14-day retention.
- SSM parameters (created manually, names passed as template parameters): `/cobra-bot/discord/public-key`, `/cobra-bot/discord/app-id`, `/cobra-bot/discord/bot-token`.
- `AWS::Budgets::Budget`: USD 5/month, email alert.

## 12. Test fixtures

- Real exports (live snapshots, finished single-sided tournaments, a double-sided tournament) are anonymised by `scripts/anonymize_fixture.py` before commit:
  - each player name (in `players` and `eliminationPlayers`) is replaced by a deterministic pseudonym (`Player0001`…);
  - player IDs are remapped consistently everywhere they appear (`players`, `rounds`, `eliminationPlayers`): new ID = 1000 + position (1-based) in the sorted original IDs; `null` (bye) stays `null`;
  - `pronouns` is set to `""`; `tournamentOrganiser.nrdbId` and `nrdbUsername` are replaced by fixed fake values;
  - the tournament `name` and `date` are replaced by fixed fake values; the shortcode in `links[rel=uploadedfrom]` is replaced by a fake one;
  - ranks, match points, SoS/eSoS, all scores, table numbers, flags, factions and identities are kept.
- Fixture files are named by content (e.g. `single_sided_top8.json`), not by Cobra tournament ID.
- Edge-case names are injected deliberately into some fixtures (e.g. `@Mention`, `*bold_name~`, `Maëlig`, `Żółw`) so tests still cover escaping and diacritics.
- Acceptance criteria refer to players by fixture player ID, not by name.

## 13. Acceptance criteria

Automated tests cover all criteria except AC-20 (manual).

| ID | Given / When / Then |
|----|---------------------|
| AC-01 | Given fixture `single_sided_top8` (8 Swiss rounds + top 8), when standings are formatted, then the header says "Standings after round 8" and the first row is player 1042 with 22 pts. |
| AC-02 | Given fixture `single_sided_top8`, when pairings for round 1 are formatted, then table 21 shows player 1023 with BYE. |
| AC-03 | Given fixture `single_sided_top8`, when pairings without a round are requested, then round 8 is shown with the note "Top cut in progress — not supported yet". |
| AC-04 | Given fixture `single_sided_top8`, when round 9 is requested, then the reply is "Top cut is not supported yet." |
| AC-05 | Given fixture `single_sided_top8`, when round 0 or 15 is requested, then the reply is a round-out-of-range error. |
| AC-06 | Given a fixture with no rounds, when pairings or standings are requested, then the reply is "Tournament has not started yet." |
| AC-07 | Given a live fixture with some unreported results in round N, then pairings say "Round N pairings — in progress" and standings say "Standings after round N−1". |
| AC-08 | Given a live fixture in round 1 with no reported results, then standings say "No completed rounds yet" and list all players in Cobra's `rank` order. |
| AC-09 | Given fixture `single_sided_top8`, when searching a substring of player 1017's name in different letter case, then exactly that player is returned with rank 2. |
| AC-10 | Given a query matching more than 3 players, then 3 are shown in rank order and "and N more" has the correct N. |
| AC-11 | Given a query matching nobody, then the reply is "No players match". |
| AC-12 | Given names `Maëlig` and `Żółw`, then queries `maelig` and `ZOLW` match them. |
| AC-13 | Given inputs `4909`, `https://tournaments.nullsignal.games/tournaments/4977/players/standings`, `https://example.com/tournaments/1`, `abc!`, then results are ID 4909, ID 4977, error, error. |
| AC-14 | Given fixture `large_top_cut` (235 players), when standings are chunked, then there are ≤ 5 messages, each with ≤ 10 embeds and ≤ 6000 chars, every description ≤ 4096 chars, and players appear once each in rank order. |
| AC-15 | Given a synthetic tournament with 1000 players, then exactly 5 messages are produced and the last one ends with "…and N more — full list on Cobra" with the correct N and link. |
| AC-16 | Given a fake store and clock, when the same tournament is requested twice within 60 s, then one HTTP call is made; after 61 s, a second call is made. |
| AC-17 | Given a 10-minute-old cache entry and a failing HTTP call, then data is returned marked stale with the stale notice; given no cache, "Cobra is unavailable, try again later."; given HTTP 404, "Tournament not found." |
| AC-18 | Given a held lock and a fresh cache object appearing within 2 s, then the second caller makes no HTTP call. (Should) |
| AC-19 | Given a request with an invalid signature, the handler returns 401; given a valid PING, `{"type": 1}`; given a `player` command, the deferred response has flag 64 and the Worker is invoked asynchronously. |
| AC-20 | Manual: on a test server and via user install in a DM, all three commands work against a real tournament; long standings arrive as several messages; no bot permissions were granted. |
| AC-21 | Given names `@Mention` and `*bold_name~`, then every outgoing payload has `allowed_mentions.parse == []` and names are escaped. |
| AC-22 | Given fixture `dss` (double-sided), then pairings show both games per table and round completion requires both games reported. |
| AC-23 | Given `template.yaml`, then WorkerFunction has `MaximumRetryAttempts: 0` and the cache bucket has a lifecycle rule (template test). |
| AC-24 | Given the command registration payload, then `integration_types == [0, 1]` and `contexts == [0, 1, 2]`. |
| AC-25 | Given a 10-minute-old cache entry and HTTP 401 from Cobra, then the cached data is returned marked stale with the note "Tournament is now private — data from <t:UNIX:R>" and the cache entry is unchanged; given no cache and HTTP 401, the reply is "This tournament is private." |

## 14. Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Cobra JSON is not an official API and may change | Bot breaks | Tolerant parser; fixture tests; contact NSG after MVP. |
| NSG does not agree to the bot | Project stops or changes | Show MVP early; shared cache and User-Agent minimise load. |
| Live-round or double-sided JSON differs from assumptions | Wrong labels or crashes | T01 snapshots before implementing `rounds.py`. |
| Thundering herd on cache expiry | Burst of requests to Cobra | Single-flight lock (Should); accepted small herd until then. |
| Discord rate limits on follow-ups | Missing messages | 5-message cap; respect `Retry-After`. |
| User install exposes the bot to many contexts | More traffic | Shared cache; budget alarm; rate limiting as follow-up if needed. |
| Cold starts | Slower first reply | Small package; deferred ack keeps within 3 s. |

## 15. Open questions

1. Unreported results in live JSON — `null`, missing, or 0? (T01)
2. Does `rank` in a live export reflect only completed rounds? (T01)
3. Double-sided JSON structure. (T01)
4. Shortcode → ID resolution method and shortcode format. (T01)
5. Response for unpublished/private tournaments (404, 403, other)? (T01)
6. ~~Exact Python version supported by Lambda at implementation time.~~ Resolved: Python 3.14 (§3).
7. Response-time target (NFR-05) and expected load.
