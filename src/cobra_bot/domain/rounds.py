"""Round-state derivation (SPEC §5, adjusted by docs/findings.md).

Round numbers are 1-based positions in `Tournament.rounds`; Swiss rounds come
first and elimination (top cut) rounds follow them in the same list.
"""

from dataclasses import dataclass

from cobra_bot.domain.models import Pairing, Player, Round, Tournament


@dataclass(frozen=True)
class NotStarted:
    """The tournament has no rounds yet."""


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
    """Standings after the last complete Swiss round, using Cobra's rank as-is.

    With no complete round yet, the players are still listed in rank order (AC-08).
    """
    if not t.rounds:
        return NotStarted()
    return StandingsView(
        after_round=last_complete_swiss_round(t),
        players=tuple(sorted(t.players, key=lambda p: p.rank)),
    )
