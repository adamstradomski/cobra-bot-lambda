# Findings — Cobra JSON discovery (T01)

Status: in progress · last updated 2026-10-01 (17:50Z)

This file records what the live Cobra exports actually look like. Per `CLAUDE.md`, it overrides assumptions marked TBD in `docs/spec.md`. The raw evidence lives in `snapshots/`, which is git-ignored and not anonymised. File names are given so the evidence can be re-checked locally.

## Evidence

| Source | What | Files |
|--------|------|-------|
| Tournament 5018 | Double-sided Swiss (confirmed by the author), multi-week event, 31 players, `preliminaryRounds: 3`, `cutToTop: 0`. Snapshot taken with rounds 1–2 complete and round 3 paired, with no results except the bye. | `snapshots/5018/20261001T160955Z.json` |
| Tournament 4909 | Finished single-sided Swiss: 46 players, 8 Swiss rounds and top 8 (6 elimination rounds in `rounds`). Matches AC-01 (rank 1 is 56587 with 22 pts), AC-02 (round 1, table 21 is a bye for 56479) and AC-09 (56463 has rank 2). | `snapshots/4909/20261001T174657Z.json` |
| Tournament 4990 | Finished single-sided Swiss: 235 players, 11 Swiss rounds and top cut (8 elimination rounds). 354 KB, fetched in 2.8 s. | `snapshots/4990/20261001T174658Z.json` |
| Shortcode probes | `/QNSF`, `/qnsf`, `/ZQXJ` | `snapshots/probes/20261001T1615*_{QNSF,qnsf,ZQXJ}.meta.json` |
| Non-existent ID probes | `/tournaments/99999999.json`, `/tournaments/99999999` | `snapshots/probes/20261001T174701Z_tournaments_99999999*.meta.json` |
| Private tournament probes | `/tournaments/5125.json`, `/tournaments/5125` while private (18:11Z) and after being made public (18:26Z) | `snapshots/probes/20261001T181141Z_tournaments_5125*.meta.json`, `snapshots/probes/20261001T182654Z_tournaments_5125*.meta.json`, `snapshots/5125/20261001T182654Z.json` |

## Open questions (SPEC §15)

### Q1 — Unreported results: `null`, missing, or 0? — **Answered: `null`, keys present**

- An unreported seat has `combinedScore`, `corpScore` and `runnerScore` all present and all `null`. All 15 non-bye tables of round 3 in 5018 look like this.
- **Exception, byes:** the bye seat already has `combinedScore` set (6 in double-sided Swiss), and `corpScore` / `runnerScore` are `null`, even while the rest of the round is unreported. Round-completion logic must skip bye pairings, which SPEC §5 already says.
- Still unknown: whether a single-sided live export behaves the same way. Expected, but to be confirmed with a Worlds snapshot.

### Q2 — Does `rank` in a live export reflect only completed rounds? — **Assumed yes (author decision, 2026-10-01)**

**Decision:** implement on the assumption that `rank` and `matchPoints` reflect completed rounds only, and use Cobra's `rank` as-is (SPEC §5). If a later snapshot of a partly reported round shows otherwise, revisit this.

- In 5018, `matchPoints` equals the sum of `combinedScore` over rounds 1–2 for every player. Player 58464's round-3 bye (already `combinedScore: 6`) is **not** included: their `matchPoints` is 0.
- `rank` is unique and matches ordering by (`matchPoints`, `strengthOfSchedule`) descending.
- So with round 3 paired and unreported, standings are "after round 2", consistent with SPEC §5.
- Not verified: whether results reported on individual tables of an in-progress round are counted before the whole round is complete. The 5018 snapshot has 0 of 15 non-bye tables of round 3 reported, and a re-fetch at 17:47Z was unchanged.

### Q3 — Double-sided JSON structure — **Answered (structure); edge cases open**

- **No top-level double-sided flag:** `preliminaryRounds`, `cutToTop` and the other top-level fields look the same as in single-sided exports.
- **One pairing per table, no `role` key:** each pairing has `player1` and `player2`, and there is no `role` key at all. Confirmed against 4909: single-sided seats have `id`, `role`, `corpScore`, `runnerScore` and `combinedScore`. Elimination seats have `id`, `role` and `winner`.
- **Each seat carries both games:** `corpScore` is the player's result as Corp (0 or 3), `runnerScore` their result as Runner (0 or 3), and `combinedScore` is the sum (0, 3 or 6). Example split: `p1 corp 3, runner 0, combined 3 | p2 corp 3, runner 0, combined 3`, meaning each player won their Corp game.
- **Consequences for the spec:**
  - `Seat.role` is `None` when the key is absent.
  - A pairing is double-sided when its seats have no `role` key.
  - The round is complete when every non-bye seat has non-null `corpScore` **and** `runnerScore`.
- **A bye can be in either slot.** In round 1 of 5018, `player2.id` is `null`. In round 2, **`player1.id`** is `null`. This contradicts SPEC §4 ("a bye is a pairing whose `player2.id` is `null`"). The parser must check both seats.
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

*Proposed spec change, not yet applied.*

User-facing handling of 401 is decided in FR-21, SPEC §7 and AC-25: serve the cache with "Tournament is now private — data from …", or reply "This tournament is private." when there is no cache.

## Other observations

- **Top-level keys:** `name`, `date`, `cutToTop`, `preliminaryRounds`, `tournamentOrganiser`, `players`, `eliminationPlayers`, `rounds`, `uploadedFrom`, `links`. `eliminationPlayers` is `[]` when there is no cut. In 4909 it has 8 entries with keys `id`, `name`, `rank` and `seed`. Those names also need anonymising.
- **Player keys:** `id`, `name`, `rank`, `corpFaction`, `corpIdentity`, `runnerFaction`, `runnerIdentity`, `matchPoints`, `strengthOfSchedule`, `extendedStrengthOfSchedule`, `pronouns`. SoS and eSoS are strings (`"3.75"`).
- **Missing identities:** 21 of 31 players in 5018 have `corpIdentity` / `runnerIdentity` (and their factions) set to `null`. Formatters must render missing IDs.
- **Personal data beyond names:** `players[].pronouns` and `tournamentOrganiser.nrdbId` / `nrdbUsername`. SPEC §12 only covers names, so the anonymiser (T04) should also replace or remove these. *Proposed spec change, not yet applied.*
- **HTTP:**
  - The JSON is served without gzip: 19 KB for 31 players and 3 rounds.
  - `Cache-Control: max-age=0, private, must-revalidate`.
  - The weak `ETag` equals the first 32 hex characters of the body's SHA-256, so it is a pure function of the body. `If-None-Match` revalidation (304) might lower the cost of refreshing the cache. Untested.

## Still to capture

- [ ] 5018 with round 3 partly reported. This is the fixture for AC-07 and AC-22 (Q2 is decided by assumption): `uv run scripts/capture_snapshots.py 5018 --interval 1800`
- [ ] Live single-sided tournament (Worlds): round start, mid-round, round complete, round 1 with no results, cut start.
- [x] Finished exports 4909 and 4990 (fixtures for the ACs).
- [x] Non-existent numeric ID.
- [x] Private tournament (Q5).
