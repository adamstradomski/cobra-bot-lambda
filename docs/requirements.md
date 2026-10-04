# Requirements — Cobra Discord Bot

Status: Draft v0.4 · 2026-10-04

## 1. Purpose

Netrunner players, organisers and spectators coordinate tournaments on many different Discord servers. Checking pairings and standings means leaving Discord for Cobra (https://tournaments.nullsignal.games/), and during large events many simultaneous visits can make Cobra slow or unresponsive.

The bot lets anyone read pairings and standings of a Cobra tournament directly in Discord, and reduces load on Cobra by serving tournament data from a shared cache.

## 2. Users

- **Tournament organisers (TOs)** — install the bot and share pairings/standings with players.
- **Players** — check their pairing and position.
- **Spectators / community** — follow the tournament.

The bot is public. It can be added to any Discord server (server install) and by any user to their own account (user install).

## 3. Priority legend

- **Must** — required for MVP.
- **Should** — desirable in MVP if cheap; otherwise first follow-up.
- **Could** — later, after MVP.
- **Out of scope** — not planned for this specification.

## 4. Functional requirements

**Status**: `Implemented`, `Partly`, `Not implemented`, `Manual` (checked by hand or review, no automated test) or `TBD`. Tests name the requirements they cover with `@pytest.mark.req("FR-xx")`; `tests/test_traceability.py` fails when an `Implemented` or `Partly` requirement has no test, or an exempt one has a test.

| ID | Priority | Requirement | Status |
|----|----------|-------------|--------|
| FR-01 | Must | Slash command `/cobra pairings <tournament> [round]` posts pairings publicly in the channel. | Implemented |
| FR-02 | Must | Without `round`, pairings are shown for the latest round, Swiss or top cut (changed 2026-10-04: the latest round always). With `round`, for that round; rounds are numbered by their position in Cobra's export, Swiss rounds first, then the top-cut rounds. A top-cut round is headed "Top cut round N pairings" and shows game numbers and the winner (`W`/`L`) instead of tables and points. | Implemented |
| FR-03 | Must | Pairings output states which round it shows and whether that round is in progress or complete. | Implemented |
| FR-04 | Must | Each pairing shows: table number, both player names, roles and identities (IDs), and results if reported. Byes and intentional draws are shown explicitly. | Implemented |
| FR-05 | Must | Both single-sided Swiss (one game per round) and double-sided Swiss (two games per round) are supported. | Implemented |
| FR-06 | Must | Slash command `/cobra standings <tournament>` posts the Swiss standings publicly, stating after which round they apply. If no round is complete yet, it says "No completed rounds yet" and lists the players in the order Cobra gives them (`rank`). Once Swiss is over (every Swiss round so far complete and counted, or a cut made), a note gives the top cut's state: none on Cobra yet, announced but not started, in progress, or finished (FR-22). | Implemented |
| FR-07 | Must | Each standings row shows: rank, player name, match points, Strength of Schedule (SoS), Corp ID and Runner ID. | Implemented |
| FR-08 | Must | IDs are displayed in short form: every ID is mapped by its full name to a short name of at most 9 columns, made from the text before the first `:` (e.g. "Nuvem SA: Law of the Land" → "Nuvem"). Where several IDs share that text (Haas-Bioroid, Jinteki, NBN, Weyland Consortium), each ID has its own short name: the faction and the ID's initials (e.g. "Haas-Bioroid: Precision Design" → "HB PD", "NBN: Reality Plus" → "NBN R+"; changed 2026-10-04). There is a fallback for IDs missing from the map (the short name of the text before `:`, e.g. "HB") (SPEC §9; `docs/embeded_format.md` A-1–A-4). The images use the same short names. | Implemented |
| FR-09 | Must | Slash command `/cobra player <tournament> <query>` replies publicly (changed from ephemeral on 2026-10-03, so a group can follow its players together). `query` may list up to 10 names separated by commas, e.g. `Alice, Bob, Carol`; each is searched on its own and every matching player gets a card, once, in rank order. Matching is a substring match that ignores letter case and diacritics (e.g. `maelig` matches "Maëlig", `zolw` matches "Żółw"). | Implemented |
| FR-10 | Must | Player search returns up to 3 matches, ordered by rank; if more exist, it says how many more matched. Each match shows rank, points, SoS, IDs and the player's pairing in the latest round, Swiss or top cut (table or game, opponent, role, result) or bye. | Implemented |
| FR-11 | Must | `<tournament>` accepts a numeric ID or a Cobra URL (any page under `/tournaments/{id}/…`). | Implemented |
| FR-12 | Should | `<tournament>` also accepts a shortcode (e.g. `HBYM`), if Cobra offers a reliable way to resolve it (see T01). | Implemented |
| FR-13 | Must | If the tournament has not started (no rounds), the bot says so; standings instead list the registered players, if there are any, as Cobra does (SPEC AC-26). | Implemented |
| FR-14 | Must | Output uses Discord embeds; standings, pairings and player search show their table as an image in the embed (decided 2026-10-03, SPEC §9). Long output is split across up to 5 messages (images: up to 5 pages, all in one message); if it does not fit, the last message (page) says how many entries were omitted and links to the full page on Cobra. | Implemented |
| FR-15 | Must | If Cobra is unavailable, the bot shows the last cached data with a note stating when it was fetched. If no cached data exists, it shows an error. | Implemented |
| FR-16 | Must | Clear user-facing errors for: invalid tournament reference, tournament not found, tournament private (without cache), round out of range, Cobra unavailable without cache. | Implemented |
| FR-17 | Must | All bot responses are in English. | Manual |
| FR-18 | Must | Commands work in servers where the bot is installed, and — for users who installed the bot on their account — in any server, DM or group DM. | Implemented |
| FR-19 | Must | Top cut (elimination) pairings (FR-02), bracket (FR-24) and ranking (FR-23). Added 2026-10-04, replacing the MVP reply "Top cut is not supported yet". | Implemented |
| FR-20 | Could | Extended SoS (eSoS) column in standings. | Not implemented |
| FR-22 | Must | The top cut's state is derived from Cobra's export: none (`cutToTop` 0, no elimination round), announced (`cutToTop` set, no elimination round), in progress (an elimination round), finished (Cobra has placed a player first in `eliminationPlayers`). | Implemented |
| FR-23 | Must | Slash command `/cobra top-cut <tournament>` posts the top-cut ranking publicly, like standings: place (blank while Cobra has not decided it), player, Corp and Runner ID, games won and lost in the cut, seed. Players still in the cut come first, by seed, then those out but not placed, the later out higher; players out are shown secondary. Without a cut: "This tournament has no top cut on Cobra yet." | Implemented |
| FR-24 | Must | Slash command `/cobra bracket <tournament>` posts the top-cut bracket publicly as an image laid out like Cobra's bracket page (`/tournaments/{id}/bracket`): a column per bracket round, upper bracket above lower, a box per game with its number, links to the game its winner plays next; without faction logos or pronouns, IDs as short names. Unknown players say where they come from (`Seed 3`, `Winner of 13`, `Loser of 21`). Cobra's brackets (double elimination top 4/8/16, single elimination top 2/3/4/8/16) are supported; another cut size replies "There is no bracket for a top N cut." | Implemented |
| FR-21 | Must | Organisers can switch a tournament between public and private while it runs. If Cobra reports the tournament as private and cached data exists, the bot shows the cached data with a note that the tournament is now private and when the data was fetched. Without cached data, it says the tournament is private. | Implemented |

## 5. Non-functional requirements

| ID | Priority | Requirement | Status |
|----|----------|-------------|--------|
| NFR-01 | Must | Anyone who can use application commands can use all bot commands; no role restrictions. | Implemented |
| NFR-02 | Must | Tournament data is cached in a shared cache (Amazon S3) for at most 60 seconds; all bot instances use the same cache. | Implemented |
| NFR-03 | Should | Concurrent cache misses for the same tournament result in a single fetch from Cobra (single-flight). | Implemented |
| NFR-04 | Must | Every interaction is acknowledged within Discord's 3-second limit. | Implemented |
| NFR-05 | Should | Final response delivered within TBD seconds (p95, warm instance). | TBD |
| NFR-06 | Must | A command never produces duplicate messages (no automatic retries of partially completed work). | Implemented |
| NFR-07 | Must | Discord request signatures (Ed25519) are verified; invalid requests are rejected with HTTP 401. | Implemented |
| NFR-08 | Must | The bot token is used only by the local command registration script, from environment variables; it is never stored in AWS, the repository or logs. Deployed configuration (Discord public key, resource names) comes from template parameters as environment variables; nothing account- or bot-specific is hard-coded, so several bots or AWS accounts can run the same code. | Implemented |
| NFR-09 | Must | No persistent storage of user data. Only a cache of public tournament data, expiring automatically. | Implemented |
| NFR-10 | Must | Bot messages never trigger mentions (`allowed_mentions` empty); player names cannot inject markup: they are shown inside code blocks they cannot close, and user text outside code blocks is escaped for Discord markdown. | Implemented |
| NFR-11 | Must | Test fixtures derived from real tournaments are anonymised before being committed. | Implemented |
| NFR-12 | Must | Logs go to CloudWatch with 14-day retention; full Cobra payloads are not logged. | Partly |
| NFR-13 | Must | AWS budget alarm at USD 5/month. | Implemented |
| NFR-14 | Must | Infrastructure defined with AWS SAM in region `eu-central-1`; deployed by GitHub Actions when `main` moves (`.github/workflows/deploy.yml`), or manually with `sam deploy`. | Implemented |
| NFR-15 | Must | GitHub Actions runs lint, type-check and tests on every push and pull request. | Implemented |
| NFR-16 | Must | Requests to Cobra use an identifying User-Agent, an 8-second timeout, and no aggressive retries. | Implemented |
| NFR-17 | Should | Running cost stays within the AWS free tier at expected load (load TBD). | TBD |
| NFR-18 | Could | Logs archived to S3. | Not implemented |

## 6. Constraints

- Language: Python 3.14, the latest version supported by the AWS Lambda managed runtime.
- Hosting: AWS Lambda with Discord HTTP interactions (no Gateway connection); Discord scope `applications.commands` only.
- Developed by one person with AI assistance; no deadline.
- Data source: Cobra public JSON export (`/tournaments/{id}.json`). Not an official API; no agreement with Null Signal Games (NSG) yet.

## 7. Out of scope (MVP)

- Automatic publishing of new pairings/standings to a channel (would need the `bot` scope).
- Linking a channel to a tournament (`/cobra track`) and any persistent state beyond the cache.
- Notifications to individual players; mapping Cobra players to Discord users.
- Public HTTP API for other bots.
- Text/prefix commands (e.g. `!pairings`) and a Gateway (WebSocket) connection.

## 8. Open items (TBD)

- Response-time target, expected load.
- NSG consent — to be requested after showing the MVP.
