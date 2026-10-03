# Requirements — Cobra Discord Bot

Status: Draft v0.2 · 2026-10-01

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

| ID | Priority | Requirement |
|----|----------|-------------|
| FR-01 | Must | Slash command `/cobra pairings <tournament> [round]` posts pairings publicly in the channel. |
| FR-02 | Must | Without `round`, pairings are shown for the latest Swiss round. With `round`, for that Swiss round. If a top cut is in progress, the latest Swiss round is shown with the note "Top cut in progress — not supported yet". |
| FR-03 | Must | Pairings output states which round it shows and whether that round is in progress or complete. |
| FR-04 | Must | Each pairing shows: table number, both player names, roles and identities (IDs), and results if reported. Byes and intentional draws are shown explicitly. |
| FR-05 | Must | Both single-sided Swiss (one game per round) and double-sided Swiss (two games per round) are supported. |
| FR-06 | Must | Slash command `/cobra standings <tournament>` posts standings publicly, stating after which round they apply. If no round is complete yet, it says "No completed rounds yet" and lists the players in the order Cobra gives them (`rank`). |
| FR-07 | Must | Each standings row shows: rank, player name, match points, Strength of Schedule (SoS), Corp ID and Runner ID. |
| FR-08 | Must | IDs are displayed in short form: the text before the first `:`, mapped to a short name of at most 9 columns (e.g. "Nuvem SA: Law of the Land" → "Nuvem", "Haas-Bioroid: Precision Design" → "HB"), with a fallback for IDs missing from the map (SPEC §9; `docs/embeded_format.md` A-1–A-4). The standings and pairings images have room for more and show the text before the `:` (cut at 24 characters). |
| FR-09 | Must | Slash command `/cobra player <tournament> <query>` replies publicly (changed from ephemeral on 2026-10-03, so a group can follow its players together). `query` may list up to 10 names separated by commas, e.g. `Alice, Bob, Carol`; each is searched on its own and every matching player gets a card, once, in rank order. Matching is a substring match that ignores letter case and diacritics (e.g. `maelig` matches "Maëlig", `zolw` matches "Żółw"). |
| FR-10 | Must | Player search returns up to 3 matches, ordered by rank; if more exist, it says how many more matched. Each match shows rank, points, SoS, IDs and the player's pairing in the latest Swiss round (table, opponent, role, result) or bye. If a top cut is in progress, the reply notes that top cut pairings are not supported yet. |
| FR-11 | Must | `<tournament>` accepts a numeric ID or a Cobra URL (any page under `/tournaments/{id}/…`). |
| FR-12 | Should | `<tournament>` also accepts a shortcode (e.g. `HBYM`), if Cobra offers a reliable way to resolve it (see T01). |
| FR-13 | Must | If the tournament has not started (no rounds), the bot says so; standings instead list the registered players, if there are any, as Cobra does (SPEC AC-26). |
| FR-14 | Must | Output uses Discord embeds; standings, pairings and player search show their table as an image in the embed (decided 2026-10-03, SPEC §9). Long output is split across up to 5 messages (images: up to 5 pages, all in one message); if it does not fit, the last message (page) says how many entries were omitted and links to the full page on Cobra. |
| FR-15 | Must | If Cobra is unavailable, the bot shows the last cached data with a note stating when it was fetched. If no cached data exists, it shows an error. |
| FR-16 | Must | Clear user-facing errors for: invalid tournament reference, tournament not found, tournament private (without cache), round out of range, Cobra unavailable without cache. |
| FR-17 | Must | All bot responses are in English. |
| FR-18 | Must | Commands work in servers where the bot is installed, and — for users who installed the bot on their account — in any server, DM or group DM. |
| FR-19 | Could | Top cut (elimination) pairings, bracket and final ranking. In MVP, a request for an elimination round returns "Top cut is not supported yet". |
| FR-20 | Could | Extended SoS (eSoS) column in standings. |
| FR-21 | Must | Organisers can switch a tournament between public and private while it runs. If Cobra reports the tournament as private and cached data exists, the bot shows the cached data with a note that the tournament is now private and when the data was fetched. Without cached data, it says the tournament is private. |

## 5. Non-functional requirements

| ID | Priority | Requirement |
|----|----------|-------------|
| NFR-01 | Must | Anyone who can use application commands can use all bot commands; no role restrictions. |
| NFR-02 | Must | Tournament data is cached in a shared cache (Amazon S3) for at most 60 seconds; all bot instances use the same cache. |
| NFR-03 | Should | Concurrent cache misses for the same tournament result in a single fetch from Cobra (single-flight). |
| NFR-04 | Must | Every interaction is acknowledged within Discord's 3-second limit. |
| NFR-05 | Should | Final response delivered within TBD seconds (p95, warm instance). |
| NFR-06 | Must | A command never produces duplicate messages (no automatic retries of partially completed work). |
| NFR-07 | Must | Discord request signatures (Ed25519) are verified; invalid requests are rejected with HTTP 401. |
| NFR-08 | Must | The bot token is used only by the local command registration script, from environment variables; it is never stored in AWS, the repository or logs. Deployed configuration (Discord public key, resource names) comes from template parameters as environment variables; nothing account- or bot-specific is hard-coded, so several bots or AWS accounts can run the same code. |
| NFR-09 | Must | No persistent storage of user data. Only a cache of public tournament data, expiring automatically. |
| NFR-10 | Must | Bot messages never trigger mentions (`allowed_mentions` empty); player names cannot inject markup: they are shown inside code blocks they cannot close, and user text outside code blocks is escaped for Discord markdown. |
| NFR-11 | Must | Test fixtures derived from real tournaments are anonymised before being committed. |
| NFR-12 | Must | Logs go to CloudWatch with 14-day retention; full Cobra payloads are not logged. |
| NFR-13 | Must | AWS budget alarm at USD 5/month. |
| NFR-14 | Must | Infrastructure defined with AWS SAM in region `eu-central-1`; deployment is manual (`sam deploy`). |
| NFR-15 | Must | GitHub Actions runs lint, type-check and tests on every push and pull request. |
| NFR-16 | Must | Requests to Cobra use an identifying User-Agent, an 8-second timeout, and no aggressive retries. |
| NFR-17 | Should | Running cost stays within the AWS free tier at expected load (load TBD). |
| NFR-18 | Could | Logs archived to S3. |

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

- Shape of Cobra JSON while a round is in progress (verify during the World Championship weekend, task T01).
- Whether shortcodes can be resolved to IDs.
- Response-time target, expected load.
- NSG consent — to be requested after showing the MVP.
