# Acceptance criteria

Each criterion has at least one test marked `@pytest.mark.req("AC-xx")`; `tests/test_traceability.py` checks it. A criterion whose text starts with "Manual" is checked by hand (`docs/acceptance.md`). Fixtures: `docs/spec/fixtures.md`; players are referred to by fixture player ID.

| ID | Given / When / Then |
|----|---------------------|
| AC-01 | Given fixture `single_sided_top8` (8 Swiss rounds + top 8), when standings are formatted, then the header says "Standings after round 8" and the first row is player 1042 with 22 pts. |
| AC-02 | Given fixture `single_sided_top8`, when pairings for round 1 are formatted, then table 21 shows player 1023 with BYE. |
| AC-03 | Given fixture `single_sided_top8`, when pairings without a round are requested, then round 14 (top cut round 6, the final) is shown, headed "Top cut round 6 pairings — complete". |
| AC-04 | Given fixture `single_sided_top8`, when round 9 is requested, then the top cut's round 1 is shown: games 1–4, the winner `W` and bold, the loser `L` and secondary. |
| AC-05 | Given fixture `single_sided_top8`, when round 0 or 15 is requested, then the reply is a round-out-of-range error. |
| AC-06 | Given a fixture with no rounds, when pairings are requested, then the reply is "Tournament has not started yet."; the same for standings when there are no players either (with players, AC-26). |
| AC-07 | Given a live fixture with some unreported results in round N, then pairings say "Round N pairings — in progress" and standings say "Standings after round N−1"; the same standings when round N is fully reported but Cobra's `matchPoints` do not count it yet (the organiser has not closed it). |
| AC-08 | Given a live fixture in round 1 with no reported results, then standings say "No completed rounds yet" and list all players in Cobra's `rank` order. |
| AC-09 | Given fixture `single_sided_top8`, when searching a substring of player 1017's name in different letter case, then exactly that player is returned with rank 2. |
| AC-10 | Given a query matching more than 3 players, then 3 are shown in rank order and "and N more" has the correct N. |
| AC-11 | Given a query matching nobody, then the reply is "No players match". |
| AC-12 | Given names `Maëlig` and `Żółw`, then queries `maelig` and `ZOLW` match them. |
| AC-13 | Given inputs `4909`, `https://tournaments.nullsignal.games/tournaments/4977/players/standings`, `https://example.com/tournaments/1`, `abc!`, then results are ID 4909, ID 4977, error, error. |
| AC-14 | Given fixture `large_top_cut` (235 players), when standings are rendered, then there are ≤ 5 pages in one message, each an embed and a PNG under Discord's 10 MB attachment limit, and every player appears once, in rank order. |
| AC-15 | Given more players (or tables) than 5 pages hold, then exactly 5 pages are produced and the last one ends with "…and N more — full list on Cobra" with the correct N and link (tested with a lowered page size). |
| AC-16 | Given a fake store and clock, when the same tournament is requested twice within 60 s, then one HTTP call is made; after 61 s, a second call is made. |
| AC-17 | Given a 10-minute-old cache entry and a failing HTTP call, then data is returned marked stale with the stale notice; given no cache, "Cobra is unavailable, try again later."; given HTTP 404, "Tournament not found." |
| AC-18 | Given a held lock and a fresh cache object appearing within 2 s, then the second caller makes no HTTP call. (Should) |
| AC-19 | Given a request with an invalid signature, the handler returns 401; given a valid PING, `{"type": 1}`; given a `player` command, the deferred response is public (no flags) and the Worker is invoked asynchronously. |
| AC-20 | Manual: on a test server and via user install in a DM, every command works against a real tournament; no bot permissions were granted (`docs/acceptance.md`). |
| AC-21 | Given names `@Mention`, `*bold_name~` and one with backticks, then every outgoing payload has `allowed_mentions.parse == []`; names are drawn in images, never sent as message text, and the search query in message text is escaped for Discord markdown. |
| AC-22 | Given fixture `dss` (double-sided), then pairings show both games per table and round completion requires both games reported. |
| AC-23 | Given `template.yaml`, then WorkerFunction has `MaximumRetryAttempts: 0` and the cache bucket has a lifecycle rule (template test). |
| AC-24 | Given the command registration payload, then `integration_types == [0, 1]` and `contexts == [0, 1, 2]`. |
| AC-25 | Given a 10-minute-old cache entry and HTTP 401 from Cobra, then the cached data is returned marked stale with the note "Tournament is now private — data from <t:UNIX:R>" and the cache entry is unchanged; given no cache and HTTP 401, the reply is "This tournament is private." |
| AC-26 | Given an export with registered players and no rounds (World Championship 2026 before round 1), when standings are requested, then the header is "Registered players — not started yet" and every player is listed, ranked 1 to N in Cobra's order: by name with only letters and digits counted, ignoring case and diacritics (`M.G.K.` between `metronome` and `Michael kwan`), not by the export's `rank`. |
| AC-27 | Given `query` "Alice, zed, ali" where `ali` also matches Alice, then each matching player gets one card in rank order, a note says "No players match “zed”.", and a name matching more than 3 players notes "…and N more matched “name”"; past 10 names, "Only the first 10 names were searched (N more given)." |
| AC-28 | Given fixture `single_sided_top8`, when standings are requested, then the note "Top 8 cut finished — see `/cobra top-cut` and `/cobra bracket`" follows the header; with a cut made and no elimination round, "Top N cut announced — not started yet"; with every Swiss round counted and no cut, "No top cut on Cobra yet"; while a Swiss round is played, no note. |
| AC-29 | Given fixture `single_sided_top8`, when `/cobra top-cut` is requested, then the header is "Top 8 cut — finished" and the 8 players are listed in Cobra's places with their W–L and seed; during a cut, undecided places hold the players still in by seed, then those out; without a cut, "This tournament has no top cut on Cobra yet." |
| AC-30 | Given fixtures `single_sided_top8` and `large_top_cut`, when `/cobra bracket` is requested, then their games fit Cobra's double-elimination top 8 and top 16 brackets and one image is sent, headed "Top 8 bracket (double elimination) — finished"; before round 1 is paired the first games show the seeded players and later games "Winner of N" / "Loser of N". |
