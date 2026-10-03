"""Round-state derivation (SPEC §5, adjusted by docs/findings.md).

Round numbers are 1-based positions in `Tournament.rounds`; Swiss rounds come
first and elimination (top cut) rounds follow them in the same list.
"""

from dataclasses import dataclass, replace

from cobra_bot.domain.models import Pairing, Player, Round, Tournament
from cobra_bot.domain.search import normalize


@dataclass(frozen=True)
class NotStarted:
    """The tournament has no rounds yet (and, for standings, no players)."""


@dataclass(frozen=True)
class RoundOutOfRange:
    requested: int
    last_round: int


@dataclass(frozen=True)
class TopCutNotSupported:
    round_number: int


@dataclass(frozen=True)
class PairingsView:
    round_number: int
    pairings: Round
    complete: bool
    top_cut_in_progress: bool


@dataclass(frozen=True)
class StandingsView:
    after_round: int  # 0 = no completed Swiss round yet
    players: tuple[Player, ...]  # in Cobra's rank order
    started: bool = True  # False: registration only, no round paired yet


type PairingsResult = PairingsView | NotStarted | RoundOutOfRange | TopCutNotSupported
type StandingsResult = StandingsView | NotStarted


def is_swiss(rnd: Round) -> bool:
    return all(not p.elimination for p in rnd)


def is_pairing_complete(pairing: Pairing) -> bool:
    """Unreported results are null (findings Q1); a bye needs no result."""
    if pairing.is_bye:
        return True
    seats = (pairing.seat1, pairing.seat2)
    if pairing.elimination:
        return any(s.winner is not None for s in seats)
    if pairing.double_sided:
        return all(
            s.corp_score is not None and s.runner_score is not None for s in seats
        )
    return all(s.combined_score is not None for s in seats)


def is_round_complete(rnd: Round) -> bool:
    return bool(rnd) and all(is_pairing_complete(p) for p in rnd)


def swiss_round_numbers(t: Tournament) -> list[int]:
    return [n for n, rnd in enumerate(t.rounds, start=1) if is_swiss(rnd)]


def top_cut_in_progress(t: Tournament) -> bool:
    return any(not is_swiss(rnd) for rnd in t.rounds)


def last_complete_swiss_round(t: Tournament) -> int:
    """Number of the last complete Swiss round; 0 if none is complete."""
    return max(
        (n for n in swiss_round_numbers(t) if is_round_complete(t.rounds[n - 1])),
        default=0,
    )


def standings_round(t: Tournament) -> int:
    """The Swiss round Cobra's `rank` and `matchPoints` stand after.

    Cobra recounts them when the organiser closes a round, not when its last
    result comes in (docs/findings.md Q2), so a complete round may not be
    counted yet. The answer is the last complete round N, or an earlier one,
    for which every player's `matchPoints` is the sum of their `combinedScore`
    over Swiss rounds 1..N (byes included). If no round fits (e.g. points
    adjusted by hand in Cobra), the last complete round is used as before.
    """
    last = last_complete_swiss_round(t)
    swiss = [t.rounds[n - 1] for n in swiss_round_numbers(t)]
    points = {p.id: 0 for p in t.players}
    totals = [dict(points)]  # totals[n] = points after the first n Swiss rounds
    for rnd in swiss[:last]:
        for pairing in rnd:
            for seat in (pairing.seat1, pairing.seat2):
                if seat.player_id in points:
                    points[seat.player_id] += seat.combined_score or 0
        totals.append(dict(points))
    counted = {p.id: p.match_points for p in t.players}
    return next((n for n in range(last, -1, -1) if totals[n] == counted), last)


def pairings_view(t: Tournament, requested: int | None = None) -> PairingsResult:
    """Pairings for `requested`, or for the latest Swiss round when it is None."""
    if not t.rounds:
        return NotStarted()
    if requested is None:
        swiss = swiss_round_numbers(t)
        if not swiss:
            return TopCutNotSupported(round_number=len(t.rounds))
        number = swiss[-1]
    elif not 1 <= requested <= len(t.rounds):
        return RoundOutOfRange(requested=requested, last_round=len(t.rounds))
    elif not is_swiss(t.rounds[requested - 1]):
        return TopCutNotSupported(round_number=requested)
    else:
        number = requested
    rnd = t.rounds[number - 1]
    return PairingsView(
        round_number=number,
        pairings=rnd,
        complete=is_round_complete(rnd),
        top_cut_in_progress=top_cut_in_progress(t),
    )


def standings_view(t: Tournament) -> StandingsResult:
    """Standings after the last Swiss round Cobra has counted (`standings_round`),
    using Cobra's rank as-is.

    With no complete round yet, the players are still listed in rank order (AC-08).
    Before the first round is paired, the registered players are listed as Cobra
    lists them then: by `name_order`, ranked 1 to N in that order (the export's
    `rank` is not that order) (AC-26). With no players either, the
    tournament has not started (AC-06).
    """
    if not t.rounds and not t.players:
        return NotStarted()
    return StandingsView(
        after_round=standings_round(t),
        players=ranked_players(t),
        started=bool(t.rounds),
    )


def ranked_players(t: Tournament) -> tuple[Player, ...]:
    """The players in standings order, with the rank standings show: Cobra's
    `rank` once a round is paired; before that, 1 to N by `name_order`, as
    Cobra lists registered players. Player search ranks by this too (AC-26)."""
    if t.rounds:
        return tuple(sorted(t.players, key=lambda p: p.rank))
    by_name = sorted(t.players, key=lambda p: (*name_order(p.name), p.id))
    return tuple(replace(p, rank=n) for n, p in enumerate(by_name, start=1))


def name_order(name: str) -> tuple[str, str]:
    """Sort key matching Cobra's player list: letters and digits only, ignoring
    case and diacritics (`M.G.K.` between `metronome` and `Michael`, `VØRT3X`
    after `Victor`), then the name ignoring case. Checked against Cobra's own
    order of the 262 players of World Championship 2026."""
    return "".join(c for c in normalize(name) if c.isalnum()), name.casefold()
