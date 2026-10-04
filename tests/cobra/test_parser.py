from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from cobra_bot.cobra.parser import ParseError, parse_tournament
from cobra_bot.domain.models import EliminationPlayer, Pairing, Seat, Tournament

FETCHED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

type LoadRaw = Callable[[str], object]


def _parse(raw: object, *, stale: bool = False) -> Tournament:
    return parse_tournament(raw, tournament_id=4909, fetched_at=FETCHED_AT, stale=stale)


def _pairing(t: Tournament, round_number: int, table: int) -> Pairing:
    return next(p for p in t.rounds[round_number - 1] if p.table == table)


@pytest.mark.parametrize(
    ("name", "players", "rounds"),
    [
        ("single_sided_top8", 46, 14),
        ("large_top_cut", 235, 19),
        ("dss", 31, 3),
        ("not_started", 0, 0),
    ],
)
def test_player_and_round_counts(
    raw_fixture: LoadRaw, name: str, players: int, rounds: int
) -> None:
    t = _parse(raw_fixture(name))

    assert (len(t.players), len(t.rounds)) == (players, rounds)


def test_tournament_fields(raw_fixture: LoadRaw) -> None:
    t = _parse(raw_fixture("single_sided_top8"), stale=True)

    assert (t.id, t.name, t.date) == (
        4909,
        "Single-Sided Top 8 Fixture",
        date(2000, 1, 1),
    )
    assert (t.cut_to_top, t.preliminary_rounds) == (8, 8)
    assert (t.fetched_at, t.stale) == (FETCHED_AT, True)


def test_player_fields(raw_fixture: LoadRaw) -> None:
    t = _parse(raw_fixture("single_sided_top8"))
    player = t.player(1042)

    assert player is not None
    assert (player.rank, player.match_points) == (1, 22)
    assert isinstance(player.sos, Decimal)
    assert player.name == "Player0042"


def test_integer_sos_is_accepted(raw_fixture: LoadRaw) -> None:
    """large_top_cut has some SoS values as JSON numbers, not strings."""
    t = _parse(raw_fixture("large_top_cut"))

    assert all(isinstance(p.sos, Decimal) for p in t.players)


def test_single_sided_bye(raw_fixture: LoadRaw) -> None:
    """AC-02 data: round 1, table 21 is a bye for player 1023."""
    pairing = _pairing(_parse(raw_fixture("single_sided_top8")), 1, 21)

    assert pairing.is_bye
    assert pairing.player_ids == (1023,)
    assert (pairing.seat2.player_id, pairing.seat2.role) == (None, None)


def test_single_sided_game_has_roles(raw_fixture: LoadRaw) -> None:
    pairing = _pairing(_parse(raw_fixture("single_sided_top8")), 1, 1)

    assert {pairing.seat1.role, pairing.seat2.role} == {"corp", "runner"}
    assert not pairing.double_sided
    assert pairing.seat1.combined_score is not None


def test_intentional_draw(raw_fixture: LoadRaw) -> None:
    t = _parse(raw_fixture("single_sided_top8"))
    draws = [p for p in t.rounds[7] if p.intentional_draw]

    assert len(draws) == 2
    assert all(p.seat1.combined_score == 1 == p.seat2.combined_score for p in draws)


def test_elimination_game(raw_fixture: LoadRaw) -> None:
    t = _parse(raw_fixture("single_sided_top8"))
    pairing = t.rounds[8][0]

    assert pairing.elimination
    assert {pairing.seat1.winner, pairing.seat2.winner} == {True, False}
    assert pairing.seat1.combined_score is None
    assert not pairing.double_sided


def test_double_sided_pairing(raw_fixture: LoadRaw) -> None:
    """AC-22 data: each seat carries the player's Corp and Runner game; no role."""
    pairing = next(p for p in _parse(raw_fixture("dss")).rounds[0] if not p.is_bye)

    assert pairing.double_sided
    for seat in (pairing.seat1, pairing.seat2):
        assert seat.role is None
        assert seat.corp_score is not None
        assert seat.runner_score is not None
        assert seat.combined_score == seat.corp_score + seat.runner_score


def test_bye_in_player1_slot(raw_fixture: LoadRaw) -> None:
    """docs/spec/cobra.md: in dss round 2 the bye has player1.id == null."""
    pairing = _pairing(_parse(raw_fixture("dss")), 2, 16)

    assert pairing.is_bye
    assert pairing.seat1.player_id is None
    assert len(pairing.player_ids) == 1
    assert not pairing.double_sided


def test_unreported_double_sided_scores_are_none(raw_fixture: LoadRaw) -> None:
    """docs/spec/cobra.md: unreported results are null; round 3 of dss is unreported."""
    pairing = next(p for p in _parse(raw_fixture("dss")).rounds[2] if not p.is_bye)

    assert pairing.seat1 == Seat(pairing.seat1.player_id, None, None, None, None, None)


def _minimal(**player: object) -> dict[str, object]:
    return {
        "name": "T",
        "players": [{"id": 1, "rank": 1, **player}],
        "rounds": [
            [{"table": "3", "player1": {"id": 1, "combinedScore": "3"}, "player2": {}}]
        ],
    }


def test_numbers_as_strings_and_missing_optionals() -> None:
    t = _parse(_minimal(matchPoints="6", strengthOfSchedule="1.25"))
    player = t.players[0]
    pairing = t.rounds[0][0]

    assert (player.match_points, player.sos, player.esos) == (
        6,
        Decimal("1.25"),
        Decimal(0),
    )
    assert (player.name, player.corp_identity) == ("", None)
    assert (pairing.table, pairing.seat1.combined_score) == (3, 3)
    assert (pairing.intentional_draw, pairing.elimination) == (False, False)
    assert t.date is None


def test_unknown_keys_are_ignored() -> None:
    raw = _minimal(nickname="x")
    raw["description"] = "free text"

    assert len(_parse(raw).players) == 1


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param([], id="not-an-object"),
        pytest.param({"players": {}}, id="players-not-a-list"),
        pytest.param({"players": [{"rank": 1}]}, id="player-without-id"),
        pytest.param({"players": [{"id": "x", "rank": 1}]}, id="non-numeric-id"),
        pytest.param({"players": [{"id": True, "rank": 1}]}, id="boolean-id"),
        pytest.param(
            {"players": [{"id": 1, "rank": 1, "strengthOfSchedule": "abc"}]},
            id="bad-sos",
        ),
        pytest.param({"rounds": [[{"player1": {}, "player2": {}}]]}, id="no-table"),
        pytest.param({"rounds": [[{"table": 1, "player1": {}}]]}, id="missing-seat"),
    ],
)
def test_malformed_exports_raise_parse_error(raw: object) -> None:
    with pytest.raises(ParseError):
        _parse(raw)


# --- eliminationPlayers (the cut ranking) ------------------------------------------


def _export(*entries: object) -> dict[str, object]:
    return {"players": [], "rounds": [], "eliminationPlayers": list(entries)}


def test_elimination_players_of_a_finished_cut(raw_fixture: LoadRaw) -> None:
    t = _parse(raw_fixture("single_sided_top8"))

    assert len(t.elimination_players) == 8
    assert t.elimination_players[0] == EliminationPlayer(rank=1, player_id=1017, seed=2)


def test_undecided_cut_places_have_no_player() -> None:
    """Cobra's export while the cut is played: `id`, `name`, `seed` null."""
    t = _parse(_export({"id": None, "name": None, "rank": 1, "seed": None}))

    assert t.elimination_players == (EliminationPlayer(1, None, None),)


def test_elimination_players_are_kept_in_rank_order() -> None:
    t = _parse(
        _export(
            {"id": 7, "rank": 2, "seed": 1},
            {"id": 8, "rank": 1, "seed": "2"},
        )
    )

    assert [(e.rank, e.player_id, e.seed) for e in t.elimination_players] == [
        (1, 8, 2),
        (2, 7, 1),
    ]


def test_missing_elimination_players_is_an_empty_ranking() -> None:
    assert _parse({"players": [], "rounds": []}).elimination_players == ()


@pytest.mark.parametrize(
    "entry",
    [
        {"id": 1, "seed": 1},  # no rank
        {"id": 1, "rank": "first", "seed": 1},
        {"id": "x", "rank": 1, "seed": 1},
        {"id": 1, "rank": 1, "seed": True},
        "not an object",
    ],
    ids=["no-rank", "bad-rank", "bad-id", "bool-seed", "not-an-object"],
)
def test_malformed_elimination_player_is_a_parse_error(entry: object) -> None:
    with pytest.raises(ParseError, match="eliminationPlayers"):
        _parse(_export(entry))
