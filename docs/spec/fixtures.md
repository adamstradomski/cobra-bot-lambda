# Test fixtures

Code: `scripts/anonymize_fixture.py`, `tests/fixtures/`, `tests/test_fixtures.py`. Usage of the script: `docs/scripts.md`.

Real Cobra exports are committed only after `scripts/anonymize_fixture.py`:

- Each player name (in `players` and `eliminationPlayers`) becomes a deterministic pseudonym (`Player0001`, …).
- Player IDs are remapped consistently everywhere (`players`, `rounds`, `eliminationPlayers`): new ID = 1000 + position (1-based) in the sorted original IDs; `null` (bye, open place) stays `null`.
- `pronouns` becomes `""`; `tournamentOrganiser.nrdbId` and `nrdbUsername`, the tournament `name` and `date`, and the shortcode in `links[rel=uploadedfrom]` get fixed fake values.
- Ranks, match points, SoS/eSoS, scores, table numbers, flags, factions and identities are kept.
- Only known keys are accepted: an unknown key anywhere aborts the run, so a new Cobra field cannot reach a committed fixture without review.
- Edge-case names can be injected (`@Mention`, `*bold_name~`, `Maëlig`, `Żółw`) so tests cover escaping and diacritics.

| Fixture | Source | Content |
|---------|--------|---------|
| `single_sided_top8` | 4909 | Finished: 46 players, 8 Swiss rounds, top 8 (6 elimination rounds). |
| `large_top_cut` | 4990 | Finished: 235 players, 11 Swiss rounds, top 16 (8 elimination rounds). 600 KB: query it, do not read it whole. |
| `dss` | 5018 | Live double-sided Swiss: rounds 1–2 complete, round 3 paired with no results. |
| `not_started` | 5125 | Empty export: no players, no rounds. |

Fixtures are named by content, not by Cobra ID. `tests/test_fixtures.py` checks that every committed fixture looks anonymised. Tests refer to players by fixture player ID, never by name.
