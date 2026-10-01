from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.models import Player
from cobra_bot.domain.search import SearchResult, normalize, search_players

type LoadRaw = Callable[[str], object]


def _players(raw_fixture: LoadRaw, name: str) -> tuple[Player, ...]:
    fetched_at = datetime(2026, 10, 1, tzinfo=UTC)
    return parse_tournament(
        raw_fixture(name), tournament_id=1, fetched_at=fetched_at
    ).players


def _player(pid: int, name: str, rank: int) -> Player:
    return Player(pid, name, rank, 0, Decimal(0), Decimal(0), None, None, None, None)


def test_ac09_substring_in_different_case_finds_one_player(
    raw_fixture: LoadRaw,
) -> None:
    """Player 1017 is Player0017 in single_sided_top8."""
    result = search_players(_players(raw_fixture, "single_sided_top8"), "LAYER0017")

    assert [(p.id, p.rank) for p in result.matches] == [(1017, 2)]
    assert result.more == 0


def test_ac10_more_than_three_matches(raw_fixture: LoadRaw) -> None:
    players = _players(raw_fixture, "single_sided_top8")
    pseudonymous = sorted(
        (p for p in players if p.name.startswith("Player")), key=lambda p: p.rank
    )

    result = search_players(players, "player")

    assert result.matches == tuple(pseudonymous[:3])
    assert result.more == len(pseudonymous) - 3


def test_ac11_no_match(raw_fixture: LoadRaw) -> None:
    result = search_players(_players(raw_fixture, "single_sided_top8"), "nobody")

    assert result == SearchResult(matches=(), more=0)


@pytest.mark.parametrize(("query", "name"), [("maelig", "Maëlig"), ("ZOLW", "Żółw")])
def test_ac12_diacritics_are_ignored(
    raw_fixture: LoadRaw, query: str, name: str
) -> None:
    result = search_players(_players(raw_fixture, "dss"), query)

    assert [p.name for p in result.matches] == [name]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Żółw", "zolw"),
        ("Maëlig", "maelig"),
        ("ŁÓDŹ", "lodz"),
        ("Øyvind", "oyvind"),
        ("Đorđe", "dorde"),
        ("Straße", "strasse"),
        ("Æsir Œuvre", "aesir oeuvre"),
        ("ﬁnal", "final"),  # NFKD compatibility ligature
        ("*bold_name~", "*bold_name~"),
    ],
)
def test_normalize(text: str, expected: str) -> None:
    assert normalize(text) == expected


def test_matches_are_ordered_by_rank_and_limited() -> None:
    players = [
        _player(i, f"Anna {i}", rank) for i, rank in [(1, 5), (2, 1), (3, 3), (4, 2)]
    ]

    result = search_players(players, "anna", limit=2)

    assert [p.id for p in result.matches] == [2, 4]
    assert result.more == 2


@pytest.mark.parametrize("query", ["", "   ", "́"])
def test_empty_query_matches_nobody(query: str) -> None:
    assert search_players([_player(1, "Anna", 1)], query) == SearchResult((), 0)
