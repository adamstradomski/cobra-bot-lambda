"""Raw Cobra JSON export -> domain models (SPEC §4).

Tolerant by design (the export is not an official API): unknown keys are
ignored, numbers may arrive as strings, optional fields may be missing.
`ParseError` is raised only when something the bot cannot work without is
missing or malformed (player IDs, ranks, pairing tables, the overall shape).
"""

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from cobra_bot import messages
from cobra_bot.domain.models import (
    EliminationPlayer,
    Pairing,
    Player,
    Role,
    Round,
    Seat,
    Tournament,
)

ROLES: dict[object, Role] = {"corp": "corp", "runner": "runner"}


class ParseError(ValueError):
    """The export does not have the expected shape."""


def parse_tournament(
    raw: object, *, tournament_id: int, fetched_at: datetime, stale: bool = False
) -> Tournament:
    top = _mapping(raw, "export")
    return Tournament(
        id=tournament_id,
        name=_str(top.get("name")) or messages.tournament_fallback_name(tournament_id),
        date=_date(top.get("date")),
        cut_to_top=_opt_int(top.get("cutToTop"), "cutToTop") or 0,
        preliminary_rounds=_opt_int(top.get("preliminaryRounds"), "preliminaryRounds")
        or 0,
        players=tuple(
            _player(p, f"players[{i}]")
            for i, p in enumerate(_list(top.get("players"), "players"))
        ),
        rounds=tuple(
            _round(r, f"rounds[{i}]")
            for i, r in enumerate(_list(top.get("rounds"), "rounds"))
        ),
        fetched_at=fetched_at,
        stale=stale,
        elimination_players=tuple(
            sorted(
                (
                    _elimination_player(e, f"eliminationPlayers[{i}]")
                    for i, e in enumerate(
                        _list(top.get("eliminationPlayers"), "eliminationPlayers")
                    )
                ),
                key=lambda e: e.rank,
            )
        ),
    )


def _player(raw: object, where: str) -> Player:
    obj = _mapping(raw, where)
    return Player(
        id=_int(obj.get("id"), f"{where}.id"),
        name=_str(obj.get("name")) or "",
        rank=_int(obj.get("rank"), f"{where}.rank"),
        match_points=_opt_int(obj.get("matchPoints"), f"{where}.matchPoints") or 0,
        sos=_decimal(obj.get("strengthOfSchedule"), f"{where}.strengthOfSchedule"),
        esos=_decimal(
            obj.get("extendedStrengthOfSchedule"),
            f"{where}.extendedStrengthOfSchedule",
        ),
        corp_faction=_str(obj.get("corpFaction")),
        corp_identity=_str(obj.get("corpIdentity")),
        runner_faction=_str(obj.get("runnerFaction")),
        runner_identity=_str(obj.get("runnerIdentity")),
    )


def _elimination_player(raw: object, where: str) -> EliminationPlayer:
    """A place in the cut ranking; its player is null until the place is decided
    (Cobra's `nrtm_json.rb`)."""
    obj = _mapping(raw, where)
    return EliminationPlayer(
        rank=_int(obj.get("rank"), f"{where}.rank"),
        player_id=_opt_int(obj.get("id"), f"{where}.id"),
        seed=_opt_int(obj.get("seed"), f"{where}.seed"),
    )


def _round(raw: object, where: str) -> Round:
    return tuple(_pairing(p, f"{where}[{i}]") for i, p in enumerate(_list(raw, where)))


def _pairing(raw: object, where: str) -> Pairing:
    obj = _mapping(raw, where)
    return Pairing(
        table=_int(obj.get("table"), f"{where}.table"),
        seat1=_seat(obj.get("player1"), f"{where}.player1"),
        seat2=_seat(obj.get("player2"), f"{where}.player2"),
        intentional_draw=obj.get("intentionalDraw") is True,
        two_for_one=obj.get("twoForOne") is True,
        elimination=obj.get("eliminationGame") is True,
    )


def _seat(raw: object, where: str) -> Seat:
    obj = _mapping(raw, where)
    winner = obj.get("winner")
    return Seat(
        player_id=_opt_int(obj.get("id"), f"{where}.id"),
        role=ROLES.get(obj.get("role")),
        combined_score=_opt_int(obj.get("combinedScore"), f"{where}.combinedScore"),
        corp_score=_opt_int(obj.get("corpScore"), f"{where}.corpScore"),
        runner_score=_opt_int(obj.get("runnerScore"), f"{where}.runnerScore"),
        winner=winner if isinstance(winner, bool) else None,
    )


# --- value helpers -----------------------------------------------------------


def _mapping(raw: object, where: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise ParseError(f"{where}: expected an object, got {type(raw).__name__}")
    return raw


def _list(raw: object, where: str) -> list[object]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ParseError(f"{where}: expected a list, got {type(raw).__name__}")
    return raw


def _opt_int(raw: object, where: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):  # bool is an int subclass; never a valid number here
        raise ParseError(f"{where}: expected an integer, got {raw!r}")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        return int(raw)
    raise ParseError(f"{where}: expected an integer, got {raw!r}")


def _int(raw: object, where: str) -> int:
    value = _opt_int(raw, where)
    if value is None:
        raise ParseError(f"{where}: missing")
    return value


def _decimal(raw: object, where: str) -> Decimal:
    if raw is None or raw == "":
        return Decimal(0)
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        raise ParseError(f"{where}: expected a number, got {raw!r}")
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        raise ParseError(f"{where}: expected a number, got {raw!r}") from None


def _str(raw: object) -> str | None:
    return raw if isinstance(raw, str) and raw else None


def _date(raw: object) -> date | None:
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None
