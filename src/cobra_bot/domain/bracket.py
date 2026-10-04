"""Top cut (elimination stage): Cobra's brackets, the cut's state and ranking.

The export has no bracket: only the cut's games, round by round, after the Swiss
rounds in `rounds`, with the game number in `table`. Where each game sits and
where its winner and loser go comes from Cobra's fixed brackets
(`app/services/bracket/*.rb` in Null-Signal-Games/cobra), copied here as
`TEMPLATES`. The k-th elimination round is the bracket's round k, as Cobra pairs
a whole bracket round at once. Cut seeds are the Swiss ranks (checked against
`eliminationPlayers[].seed` in every fixture), and in round 1 the first player
holds the first slot.

The export does not say whether the cut is single or double elimination, so
the paired games decide: the bracket whose rounds hold exactly those games
(and, in round 1, those seeds). Before round 1 is paired, or where both fit
(round 1 of a top 4), double elimination, Cobra's default.
"""

from dataclasses import dataclass
from typing import Literal

from cobra_bot.domain.models import Pairing, Player, Round, Tournament


@dataclass(frozen=True)
class Seed:
    position: int


@dataclass(frozen=True)
class WinnerOf:
    game: int


@dataclass(frozen=True)
class LoserOf:
    game: int


@dataclass(frozen=True)
class Reseeded:
    """Single elimination: a later game's players are known only once paired
    (Cobra's `seed_of`: the best and worst remaining seeds meet)."""


type Source = Seed | WinnerOf | LoserOf | Reseeded


@dataclass(frozen=True)
class GameSpec:
    number: int
    round: int
    upper: bool  # False: the lower (losers') bracket
    slot1: Source
    slot2: Source
    winner_game: int | None = None
    loser_game: int | None = None


@dataclass(frozen=True)
class Template:
    size: int
    double: bool
    games: tuple[GameSpec, ...]

    def game(self, number: int) -> GameSpec | None:
        return next((g for g in self.games if g.number == number), None)

    @property
    def reset_game(self) -> int | None:
        """Double elimination: the second final, played only when the lower
        bracket's player wins the first."""
        return self.games[-1].number if self.double else None


def _g(
    number: int,
    rnd: int,
    slot1: Source,
    slot2: Source,
    winner_game: int | None = None,
    loser_game: int | None = None,
    *,
    upper: bool = True,
) -> GameSpec:
    return GameSpec(number, rnd, upper, slot1, slot2, winner_game, loser_game)


def _lower(
    number: int, rnd: int, slot1: Source, slot2: Source, winner_game: int
) -> GameSpec:
    return _g(number, rnd, slot1, slot2, winner_game, upper=False)


S, W, L, R = Seed, WinnerOf, LoserOf, Reseeded()

DOUBLE_TOP4 = Template(
    4,
    True,
    (
        _g(1, 1, S(1), S(4), 3, 4),
        _g(2, 1, S(2), S(3), 3, 4),
        _g(3, 2, W(1), W(2), 6, 5),
        _lower(4, 2, L(1), L(2), 5),
        _lower(5, 3, L(3), W(4), 6),
        _g(6, 4, W(3), W(5), 7, 7),
        _g(7, 5, W(6), L(6)),
    ),
)

DOUBLE_TOP8 = Template(
    8,
    True,
    (
        _g(1, 1, S(1), S(8), 5, 7),
        _g(2, 1, S(4), S(5), 5, 7),
        _g(3, 1, S(2), S(7), 6, 8),
        _g(4, 1, S(3), S(6), 6, 8),
        _g(5, 2, W(1), W(2), 9, 11),
        _g(6, 2, W(3), W(4), 9, 10),
        _lower(7, 2, L(1), L(2), 10),
        _lower(8, 2, L(3), L(4), 11),
        _g(9, 3, W(5), W(6), 14, 13),
        _lower(10, 3, L(6), W(7), 12),
        _lower(11, 3, W(8), L(5), 12),
        _lower(12, 4, W(10), W(11), 13),
        _lower(13, 5, L(9), W(12), 14),
        _g(14, 6, W(9), W(13), 15, 15),
        _g(15, 7, W(14), L(14)),
    ),
)

DOUBLE_TOP16 = Template(
    16,
    True,
    (
        _g(1, 1, S(1), S(16), 13, 9),
        _g(2, 1, S(8), S(9), 13, 9),
        _g(3, 1, S(5), S(12), 14, 10),
        _g(4, 1, S(4), S(13), 14, 10),
        _g(5, 1, S(3), S(14), 15, 11),
        _g(6, 1, S(6), S(11), 15, 11),
        _g(7, 1, S(7), S(10), 16, 12),
        _g(8, 1, S(2), S(15), 16, 12),
        _lower(9, 2, L(1), L(2), 17),
        _lower(10, 2, L(3), L(4), 18),
        _lower(11, 2, L(5), L(6), 19),
        _lower(12, 2, L(7), L(8), 20),
        _g(13, 2, W(1), W(2), 21, 20),
        _g(14, 2, W(3), W(4), 21, 19),
        _g(15, 2, W(5), W(6), 22, 18),
        _g(16, 2, W(7), W(8), 22, 17),
        _lower(17, 3, L(16), W(9), 23),
        _lower(18, 3, L(15), W(10), 23),
        _lower(19, 3, L(14), W(11), 24),
        _lower(20, 3, L(13), W(12), 24),
        _g(21, 3, W(13), W(14), 27, 25),
        _g(22, 3, W(15), W(16), 27, 26),
        _lower(23, 4, W(17), W(18), 25),
        _lower(24, 4, W(19), W(20), 26),
        _g(27, 4, W(21), W(22), 30, 29),
        _lower(25, 5, L(21), W(23), 28),
        _lower(26, 5, W(24), L(22), 28),
        _lower(28, 6, W(25), W(26), 29),
        _lower(29, 7, L(27), W(28), 30),
        _g(30, 8, W(27), W(29), 31, 31),
        _g(31, 9, W(30), L(30)),
    ),
)

SINGLE_TOP2 = Template(2, False, (_g(1, 1, S(1), S(2)),))

SINGLE_TOP3 = Template(3, False, (_g(1, 1, S(2), S(3), 2), _g(2, 2, S(1), W(1))))

SINGLE_TOP4 = Template(
    4, False, (_g(1, 1, S(1), S(4), 3), _g(2, 1, S(2), S(3), 3), _g(3, 2, R, R))
)

SINGLE_TOP8 = Template(
    8,
    False,
    (
        _g(1, 1, S(1), S(8), 5),
        _g(2, 1, S(2), S(7), 5),
        _g(3, 1, S(3), S(6), 6),
        _g(4, 1, S(4), S(5), 6),
        _g(5, 2, R, R, 7),
        _g(6, 2, R, R, 7),
        _g(7, 3, R, R),
    ),
)

SINGLE_TOP16 = Template(
    16,
    False,
    (
        *(_g(n, 1, S(n), S(17 - n), 9 + (n - 1) // 2) for n in range(1, 9)),
        *(_g(n, 2, R, R, 13 + (n - 9) // 2) for n in range(9, 13)),
        _g(13, 3, R, R, 15),
        _g(14, 3, R, R, 15),
        _g(15, 4, R, R),
    ),
)

# By cut size: the double-elimination bracket first (Cobra's default).
TEMPLATES: dict[int, tuple[Template, ...]] = {
    2: (SINGLE_TOP2,),
    3: (SINGLE_TOP3,),
    4: (DOUBLE_TOP4, SINGLE_TOP4),
    8: (DOUBLE_TOP8, SINGLE_TOP8),
    16: (DOUBLE_TOP16, SINGLE_TOP16),
}


# --- the cut in a tournament ---------------------------------------------------


type CutStatus = Literal["none", "announced", "in_progress", "finished"]


def cut_rounds(t: Tournament) -> tuple[Round, ...]:
    """The elimination rounds, in order: bracket rounds 1, 2, …"""
    return tuple(rnd for rnd in t.rounds if any(p.elimination for p in rnd))


def cut_size(t: Tournament) -> int:
    """Players in the cut: `cutToTop`, which Cobra sets when the cut is made."""
    return t.cut_to_top


def cut_status(t: Tournament) -> CutStatus:
    """`none`: Cobra has no cut (yet); `announced`: the cut is made, no game is
    paired; `in_progress`; `finished`: Cobra has placed the winner first."""
    if any(e.rank == 1 and e.player_id is not None for e in t.elimination_players):
        return "finished"
    if cut_rounds(t):
        return "in_progress"
    return "announced" if t.cut_to_top > 0 else "none"


def seeds(t: Tournament) -> dict[int, int]:
    """Player ID -> cut seed: the Swiss rank of the top `cut_size` players,
    overridden by the seeds Cobra exports for placed players."""
    size = cut_size(t)
    out = {p.id: p.rank for p in t.players if p.rank <= size}
    for e in t.elimination_players:
        if e.player_id is not None and e.seed is not None:
            out[e.player_id] = e.seed
    return out


def template(t: Tournament) -> Template | None:
    """Cobra's bracket for this cut, or None when no bracket fits (a cut size
    Cobra has no bracket for, or games that match none)."""
    by_seed = {seed: pid for pid, seed in seeds(t).items()}
    rounds = cut_rounds(t)
    return next(
        (c for c in TEMPLATES.get(cut_size(t), ()) if _fits(c, rounds, by_seed)),
        None,
    )


def _fits(c: Template, rounds: tuple[Round, ...], by_seed: dict[int, int]) -> bool:
    for number, rnd in enumerate(rounds, start=1):
        expected = {g.number for g in c.games if g.round == number}
        if {p.table for p in rnd} != expected:
            return False
        for pairing in rnd:
            spec = c.game(pairing.table)
            if spec is None:
                return False
            # A seed whose player the export lacks is not checked.
            wanted = {
                by_seed[s.position]
                for s in (spec.slot1, spec.slot2)
                if isinstance(s, Seed) and s.position in by_seed
            }
            if wanted and not wanted <= set(pairing.player_ids):
                return False
    return True


# --- bracket view ---------------------------------------------------------------


@dataclass(frozen=True)
class BracketSlot:
    player_id: int | None  # None while not known
    source: Source  # where the player comes from, shown while unknown


@dataclass(frozen=True)
class BracketGame:
    spec: GameSpec
    pairing: Pairing | None  # None until Cobra pairs the game
    slot1: BracketSlot
    slot2: BracketSlot


@dataclass(frozen=True)
class BracketView:
    template: Template
    games: tuple[BracketGame, ...]  # the reset game only once it is paired
    rounds: int  # columns: the highest bracket round shown
    status: CutStatus


@dataclass(frozen=True)
class NoTopCut:
    """Cobra has no cut for this tournament (yet)."""


@dataclass(frozen=True)
class BracketUnavailable:
    """A cut whose bracket the bot does not know."""

    size: int


type BracketResult = BracketView | NoTopCut | BracketUnavailable


def bracket_view(t: Tournament) -> BracketResult:
    status = cut_status(t)
    if status == "none":
        return NoTopCut()
    c = template(t)
    if c is None:
        return BracketUnavailable(cut_size(t))
    paired = {p.table: p for rnd in cut_rounds(t) for p in rnd}
    by_seed = {seed: pid for pid, seed in seeds(t).items()}
    games = []
    for spec in c.games:
        pairing = paired.get(spec.number)
        if spec.number == c.reset_game and pairing is None:
            continue
        if pairing is not None:
            slot1 = BracketSlot(pairing.seat1.player_id, spec.slot1)
            slot2 = BracketSlot(pairing.seat2.player_id, spec.slot2)
        else:
            slot1 = BracketSlot(_resolve(spec.slot1, paired, by_seed), spec.slot1)
            slot2 = BracketSlot(_resolve(spec.slot2, paired, by_seed), spec.slot2)
        games.append(BracketGame(spec, pairing, slot1, slot2))
    return BracketView(
        template=c,
        games=tuple(games),
        rounds=max(g.spec.round for g in games),
        status=status,
    )


def _resolve(
    source: Source, paired: dict[int, Pairing], by_seed: dict[int, int]
) -> int | None:
    match source:
        case Seed(position=position):
            return by_seed.get(position)
        case WinnerOf(game=game):
            return winner(paired.get(game))
        case LoserOf(game=game):
            return loser(paired.get(game))
        case Reseeded():
            return None


def winner(pairing: Pairing | None) -> int | None:
    if pairing is None:
        return None
    seat = next((s for s in (pairing.seat1, pairing.seat2) if s.winner), None)
    return seat.player_id if seat else None


def loser(pairing: Pairing | None) -> int | None:
    if pairing is None or winner(pairing) is None:
        return None
    seat = next((s for s in (pairing.seat1, pairing.seat2) if not s.winner), None)
    return seat.player_id if seat else None


# --- top-cut ranking ------------------------------------------------------------


@dataclass(frozen=True)
class CutEntry:
    rank: int | None  # Cobra's final place; None while not decided
    player_id: int
    player: Player | None  # the Swiss record (name, IDs)
    seed: int | None
    wins: int
    losses: int
    eliminated: bool


@dataclass(frozen=True)
class TopCutView:
    size: int
    status: CutStatus
    entries: tuple[CutEntry, ...]  # places 1..size


type TopCutResult = TopCutView | NoTopCut


def top_cut_view(t: Tournament) -> TopCutResult:
    """The cut's ranking, like standings: Cobra's places where decided. The
    other places hold the players not placed yet: those still playing first,
    then those already out, the later out higher; ties by seed."""
    status = cut_status(t)
    if status == "none":
        return NoTopCut()
    c = template(t)
    double = c.double if c is not None else True
    seed_of = seeds(t)
    games = [p for rnd in cut_rounds(t) for p in rnd]
    placed = {
        e.player_id: e.rank for e in t.elimination_players if e.player_id is not None
    }
    ids = set(seed_of) | set(placed) | {i for p in games for i in p.player_ids}

    entries: dict[int, CutEntry] = {}
    last_round: dict[int, int] = {}
    for pid in ids:
        wins = losses = 0
        for number, rnd in enumerate(cut_rounds(t), start=1):
            for p in rnd:
                if pid in p.player_ids:
                    last_round[pid] = number
                    if winner(p) == pid:
                        wins += 1
                    elif loser(p) == pid:
                        losses += 1
        rank = placed.get(pid)
        entries[pid] = CutEntry(
            rank=rank,
            player_id=pid,
            player=t.player(pid),
            seed=seed_of.get(pid),
            wins=wins,
            losses=losses,
            eliminated=(rank is not None and rank > 1)
            or losses >= (2 if double else 1),
        )

    def waiting(e: CutEntry) -> tuple[bool, int, int, int]:
        return (
            e.eliminated,
            -last_round.get(e.player_id, 0),
            e.seed if e.seed is not None else len(ids) + 1,
            e.player_id,
        )

    unplaced = iter(
        sorted((e for e in entries.values() if e.rank is None), key=waiting)
    )
    by_rank = {e.rank: e for e in entries.values() if e.rank is not None}
    size = max(cut_size(t), len(ids))
    ordered = [by_rank.get(n) or next(unplaced, None) for n in range(1, size + 1)]
    return TopCutView(
        size=cut_size(t),
        status=status,
        entries=tuple(e for e in ordered if e is not None),
    )
