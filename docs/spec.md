# Specification — Cobra Discord Bot

Status: Draft v0.3 · 2026-10-01 · Requirements: see `requirements.md`

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
| `/cobra player` | `tournament` (string, required), `query` (string, required, 1–200 chars; up to 10 names separated by `,` or `;`) | Public |

Registered globally by a script: `integration_types: [0, 1]` (guild, user), `contexts: [0, 1, 2]` (guild, bot DM, private channel).

## 3. Components

| Module | Responsibility |
|--------|----------------|
| `handlers/interactions.py` | Lambda entry point: signature check, PING, deferred response (public for every command), async invoke of Worker. |
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

Libraries: `httpx` (HTTP), `PyNaCl` (Ed25519), `Pillow` (reply images, Worker only), `boto3` (provided by Lambda runtime; S3, Lambda invoke). Tests use an in-memory `CacheStore` fake — no AWS mocking library.

## 4. Data model

Source: Cobra export `GET https://tournaments.nullsignal.games/tournaments/{id}.json` (schema link inside the export: `/schemas/tournament-schema.json`).

```python
@dataclass(frozen=True)
class Player:
    id: int
    name: str
    rank: int
    match_points: int
    sos: Decimal                 # "strengthOfSchedule": a string or a number
    esos: Decimal
    corp_faction: str | None
    corp_identity: str | None
    runner_faction: str | None
    runner_identity: str | None

@dataclass(frozen=True)
class Seat:
    player_id: int | None        # None = bye (either seat)
    role: Literal["corp", "runner"] | None   # None in byes and double-sided pairings
    combined_score: int | None   # None = not reported
    corp_score: int | None       # double-sided: the player's result as Corp
    runner_score: int | None     # double-sided: the player's result as Runner
    winner: bool | None          # elimination games only

@dataclass(frozen=True)
class Pairing:
    table: int
    seat1: Seat
    seat2: Seat
    intentional_draw: bool
    two_for_one: bool
    elimination: bool
    # derived: is_bye (either seat has no player), double_sided (not a bye, not
    # elimination, no roles), player_ids

@dataclass(frozen=True)
class Tournament:
    id: int
    name: str
    date: date | None                         # None if missing or malformed
    cut_to_top: int
    preliminary_rounds: int
    players: tuple[Player, ...]
    rounds: tuple[tuple[Pairing, ...], ...]   # index 0 = round 1
    fetched_at: datetime
    stale: bool                               # served from cache after a failed fetch
```

Observed in real exports (4909, 4990 single-sided; 5018 double-sided; details in `findings.md`):
- Single-sided Swiss: each pairing has one Corp and one Runner seat; roles are always set, even before results are reported.
- Double-sided Swiss: one pairing per table and no `role` key; each seat carries the player's own Corp result (`corpScore`), Runner result (`runnerScore`) and their sum (`combinedScore`). There is no top-level double-sided flag, so a non-bye Swiss pairing without roles is double-sided.
- A bye is a pairing where **either** `player1.id` or `player2.id` is `null`; roles are `null`. The bye seat's `combinedScore` is set immediately (e.g. 6 in double-sided Swiss); the empty seat may carry `combinedScore: 0`.
- Unreported results are `null`, with the keys present.
- Elimination rounds follow Swiss rounds in the same `rounds` array, with `eliminationGame: true` and `winner` instead of scores.
- Table numbers may have gaps.
- Some numeric fields arrive as strings or as numbers (`strengthOfSchedule` is usually a string, sometimes an integer).
- The parser is tolerant: unknown keys are ignored, numbers given as strings are accepted, missing optional fields get defaults; it fails only when player IDs, ranks, tables or the overall shape are missing or malformed.

## 5. Round-state derivation

- **Swiss rounds** = rounds whose pairings all have `eliminationGame == false`.
- **Not started**: no rounds → "Tournament has not started yet."
- **Round complete**: every non-bye pairing has all results reported (single-sided: both combined scores; double-sided: both games, i.e. `corpScore` and `runnerScore` of both seats). Unreported scores are `null` (`findings.md` Q1).
- **Latest Swiss round** = last Swiss round in the array (complete or not).
- **Standings "after round N"**: N = number of the last complete Swiss round; if N = 0 → "No completed rounds yet", followed by the player list in Cobra's `rank` order. Cobra's `rank` is used as-is; it is assumed to reflect completed rounds only (author decision, `findings.md` Q2).
- **Round numbers** are 1-based positions in `rounds`; a requested round below 1 or above the number of rounds (Swiss and elimination) is out of range.
- **Top cut present**: default `pairings` shows the latest Swiss round with the note "Top cut in progress — not supported yet"; `round` pointing at an elimination round → "Top cut is not supported yet."; `player` adds the same note.

## 6. Tournament reference parsing

| Input | Result |
|-------|--------|
| `4909` (1–9 digits, > 0) | ID 4909 |
| `https://tournaments.nullsignal.games/tournaments/4977/players/standings` (any page under `/tournaments/{id}`; `http` or `https`; query and fragment ignored) | ID 4977 |
| Shortcode: 4 letters or digits, not all digits, any case, e.g. `QNSF`, `n9wi` | Shortcode `QNSF` / `N9WI` (FR-12), resolved via Cobra (below) |
| `https://tournaments.nullsignal.games/QNSF` | Shortcode `QNSF` |
| Other hosts, schemes or input | "Invalid tournament reference" |

Surrounding whitespace and Discord's `<…>` link-suppression brackets are ignored. An all-digit input is always an ID, never a shortcode.

Shortcode resolution (`findings.md` Q4): `GET /{CODE}` without following redirects. Cobra answers `302` in every case, so the `Location` header decides: `/tournaments/{id}` → that ID; `/tournaments/not_found?code=…` → "Tournament not found."; `/` → private tournament (see `codes/` in §7).

## 7. Cache (S3)

- Bucket created by the SAM template; private; lifecycle rule deletes objects after 1 day.
- `cache/{id}.json` — raw Cobra JSON; object metadata `fetched-at` (UTC epoch).
- `codes/{CODE}.json` — shortcode → tournament ID, written whenever a shortcode resolves to `/tournaments/{id}`. Codes never change, so there is no TTL; the object expires with the bucket's 1-day lifecycle rule and is refreshed on every successful resolution. When a shortcode redirects to `/` (private tournament), the Worker looks the code up here; on a hit it continues with that ID (FR-21 applies), on a miss it replies "This tournament is private."
- Fresh (age ≤ 60 s): served without contacting Cobra.
- Expired or missing: fetch from Cobra, write to S3, serve.
- Fetch failure (timeout, 5xx, connection error): serve the cached copy marked stale, any age; notice "Cobra unavailable — data from <t:UNIX:R>" (§9). No cached copy → "Cobra is unavailable, try again later."
- Non-existent tournament: Cobra answers `302` to `/error`, not 404 (`findings.md` Q5). The JSON is fetched without following redirects; a redirect to `/error`, or a 404, → "Tournament not found." (not cached). Any other unexpected status or a non-JSON body counts as a fetch failure.
- 401 from Cobra (private tournament, see `docs/findings.md` Q5; FR-21): the cache is not overwritten. Serve the cached copy marked stale, any age (up to the 1-day bucket lifecycle); notice "Tournament is now private — data from <t:UNIX:R>" (§9). No cached copy → "This tournament is private."
- **Single-flight (Should, NFR-03):** before fetching, the Worker creates `locks/{id}` with a conditional write (`If-None-Match: *`) containing a timestamp. The winner fetches and deletes the lock. Others wait up to 2 s polling for a fresh cache object, then serve stale data if available, else fetch themselves. A lock older than 15 s is treated as abandoned and replaced (conditional on its ETag).

## 8. Player search

- Normalisation of both name and query: Unicode NFKD, remove combining marks, `casefold()`, plus an explicit map for letters that do not decompose (`ł→l`, `ø→o`, `đ→d`, `ß→ss`, `æ→ae`, `œ→oe`).
- Substring match on normalised strings; results ordered by rank; first 3 returned plus count of the rest.

## 9. Output format

- Every message: one embed, `allowed_mentions: {"parse": []}`, colour `0xE0B23A` (also on one-sentence replies such as errors, which have no code block). The detailed design requirements are in `docs/embeded_format.md`.
- **Standings and pairings are images** (decided 2026-10-03, replacing the code-block tables below for these two commands; `docs/embeded_format.md` §7). The table is drawn as a PNG (`formatting/image.py`, Pillow) and shown in the embed (`image: attachment://standings-1.png`), so colours and columns look the same on desktop and mobile. Columns have headings. Standings: `#`, Player, Corp, Runner, Pts, SoS (IDs before points), a background stripe per group of players on equal points. Pairings, single-sided: Table, Player, Side, ID, Pts, two rows per table with the Corp first; double-sided: Table, Player, Game 1 (side tag, ID, points), Game 2, Total, seat 1 first. Winners bold, losers secondary, as in the code-block tables. IDs are the text before the `:` (not the 9-column short names), names and IDs cut at 28 and 24 characters with `…`, made safe as in code blocks. Colours on Discord's dark background: points yellow `#f0b232`, Corp blue `#7998ec` and Runner red `#dd4847` (the NSG card-back colours, the blue lightened to be readable), secondary `#949ba4`. Text is drawn in the bundled Noto Sans (SIL OFL, `src/cobra_bot/fonts/`), since Lambda has no system fonts. A page holds at most 40 rows, one message per page: the first embed has the title, link and header; every embed has the legend ("Round 8 · 46 players", "Round 8 · 23 tables") and "N / M" when there are several pages. Pages after the fifth are dropped and the last message's description ends with "…and N more — [full list on Cobra](url)" (N players, or N tables). The text in an image cannot be selected or searched.
- Player cards (`/cobra player`) stay as text: the table sits in ```` ```ansi ```` code blocks, so columns line up and Discord renders colours on desktop in its own fixed palette (mobile shows them uncoloured). Columns are aligned by display width: combining marks take no column, wide characters (CJK, most emoji) two, everything else one. Inside a code block markdown and mentions do not render, so player names and identities are not escaped; instead backticks become `'` so a name cannot close the block, control and format characters (e.g. ESC) are dropped, whitespace runs collapse to one space, and text is NFC-normalised. User text outside code blocks (the search query) is escaped for Discord markdown: a backslash goes before each of `` \ * _ ~ ` | > # - [ ] ( ) < : ``; whitespace runs, including newlines, collapse to one space.
- First embed: title = tournament name (plain text; Discord does not render markdown in titles), title link = the tournament on Cobra (standings: its standings page). Only the first message has a title. The bot's name comes from the Discord application (interaction responses cannot override it).
- Header (description lines above the table): the state line in bold, e.g. "**Round 5 pairings — in progress**", "**Standings after round 8**", "**No completed rounds yet**" (round 1 under way) or "**Registered players — not started yet**" (players registered, no round paired; AC-26); the top-cut note as subtext (`-# Top cut in progress — not supported yet`) if applicable; then "Data from <t:UNIX:R>", or the stale notice instead ("Cobra unavailable — data from …" / "Tournament is now private — data from …"). This sits in the description, not the embed footer, because footers do not render Discord timestamps.
- Footer (every message): a legend. For the images it is the short legend above. Code-block tables (player cards; the formatters keep the standings and pairings variants too) — standings: "Round 8 · 46 players · Corp + SoS on line 2, Runner on line 3" (no round part when no round is complete). Pairings: "Round 8 · 23 tables · Corp first · number = points scored", or for a double-sided round "Round 3 · 16 tables · double-sided · columns = game 1 | game 2". Player cards: "Corp + SoS on line 2, Runner on line 3 · pairing: Corp first · number = points scored".
- ID display (FR-08): the text before the first `:`, looked up in `src/cobra_bot/formatting/identities.py` (separate Corp and Runner maps, values at most 9 columns). An ID missing from the map falls back to — Corp: the text before the `:`; Runner: a quoted nickname if there is one (`Kim "Ghost" Lee` → `Ghost`), otherwise the first word — cut to 9 columns with `…`, and a warning is logged once per ID and process. A missing identity shows `—` in the secondary colour. Player names longer than 15 columns are cut to 14 columns plus `…`.
- Width: every table line is at most 22 display columns in standings and 34 in pairings (measured without ANSI codes), so the same layout fits phones; no information depends on colour alone (mobile clients drop it).
- ANSI colours (`docs/embeded_format.md` §1.1, A-0): primary text, the default colour (`0`), for ranks, table labels and players without a decided result (equal points, ID, unreported, bye); standings names and winners bold in the default colour (`0` then `1`, since `1` keeps the previous colour); secondary (`0;37`, which Discord renders dimmer than default text) for SoS, losers, the `·` separator and an unknown ID; points bold yellow (`1;33`); Corp IDs and the `C` tag blue (`0;34`); Runner IDs and the `R` tag magenta (`0;35`). Every line ends with `0`. Code `30` is never used: Discord dark themes render it black on the code-block background. Discord renders these codes in its own fixed palette, which differs between themes.
- Standings table: no column header; three lines per player. Line 1: rank right-aligned in 2, `. `, name padded to 15, points right-aligned in 3 (` 1. Alice           22`). Line 2: the indent (rank width + 2), the short Corp ID, and SoS with three decimals right-aligned to end under the points (`    Nuvem        1.821`). Line 3: the indent and the short Runner ID (`    Arissana`). From rank 100 the rank column is 3 wide for the whole table and the name column gives up that column (names cut at 14), so lines stay within 22. A blank line separates groups of players on the same points.
- Pairings table: no column header; a blank line between tables; tables in table order. Single-sided, two lines per table, the Corp first whatever the seat order: the table label padded to 4 (wider from table 100; following lines indented to match), the points that player scored right-aligned in 2, a space, the player, ` · ` and the short ID (`T1   3 Alice · Nuvem` / `     0 Bob · Zahya`). Unreported points show `–`, an intentional draw `ID` for both players. The player with more points is bold, the one with fewer secondary. Bye: one line with no ID, `T21 BYE Carol`.
- Double-sided pairing: four lines. Seat 1 (the Corp in game 1, findings Q3) and seat 2 each get a name line with the round total (the sum of both games; `–` while neither is reported) and a game line: six spaces, then a cell per game — tag `C`/`R`, a space, the short ID padded to 10, the points of that game — separated by two spaces. Seat 1 reads `C … R …`, seat 2 `R … C …`, so the left column is game 1 and the right column game 2 (`      C Nuvem     0  R Arissana  3`).
- Player card: the player's standings unit (three lines), then a secondary `Round N` line and the player's table in the latest Swiss round (in the pairing format above, including a bye), or `Round N: not paired`. Cards are separated by a blank line; no column headings. Header "**Players matching “query”**" plus the top-cut note if applicable; "…and N more matched" follows the table; no match → "No players match." and no table.
- Round out of range: "Round N does not exist. This tournament has rounds 1–M." All user-facing text lives in `messages.py`.
- Chunking (code-block replies, i.e. player cards): one embed per message; the table fills the description (≤ 4096 chars), then fields (value ≤ 1024 chars, name a zero-width space, at most 25), each part with its own complete code block; ≤ 6000 chars per message counting title, description, field names and values, and footer; at most 5 messages. Entries are never split (a double-sided pairing or a player card is one entry), and a part never starts with a blank line. If the content does not fit, the longest prefix of entries is kept and the last line of the last message, below the table, reads "…and N more — [full list on Cobra](url)". First message edits the original response; the rest are follow-ups (ephemeral for `player`).

## 10. Security

- Signature verification before any processing; reject on missing/invalid headers.
- Configuration comes from environment variables set by template parameters, read once per cold start: InteractionsFunction — `DISCORD_PUBLIC_KEY` (hex; not a secret, it only verifies signatures) and `WORKER_FUNCTION_NAME`; WorkerFunction — `CACHE_BUCKET`. Missing, blank or invalid values fail at startup. Nothing account- or bot-specific is hard-coded.
- The bot token is never deployed: only `scripts/register_commands.py` uses it, locally, from `DISCORD_BOT_TOKEN` (with `DISCORD_APPLICATION_ID`). The functions need no secrets: the application ID arrives with each interaction and replies use the interaction token.
- IAM least privilege: InteractionsFunction — invoke WorkerFunction. WorkerFunction — read/write/delete objects in the cache bucket (and list it, so a missing key is a 404, not a 403). No SSM access.
- Outbound calls limited in code to `tournaments.nullsignal.games` and `discord.com`.
- No user data persisted; cache holds only public tournament data and expires.
- Logs: command name, tournament ID, cache hit/miss/stale, durations, errors — never tokens or full payloads.

## 11. Infrastructure (AWS SAM, `eu-central-1`)

- `InteractionsFunction` + Function URL (auth NONE; protected by signature check).
- `WorkerFunction`: timeout 30 s, memory 256 MB; `EventInvokeConfig` with `MaximumRetryAttempts: 0` and `MaximumEventAgeInSeconds: 600` (interaction tokens expire after 15 min).
- `CacheBucket` (S3, private, lifecycle 1 day).
- Log groups with 14-day retention.
- Template parameter `DiscordPublicKey` → `DISCORD_PUBLIC_KEY` on InteractionsFunction. No SSM parameters.
- `AWS::Budgets::Budget`: USD 5/month, email alert.
- Implementation (`template.yaml`): `python3.14` on x86_64; WorkerFunction 256 MB; InteractionsFunction 512 MB and timeout 10 s (at 256 MB a cold start took ~2.8 s, too close to Discord's 3 s limit; NFR-04); the bucket blocks public access, enforces bucket-owner object ownership and SSE-S3 encryption, and also aborts incomplete multipart uploads after 1 day; each function logs to its own log group through `LoggingConfig`; the budget alerts by email on actual and forecasted cost above 100 % (it covers the whole account, not just this stack); output `InteractionsEndpointUrl` is the Function URL for the Developer Portal. `samconfig.toml` pins the region.

## 12. Test fixtures

- Real exports (live snapshots, finished single-sided tournaments, a double-sided tournament) are anonymised by `scripts/anonymize_fixture.py` before commit:
  - each player name (in `players` and `eliminationPlayers`) is replaced by a deterministic pseudonym (`Player0001`…);
  - player IDs are remapped consistently everywhere they appear (`players`, `rounds`, `eliminationPlayers`): new ID = 1000 + position (1-based) in the sorted original IDs; `null` (bye) stays `null`;
  - `pronouns` is set to `""`; `tournamentOrganiser.nrdbId` and `nrdbUsername` are replaced by fixed fake values;
  - the tournament `name` and `date` are replaced by fixed fake values; the shortcode in `links[rel=uploadedfrom]` is replaced by a fake one;
  - ranks, match points, SoS/eSoS, all scores, table numbers, flags, factions and identities are kept;
  - only known keys are accepted: an unknown key anywhere in the export aborts the run, so a new Cobra field cannot reach a committed fixture without review.
- Fixture files are named by content, not by Cobra tournament ID: `single_sided_top8` (4909), `large_top_cut` (4990), `dss` (5018, live double-sided), `not_started` (5125, empty export). A test checks that every committed fixture looks anonymised.
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
| AC-06 | Given a fixture with no rounds, when pairings are requested, then the reply is "Tournament has not started yet."; the same for standings when there are no players either (with players, AC-26). |
| AC-07 | Given a live fixture with some unreported results in round N, then pairings say "Round N pairings — in progress" and standings say "Standings after round N−1". |
| AC-08 | Given a live fixture in round 1 with no reported results, then standings say "No completed rounds yet" and list all players in Cobra's `rank` order. |
| AC-09 | Given fixture `single_sided_top8`, when searching a substring of player 1017's name in different letter case, then exactly that player is returned with rank 2. |
| AC-10 | Given a query matching more than 3 players, then 3 are shown in rank order and "and N more" has the correct N. |
| AC-11 | Given a query matching nobody, then the reply is "No players match". |
| AC-12 | Given names `Maëlig` and `Żółw`, then queries `maelig` and `ZOLW` match them. |
| AC-13 | Given inputs `4909`, `https://tournaments.nullsignal.games/tournaments/4977/players/standings`, `https://example.com/tournaments/1`, `abc!`, then results are ID 4909, ID 4977, error, error. |
| AC-14 | Given fixture `large_top_cut` (235 players), when standings are rendered, then there are ≤ 5 messages, each one embed with one PNG under Discord's 10 MB attachment limit, the players shown appear once each in rank order, and the last message says how many are missing. The code-block chunker keeps its own check: ≤ 5 messages, each with ≤ 10 embeds and ≤ 6000 chars, every description ≤ 4096 chars. |
| AC-15 | Given more players (or tables) than 5 pages hold, then exactly 5 messages are produced and the last one ends with "…and N more — full list on Cobra" with the correct N and link (images: tested with a lowered page size; code-block chunker: a synthetic tournament with 1000 players). |
| AC-16 | Given a fake store and clock, when the same tournament is requested twice within 60 s, then one HTTP call is made; after 61 s, a second call is made. |
| AC-17 | Given a 10-minute-old cache entry and a failing HTTP call, then data is returned marked stale with the stale notice; given no cache, "Cobra is unavailable, try again later."; given HTTP 404, "Tournament not found." |
| AC-18 | Given a held lock and a fresh cache object appearing within 2 s, then the second caller makes no HTTP call. (Should) |
| AC-19 | Given a request with an invalid signature, the handler returns 401; given a valid PING, `{"type": 1}`; given a `player` command, the deferred response is public (no flags) and the Worker is invoked asynchronously. |
| AC-20 | Manual: on a test server and via user install in a DM, all three commands work against a real tournament; long standings arrive as several messages; no bot permissions were granted. |
| AC-21 | Given names `@Mention`, `*bold_name~` and one with backticks, then every outgoing payload has `allowed_mentions.parse == []`, names appear literally inside code blocks, and no name closes a code block. In images names are drawn, never sent as message text. |
| AC-22 | Given fixture `dss` (double-sided), then pairings show both games per table and round completion requires both games reported. |
| AC-23 | Given `template.yaml`, then WorkerFunction has `MaximumRetryAttempts: 0` and the cache bucket has a lifecycle rule (template test). |
| AC-24 | Given the command registration payload, then `integration_types == [0, 1]` and `contexts == [0, 1, 2]`. |
| AC-26 | Given an export with registered players and no rounds (World Championship 2026 before round 1), when standings are requested, then the header is "Registered players — not started yet" and every player is listed, ranked 1 to N in Cobra's order: by name with only letters and digits counted, ignoring case and diacritics (`M.G.K.` between `metronome` and `Michael kwan`), not by the export's `rank`. |
| AC-27 | Given `query` "Alice, zed, ali" where `ali` also matches Alice, then each matching player gets one card in rank order, a note says "No players match “zed”.", and a name matching more than 3 players notes "…and N more matched “name”"; past 10 names, "Only the first 10 names were searched (N more given)." |
| AC-25 | Given a 10-minute-old cache entry and HTTP 401 from Cobra, then the cached data is returned marked stale with the note "Tournament is now private — data from <t:UNIX:R>" and the cache entry is unchanged; given no cache and HTTP 401, the reply is "This tournament is private." |

## 14. Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Cobra JSON is not an official API and may change | Bot breaks | Tolerant parser; fixture tests; contact NSG after MVP. |
| NSG does not agree to the bot | Project stops or changes | Show MVP early; shared cache and User-Agent minimise load. |
| Live-round or double-sided JSON differs from assumptions | Wrong labels or crashes | T01 snapshots (`findings.md`); tolerant parser; real fixtures for live and double-sided rounds. |
| Thundering herd on cache expiry | Burst of requests to Cobra | Single-flight lock (Should); accepted small herd until then. |
| Discord rate limits on follow-ups | Missing messages | 5-message cap; respect `Retry-After`. |
| User install exposes the bot to many contexts | More traffic | Shared cache; budget alarm; rate limiting as follow-up if needed. |
| Cold starts | Slower first reply | Small package; deferred ack keeps within 3 s. |

## 15. Open questions

1. ~~Unreported results in live JSON — `null`, missing, or 0?~~ Resolved: `null`, keys present (§4).
2. ~~Does `rank` in a live export reflect only completed rounds?~~ Assumed yes (author decision; §5).
3. ~~Double-sided JSON structure.~~ Resolved (§4).
4. ~~Shortcode → ID resolution method and shortcode format.~~ Resolved (§6).
5. ~~Response for unpublished/private tournaments?~~ Resolved: private → 401; non-existent → 302 to `/error` (§7).
6. ~~Exact Python version supported by Lambda at implementation time.~~ Resolved: Python 3.14 (§3).
7. Response-time target (NFR-05) and expected load.
