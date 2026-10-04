# Domain: round state, top cut, player search

Code: `domain/rounds.py`, `domain/bracket.py`, `domain/search.py`. Pure functions over the models in `docs/spec/cobra.md`.

## Rounds

- **Swiss rounds**: rounds whose pairings all have `eliminationGame == false`.
- **Round numbers**: 1-based positions in `rounds`, Swiss and elimination together. A requested round below 1 or above the last is out of range: "Round N does not exist. This tournament has rounds 1–M."
- **Latest round**: the last round in `rounds`, Swiss or elimination. Default `pairings` and the player search show it.
- **Not started**: no rounds → "Tournament has not started yet." (standings with registered players: see below).
- **Round complete**: every non-bye pairing has all results reported. Single-sided: both `combinedScore`. Double-sided: `corpScore` and `runnerScore` of both seats. Elimination: a seat has `winner: true`.

## Standings

- Cobra's `rank` and `matchPoints` are shown as they are.
- "Standings after round N": N is the last complete Swiss round, or an earlier one, for which every player's `matchPoints` equals the sum of their `combinedScore` over Swiss rounds 1..N (byes included). If no round fits (e.g. points adjusted by hand), the last complete Swiss round, and a warning is logged.
- N = 0 → "No completed rounds yet", players in Cobra's `rank` order.
- Players registered and no round paired → "Registered players — not started yet", ranked 1 to N in Cobra's order: by name with only letters and digits counted, ignoring case and diacritics (`M.G.K.` between `metronome` and `Michael kwan`), not by the export's `rank`.

## Top cut

- The elimination rounds, in order, are bracket rounds 1, 2, …; `table` is the game number.
- Game positions and where winners and losers go come from Cobra's fixed brackets (`app/services/bracket/*.rb` in Null-Signal-Games/cobra), copied as templates: double elimination top 4, 8, 16 (the second final shown only once paired) and single elimination top 2, 3, 4, 8, 16.
- The export has no format flag: the template whose rounds hold exactly the paired games, and whose round 1 holds the seeded players, is used; double elimination when both fit or nothing is paired. Another cut size has no bracket ("There is no bracket for a top N cut.").
- Seeds: the Swiss ranks of the top `cutToTop` players, overridden by `eliminationPlayers[].seed`.
- **Cut state** (FR-22): none (`cutToTop` 0, no elimination round) / announced (`cutToTop` set, no elimination round) / in progress (an elimination round) / finished (Cobra has placed a player first in `eliminationPlayers`).
- Standings carry the cut state once Swiss is over: every Swiss round so far complete and counted (the standings round equals the number of Swiss rounds), or a cut made. Cobra does not export the planned number of Swiss rounds, so between two Swiss rounds this also reads "No top cut on Cobra yet".
- **Cut ranking**: Cobra's `eliminationPlayers` places where decided; the other places hold the players not placed yet: still in first (by seed), then out (double elimination: two losses; single: one), the later out higher, ties by seed.

## Player search

- `query` is split on `,` and `;` into at most 10 names; each name is searched on its own; past 10, a note says how many were not searched.
- Normalisation of name and query: Unicode NFKD, combining marks removed, `casefold()`, plus a map for letters that do not decompose (`ł→l`, `ø→o`, `đ→d`, `ß→ss`, `æ→ae`, `œ→oe`).
- Substring match on the normalised strings; per name at most 3 matches in rank order, plus the count of the rest. The union of all names' matches is shown once each, in rank order.
