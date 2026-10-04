# Cobra: references, HTTP, export format

Code: `cobra/refs.py`, `cobra/client.py`, `cobra/parser.py`, `domain/models.py`. Cobra is <https://tournaments.nullsignal.games>; its JSON export is not an official API. Evidence for the facts below (captured snapshots, Cobra's source): `docs/archive/findings.md`.

## Tournament references

| Input | Result |
|-------|--------|
| `4909` (1–9 digits, > 0) | ID 4909 |
| `https://tournaments.nullsignal.games/tournaments/4977/players/standings` (any page under `/tournaments/{id}`; `http` or `https`; query and fragment ignored) | ID 4977 |
| Shortcode: 4 letters or digits, not all digits, any case (`QNSF`, `n9wi`) | Shortcode `QNSF` / `N9WI` |
| `https://tournaments.nullsignal.games/QNSF` | Shortcode `QNSF` |
| Other hosts, schemes or input | "Invalid tournament reference" |

Surrounding whitespace and Discord's `<…>` link brackets are ignored. An all-digit input is always an ID.

## HTTP

- Requests: User-Agent identifying the bot, 8 s timeout, no redirects followed, no retries.
- `GET /tournaments/{id}.json`:
  - 200 with a JSON body → the export.
  - 302 to `/error` (Cobra's answer for a non-existent ID), or 404 → `NotFound` ("Tournament not found.", not cached).
  - 401 → `Private` (the tournament is private; JSON body `{"error": …}`). Visibility can change at any moment and takes effect immediately; the export itself has no visibility flag.
  - Timeout, connection error, 5xx, any other status, a non-JSON body → `Unavailable`.
- Shortcode: `GET /{CODE}` (any case). Cobra always answers 302; the `Location` decides: `/tournaments/{id}` → that ID; `/tournaments/not_found?code=…` → not found; `/` → the tournament is private (the ID is hidden; see `codes/` in `docs/spec/cache.md`).
- The export is not gzipped: about 120–200 KB for 280 players. Its weak `ETag` is a hash of the body (revalidation not used).

## Export format and parser

Top-level keys: `name`, `date`, `cutToTop`, `preliminaryRounds`, `tournamentOrganiser`, `players`, `eliminationPlayers`, `rounds`, `uploadedFrom`, `links`. Player keys: `id`, `name`, `rank`, `corpFaction`, `corpIdentity`, `runnerFaction`, `runnerIdentity`, `matchPoints`, `strengthOfSchedule`, `extendedStrengthOfSchedule`, `pronouns`.

```python
@dataclass(frozen=True)
class Player:
    id: int; name: str; rank: int; match_points: int
    sos: Decimal; esos: Decimal                     # strings or numbers in the export
    corp_faction: str | None; corp_identity: str | None
    runner_faction: str | None; runner_identity: str | None

@dataclass(frozen=True)
class Seat:
    player_id: int | None         # None = bye (either seat)
    role: Literal["corp", "runner"] | None   # None in byes and double-sided pairings
    combined_score: int | None    # None = not reported
    corp_score: int | None        # double-sided: the player's result as Corp
    runner_score: int | None      # double-sided: the player's result as Runner
    winner: bool | None           # elimination games only; None until reported

@dataclass(frozen=True)
class Pairing:
    table: int; seat1: Seat; seat2: Seat
    intentional_draw: bool; two_for_one: bool; elimination: bool
    # derived: is_bye, double_sided (not a bye, not elimination, no roles), player_ids

@dataclass(frozen=True)
class EliminationPlayer:
    rank: int; player_id: int | None; seed: int | None   # None while the place is open

@dataclass(frozen=True)
class Tournament:
    id: int; name: str; date: date | None; cut_to_top: int; preliminary_rounds: int
    players: tuple[Player, ...]
    rounds: tuple[tuple[Pairing, ...], ...]  # index 0 = round 1
    elimination_players: tuple[EliminationPlayer, ...]
    fetched_at: datetime; stale: bool        # stale: served from cache after a failed fetch
```

How Cobra's exports behave:

- Single-sided Swiss: one Corp and one Runner seat per pairing; roles are set from the moment the round is paired.
- Double-sided Swiss: one pairing per table, no `role` key; each seat holds the player's own Corp result (`corpScore`), Runner result (`runnerScore`) and their sum (`combinedScore`). Seat 1 is the Corp in game 1. There is no top-level double-sided flag.
- Unreported results: the score keys are present and `null`.
- A bye: **either** `player1.id` or `player2.id` is `null`, roles `null`. The bye seat's `combinedScore` is set at once (3 single-sided, 6 double-sided); the empty seat may have `combinedScore: 0`. A round can have several byes, on any tables.
- Table numbers can have gaps.
- `rank`, `matchPoints` and SoS count only rounds the organiser has **closed**, which can be later than the last result coming in (see standings in `docs/spec/domain.md`).
- Elimination rounds follow the Swiss rounds in `rounds`, with `eliminationGame: true` and `winner` (`null` until both scores are in). Each is one bracket round and `table` is the game number.
- `cutToTop` is 0 until the organiser makes the cut. `eliminationPlayers` is `[]` without a cut; during it, one entry per place, with `id`, `name` and `seed` `null` while the place is open.
- Identities and factions can be `null`.
- Personal data beyond names: `pronouns`, `tournamentOrganiser.nrdbId` / `nrdbUsername` (removed by the anonymiser, `docs/spec/fixtures.md`).

The parser is tolerant: unknown keys are ignored, numbers given as strings are accepted, missing optional fields get defaults, a missing or malformed `date` becomes `None`. It fails (`ParseError`, a `ValueError`) only when player IDs, ranks, tables or the overall shape are missing or malformed; the reply is then "unreadable data".
