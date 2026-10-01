"""Tournament data model (SPEC §4, adjusted by docs/findings.md)."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

type Role = Literal["corp", "runner"]


@dataclass(frozen=True)
class Player:
    id: int
    name: str
    rank: int
    match_points: int
    sos: Decimal
    esos: Decimal
    corp_faction: str | None
    corp_identity: str | None
    runner_faction: str | None
    runner_identity: str | None


@dataclass(frozen=True)
class Seat:
    player_id: int | None  # None = bye
    role: Role | None  # None in byes and in double-sided pairings
    combined_score: int | None  # None = not reported
    corp_score: int | None  # double-sided: result of the player's Corp game
    runner_score: int | None  # double-sided: result of the player's Runner game
    winner: bool | None  # elimination games only


@dataclass(frozen=True)
class Pairing:
    table: int
    seat1: Seat
    seat2: Seat
    intentional_draw: bool
    two_for_one: bool
    elimination: bool

    @property
    def is_bye(self) -> bool:
        """A bye has no player in one seat; it can be either seat (findings Q3)."""
        return self.seat1.player_id is None or self.seat2.player_id is None

    @property
    def double_sided(self) -> bool:
        """Double-sided Swiss pairings carry both games per seat and no role.

        Single-sided games always have roles; only byes lack them (findings Q3).
        """
        return (
            not self.is_bye
            and not self.elimination
            and self.seat1.role is None
            and self.seat2.role is None
        )

    @property
    def player_ids(self) -> tuple[int, ...]:
        return tuple(
            s.player_id for s in (self.seat1, self.seat2) if s.player_id is not None
        )


type Round = tuple[Pairing, ...]


@dataclass(frozen=True)
class Tournament:
    id: int
    name: str
    date: date | None
    cut_to_top: int
    preliminary_rounds: int
    players: tuple[Player, ...]
    rounds: tuple[Round, ...]  # index 0 = round 1
    fetched_at: datetime
    stale: bool  # served from cache after a failed fetch

    def player(self, player_id: int) -> Player | None:
        return next((p for p in self.players if p.id == player_id), None)
