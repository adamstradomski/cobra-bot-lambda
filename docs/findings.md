# Findings — Cobra JSON discovery (T01)

Status: in progress (top cut still to capture) · last updated 2026-10-03 (16:00Z)

This file records what the live Cobra exports actually look like. Per `CLAUDE.md`, it overrides assumptions marked TBD in `docs/spec.md`. The raw evidence lives in `snapshots/`, which is git-ignored and not anonymised. File names are given so the evidence can be re-checked locally.

## Evidence

| Source | What | Files |
|--------|------|-------|
| Tournament 5018 | Double-sided Swiss (confirmed by the author), multi-week event, 31 players, `preliminaryRounds: 3`, `cutToTop: 0`. Snapshot taken with rounds 1–2 complete and round 3 paired, with no results except the bye. | `snapshots/5018/20261001T160955Z.json` |
| Tournament 4909 | Finished single-sided Swiss: 46 players, 8 Swiss rounds and top 8 (6 elimination rounds in `rounds`). Matches AC-01 (rank 1 is 56587 with 22 pts), AC-02 (round 1, table 21 is a bye for 56479) and AC-09 (56463 has rank 2). | `snapshots/4909/20261001T174657Z.json` |
| Tournament 4990 | Finished single-sided Swiss: 235 players, 11 Swiss rounds and top cut (8 elimination rounds). 354 KB, fetched in 2.8 s. | `snapshots/4990/20261001T174658Z.json` |
| Shortcode probes | `/QNSF`, `/qnsf`, `/ZQXJ` | `snapshots/probes/20261001T1615*_{QNSF,qnsf,ZQXJ}.meta.json` |
| Non-existent ID probes | `/tournaments/99999999.json`, `/tournaments/99999999` | `snapshots/probes/20261001T174701Z_tournaments_99999999*.meta.json` |
| Tournament 5132 | World Championship 2026, live single-sided Swiss, day 1: 262 players registered before round 1, 283 once round 1 was paired, `preliminaryRounds: 3`, `cutToTop: 0` (the cut is played on day 2). Polled every 2 min from 13:17Z to 15:55Z (64 changed exports, 9 kept, listed under each finding). | `snapshots/5132/20261003T123215Z.json` (before round 1), `…T131725Z` (round 1 paired, no results), `…T134544Z` (round 1, 66/138 tables), `…T140144Z` (round 1 complete and counted), `…T140344Z` (round 2 paired), `…T143944Z` (round 2, 61/141), `…T145545Z` (round 2, 140/141), `…T145945Z` (round 3 paired, round 2 counted), `…T153345Z` (round 3, 50/141), `…T155545Z` (round 3 complete, not counted) |
| Private tournament probes | `/tournaments/5125.json`, `/tournaments/5125` while private (18:11Z) and after being made public (18:26Z) | `snapshots/probes/20261001T181141Z_tournaments_5125*.meta.json`, `snapshots/probes/20261001T182654Z_tournaments_5125*.meta.json`, `snapshots/5125/20261001T182654Z.json` |

## Open questions (SPEC §15)

### Q1 — Unreported results: `null`, missing, or 0? — **Answered: `null`, keys present**

- An unreported seat has `combinedScore`, `corpScore` and `runnerScore` all present and all `null`. All 15 non-bye tables of round 3 in 5018 look like this.
- **Exception, byes:** the bye seat already has `combinedScore` set (6 in double-sided Swiss), and `corpScore` / `runnerScore` are `null`, even while the rest of the round is unreported. Round-completion logic must skip bye pairings, which SPEC §5 already says.
- **Single-sided live exports behave the same way** (5132, 2026-10-03). An unreported seat has all three scores `null` (e.g. every table in `…T131725Z`), and the role is set from the moment the round is paired. A bye seat has `combinedScore: 3` straight away, the empty seat `id: null` and `combinedScore: 0`; both roles are `null`.
- Byes can be many and need not take the last tables: round 1 of 5132 has 7 byes, on tables 129–134 and 200, while the round's tables run up to 215 with gaps. Rounds 2 and 3 have one bye each.

### Q2 — Does `rank` in a live export reflect only completed rounds? — **Answered: only rounds the organiser has closed**

**Answer (5132, 2026-10-03):** `rank`, `matchPoints` and SoS ignore every result of the current round, however many tables have reported. They change in one step when the organiser closes the round, which can come after the last result is in. So "every result reported" does not mean "counted in the standings". *Applied in SPEC §5 (v0.4):* standings are "after round N" for the last complete round N whose points `matchPoints` already include, checked as `matchPoints` = sum of `combinedScore` over Swiss rounds 1..N for every player.

- In 64 exports across rounds 1–3, `rank`, `matchPoints` and `strengthOfSchedule` changed only twice: at `…T140144Z` (round 1's last result and the recount arrived together) and at `…T145945Z` (round 2's recount arrived with the round 3 pairings). They never changed while a round was being reported.
- **Complete but not counted:** at `…T155545Z` all 141 non-bye tables of round 3 are reported, yet `matchPoints` is still the sum over rounds 1–2 for all 283 players (only 136 match rounds 1–3). Before the fix the bot showed "Standings after round 3" there over round-2 points.
- The check holds on every other real export: 4909 matches round 8 (46/46 players, top cut excluded), 4990 round 11 (235/235), 5018 round 2 (31/31), each the last complete Swiss round. Byes count with their `combinedScore`.
- Earlier evidence (2026-10-01), still consistent: in 5018, `matchPoints` equals the sum of `combinedScore` over rounds 1–2 for every player. Player 58464's round-3 bye (already `combinedScore: 6`) is **not** included: their `matchPoints` is 0.

- In 5018, `matchPoints` equals the sum of `combinedScore` over rounds 1–2 for every player. Player 58464's round-3 bye (already `combinedScore: 6`) is **not** included: their `matchPoints` is 0.
- `rank` is unique, runs 1 to N, and matches ordering by (`matchPoints`, `strengthOfSchedule`) descending (5018; 5132 before and during round 1 and after round 3).

### Q3 — Double-sided JSON structure — **Answered (structure); edge cases open**

- **No top-level double-sided flag:** `preliminaryRounds`, `cutToTop` and the other top-level fields look the same as in single-sided exports.
- **One pairing per table, no `role` key:** each pairing has `player1` and `player2`, and there is no `role` key at all. Confirmed against 4909: single-sided seats have `id`, `role`, `corpScore`, `runnerScore` and `combinedScore`. Elimination seats have `id`, `role` and `winner`.
- **Each seat carries both games:** `corpScore` is the player's result as Corp (0 or 3), `runnerScore` their result as Runner (0 or 3), and `combinedScore` is the sum (0, 3 or 6). Example split: `p1 corp 3, runner 0, combined 3 | p2 corp 3, runner 0, combined 3`, meaning each player won their Corp game.
- **Consequences for the spec:**
  - `Seat.role` is `None` when the key is absent.
  - A pairing is double-sided when its seats have no `role` key.
  - The round is complete when every non-bye seat has non-null `corpScore` **and** `runnerScore`.
- **A bye can be in either slot.** In round 1 of 5018, `player2.id` is `null`. In round 2, **`player1.id`** is `null`. This contradicted SPEC §4 ("a bye is a pairing whose `player2.id` is `null`"); the parser checks both seats. *Applied in SPEC §4 (v0.3).*
- Table numbers 1..16 with no gaps here. A bye takes the last table.
- **Not yet observed:** draws or ties (1 point), a pair with only one of the two games reported, intentional draws, and `twoForOne` in double-sided Swiss.

### Q4 — Shortcode → ID resolution — **Answered**

- **URL:** `GET https://tournaments.nullsignal.games/{CODE}`. The code sits directly under the root, not under `/tournaments/`.
- **Known code:** `302`, `Location: https://tournaments.nullsignal.games/tournaments/{id}`, empty body, `Cache-Control: no-cache`. Example: `QNSF` → 5018.
- **Unknown code:** **also `302`**, with `Location: https://tournaments.nullsignal.games/tournaments/not_found?code={CODE}`. The status code does not distinguish success from failure, so the resolver must parse `Location`:
  - matches `/tournaments/{digits}` → that ID
  - anything else → "Tournament not found"
- **Letter case doesn't matter:** `qnsf` resolves the same as `QNSF`.
- **Format:** observed codes are `HBYM`, `BQNH`, `QNSF` and **`N9WI`**, so codes contain digits too. They are 4 characters long, but the length is not confirmed beyond that. The parser could accept `^[A-Za-z0-9]{4}$` and let Cobra decide.
  - Note that a 4-digit code would be ambiguous with a numeric tournament ID (`4909`). A purely numeric input must stay an ID.
- **Implementation:** request without following redirects (one extra request per shortcode lookup). The mapping code → ID never changes. It is cached in `codes/{CODE}.json` (SPEC §7, decided 2026-10-01), which also lets a shortcode reach the cached copy while the tournament is private.
- **Consequence:** FR-12 is feasible. Implementing it changes T07 and T14, so the author decides whether it goes into MVP.

### Q5 — Unpublished/private tournaments — **Answered**

**A private tournament returns 401.**
- The JSON export returns `401` with `Content-Type: application/json`, `Cache-Control: no-cache` and the body `{"error":"🔒 Sorry, you can't do that"}`.
- The HTML page returns `302` to `/` (the home page), not to `/error`.
- Tested on tournament 5125, created as private by the author for this purpose.
- So the client can tell "private" (401 on the JSON) from "does not exist" (302 to `/error`).
- **Switching to public takes effect immediately.** At 18:26Z, after the author made 5125 public, the JSON returned `200` and the HTML page `200`. Neither Cobra-side caching nor a delay was observed.
- **The JSON has no visibility flag.** The export of a public tournament has the same top-level keys as before. Private versus public can only be seen from the HTTP status.
- **Switching back to private also takes effect immediately.** At 18:31Z, after the author made 5125 private again, the JSON returned `401` and the HTML page a `302` to `/`, the same as the first time.
- **The shortcode of a private tournament hides the ID.** `/N9WI` returns `302` with `Location: https://tournaments.nullsignal.games/` (the home page). This is a third outcome, distinct from `/tournaments/{id}` (known code) and `/tournaments/not_found?code=…` (unknown code). A shortcode given while the tournament is private cannot be resolved to an ID, and so cannot reach the cached copy, unless the code → ID mapping was cached while the tournament was public.
- **Why organisers hide a tournament** (author, 2026-10-01): briefly, e.g. to announce pairings or results live so players are not on their phones, or to protect Cobra from overload. The tournament becomes visible again afterwards. The cache only holds data fetched before the tournament was hidden, so serving it does not leak what is announced while it is private.
- **Organisers can toggle visibility mid-event.** FR-21, SPEC §7 and AC-25 cover a public tournament turning private: serve the cached copy with a "now private" note.
- **Empty tournament export:** 5125 has `players: []`, `rounds: []`, `preliminaryRounds: 0`, `cutToTop: 0` (424 B). This is a real "not started" export, usable for AC-06 instead of a synthetic one. Snapshot: `snapshots/5125/20261001T182654Z.json`.

**A non-existent ID does not return 404.**
- Both `/tournaments/99999999.json` and `/tournaments/99999999` return `302` with `Location: https://tournaments.nullsignal.games/error`.
- That `/error` page is `200 text/html` (4.6 KB).
- This contradicts SPEC §7 and T14 ("404 → Tournament not found"). The client must treat it as NotFound:
  - fetch the JSON without following redirects
  - a 3xx whose `Location` path is `/error` → NotFound
  - any other non-200, or a 200 with a non-JSON body → Unavailable
  - keep 404 → NotFound in case Cobra starts sending it

*Applied in SPEC §7 (v0.3).*

User-facing handling of 401 is decided in FR-21, SPEC §7 and AC-25: serve the cache with "Tournament is now private — data from …", or reply "This tournament is private." when there is no cache.

## Other observations

- **Top-level keys:** `name`, `date`, `cutToTop`, `preliminaryRounds`, `tournamentOrganiser`, `players`, `eliminationPlayers`, `rounds`, `uploadedFrom`, `links`. `eliminationPlayers` is `[]` when there is no cut. In 4909 it has 8 entries with keys `id`, `name`, `rank` and `seed`. Those names also need anonymising.
- **Player keys:** `id`, `name`, `rank`, `corpFaction`, `corpIdentity`, `runnerFaction`, `runnerIdentity`, `matchPoints`, `strengthOfSchedule`, `extendedStrengthOfSchedule`, `pronouns`. SoS and eSoS are strings (`"3.75"`).
- **Missing identities:** 21 of 31 players in 5018 have `corpIdentity` / `runnerIdentity` (and their factions) set to `null`. Formatters must render missing IDs.
- **Personal data beyond names:** `players[].pronouns` and `tournamentOrganiser.nrdbId` / `nrdbUsername`. The anonymiser (T04) replaces them. *Applied in SPEC §12.*
- **HTTP:**
  - The JSON is served without gzip: 19 KB for 31 players and 3 rounds; 123 KB for World Championship 2026 in round 1 and 197 KB after 3 rounds (283 players), fetched in 0.6–1.8 s during play.
  - `Cache-Control: max-age=0, private, must-revalidate`.
  - The weak `ETag` equals the first 32 hex characters of the body's SHA-256, so it is a pure function of the body. `If-None-Match` revalidation (304) might lower the cost of refreshing the cache. Untested.

## Still to capture

- [ ] Live top cut (World Championship 2026, day 2): cut start, an elimination round in progress. Run `uv run scripts/capture_snapshots.py <id> --interval 120`, using 5132 or the ID of a separate cut tournament if the organisers create one.
- [ ] 5018 with round 3 partly reported. No longer needed for AC-07: 5132 `…T153345Z` (single-sided, 50/141 tables) covers a partly reported round. It would still show a double-sided pair with only one game in (Q3): `uv run scripts/capture_snapshots.py 5018 --interval 1800`
- [x] Live single-sided Swiss (World Championship 2026, 5132): round 1 with no results, round start, mid-round, round complete before and after the recount.
- [x] Finished exports 4909 and 4990 (fixtures for the ACs).
- [x] Non-existent numeric ID.
- [x] Private tournament (Q5).
