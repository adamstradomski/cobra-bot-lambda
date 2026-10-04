"""Builders for domain objects, so tests construct inputs directly at their layer."""

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from cobra_bot.domain.models import (
    EliminationPlayer,
    Pairing,
    Player,
    Role,
    Round,
    Seat,
    Tournament,
)

FETCHED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
FETCHED_AT_TAG = "<t:1790856000:R>"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_SGR = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    """`text` without ANSI colour codes."""
    return _SGR.sub("", text)


def fixture_bytes(name: str) -> bytes:
    """Raw JSON of an anonymised fixture in tests/fixtures/."""
    return (FIXTURES_DIR / f"{name}.json").read_bytes()


def player(
    pid: int,
    name: str | None = None,
    *,
    rank: int = 1,
    points: int = 0,
    sos: str = "0",
    corp: str | None = None,
    runner: str | None = None,
) -> Player:
    return Player(
        id=pid,
        name=name if name is not None else f"Player{pid}",
        rank=rank,
        match_points=points,
        sos=Decimal(sos),
        esos=Decimal(0),
        corp_faction=None,
        corp_identity=corp,
        runner_faction=None,
        runner_identity=runner,
    )


def seat(
    pid: int | None,
    role: Role | None = None,
    combined: int | None = None,
    *,
    corp: int | None = None,
    runner: int | None = None,
    winner: bool | None = None,
) -> Seat:
    return Seat(pid, role, combined, corp, runner, winner)


def pairing(
    table: int,
    seat1: Seat,
    seat2: Seat,
    *,
    intentional_draw: bool = False,
    elimination: bool = False,
) -> Pairing:
    return Pairing(table, seat1, seat2, intentional_draw, False, elimination)


def tournament(
    *rounds: Round,
    players: tuple[Player, ...] = (),
    name: str = "Test Cup",
    tid: int = 1,
    stale: bool = False,
    cut_to_top: int = 0,
    elimination_players: tuple[EliminationPlayer, ...] = (),
) -> Tournament:
    return Tournament(
        id=tid,
        name=name,
        date=None,
        cut_to_top=cut_to_top,
        preliminary_rounds=len(rounds),
        players=players,
        rounds=rounds,
        fetched_at=FETCHED_AT,
        stale=stale,
        elimination_players=elimination_players,
    )
