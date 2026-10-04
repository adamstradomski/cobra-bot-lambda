# Acceptance test — AC-20 (manual)

Task T25. Run against a deployed stack (README, Deployment) and a real Cobra tournament. Fill in the result of every item: **pass**, or **fail** with a link to the issue filed for it. T25 is done when every item passes or has an issue.

## Run

| Field | Value |
|-------|-------|
| Date | |
| Tester | |
| Commit (`git rev-parse --short HEAD`) | |
| Stack name / region | / eu-central-1 |
| Test server | |
| Tournaments used (ID, shortcode) | e.g. a finished one with a top cut, a large one (> 100 players), a live one if available |

## A. Server install (test server)

| # | Check | Expected | Result |
|---|-------|----------|--------|
| A1 | Install via the Install Link, **Add to server** | Only `applications.commands` requested; no permissions; no bot member joins the server | |
| A2 | `/cobra pairings tournament:<id>` | Public reply; the latest round: "Round N pairings — …", or "Top cut round N pairings — …" with game numbers and W/L during a cut | |
| A3 | `/cobra pairings tournament:<id> round:1` | Round 1 pairings as an image with column headings, two rows per table with the Corp first and the points each player scored; byes shown as one `BYE` row | |
| A4 | `/cobra standings tournament:<large id>` | One message with several image pages (`N / M` in the footers), ranks in order; "…and N more — full list on Cobra" only if over 5 pages | |
| A5 | `/cobra player tournament:<id> query:<part of a name>` | **Everyone** in the channel sees the reply; rank, points, SoS, IDs and the latest pairing or bye | |
| A6 | `/cobra player` with a name containing diacritics, typed without them | The player is found (FR-09) | |
| A7 | Tournament given as a Cobra URL (`https://tournaments.nullsignal.games/tournaments/<id>/…`) | Same reply as with the ID | |
| A8 | Tournament given as a shortcode (e.g. `QNSF`) | Same reply as with the ID | |
| A9 | `tournament:abc!` | "Invalid tournament reference. …" | |
| A10 | `tournament:99999999` | "Tournament not found." | |
| A11 | `round:` beyond the last round | "Round N does not exist. …" | |
| A12 | `round:` pointing at a top-cut round | That bracket round's games, headed "Top cut round N pairings — …" | |
| A14 | `/cobra standings` once Swiss is over | Below the header: "No top cut on Cobra yet", "Top N cut announced — not started yet", or "Top N cut in progress/finished — see `/cobra top-cut` and `/cobra bracket`" | |
| A15 | `/cobra top-cut tournament:<id with a cut>` | Image like standings: place, player, IDs, W–L, seed; players still in bold | |
| A16 | `/cobra bracket tournament:<id with a cut>` | One image laid out like Cobra's bracket page; short IDs, no logos or pronouns | |
| A17 | `/cobra top-cut` and `/cobra bracket` for a tournament without a cut | "This tournament has no top cut on Cobra yet." | |
| A13 | The same command twice within a minute | Second reply shows the same "Data from …" time (served from the cache) | |

## B. User install

| # | Check | Expected | Result |
|---|-------|----------|--------|
| B1 | Install via the Install Link, **Add to my apps** | No permissions requested | |
| B2 | `/cobra standings` in the bot's DM | Works | |
| B3 | `/cobra pairings` in a server where the bot is **not** installed | Works, visible to the channel (FR-18) | |
| B4 | `/cobra player` in a group DM with `query:<name>, <name>` | Works for everyone in the DM; one card per named player | |

## C. Safety

| # | Check | Expected | Result |
|---|-------|----------|--------|
| C1 | Any reply with a player name containing `@`, `*`, `_` or `~` (if the tournament has one) | Shown literally; nobody is pinged; no formatting applied | |
| C2 | CloudWatch logs of both functions after the run | No interaction tokens, bot token or full Cobra/Discord payloads (NFR-12, `docs/spec/architecture.md`) | |

## Issues filed

| Item | Issue | Status |
|------|-------|--------|
| | | |
