from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.models import Player
from cobra_bot.domain.search import (
    MAX_NAMES,
    SearchResult,
    normalize,
    search_names,
    search_players,
    split_names,
)

type LoadRaw = Callable[[str], object]


def _players(raw_fixture: LoadRaw, name: str) -> tuple[Player, ...]:
    fetched_at = datetime(2026, 10, 1, tzinfo=UTC)
    return parse_tournament(
        raw_fixture(name), tournament_id=1, fetched_at=fetched_at
    ).players


def _player(pid: int, name: str, rank: int) -> Player:
    return Player(pid, name, rank, 0, Decimal(0), Decimal(0), None, None, None, None)


@pytest.mark.req("FR-09", "AC-09")
def test_ac09_substring_in_different_case_finds_one_player(
    raw_fixture: LoadRaw,
) -> None:
    """Player 1017 is Player0017 in single_sided_top8."""
    result = search_players(_players(raw_fixture, "single_sided_top8"), "LAYER0017")

    assert [(p.id, p.rank) for p in result.matches] == [(1017, 2)]
    assert result.more == 0


@pytest.mark.req("FR-10", "AC-10")
def test_ac10_more_than_three_matches(raw_fixture: LoadRaw) -> None:
    players = _players(raw_fixture, "single_sided_top8")
    pseudonymous = sorted(
        (p for p in players if p.name.startswith("Player")), key=lambda p: p.rank
    )

    result = search_players(players, "player")

    assert result.matches == tuple(pseudonymous[:3])
    assert result.more == len(pseudonymous) - 3


@pytest.mark.req("AC-11")
def test_ac11_no_match(raw_fixture: LoadRaw) -> None:
    result = search_players(_players(raw_fixture, "single_sided_top8"), "nobody")

    assert result == SearchResult(matches=(), more=0)


@pytest.mark.req("FR-09", "AC-12")
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


@pytest.mark.req("FR-10")
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


# --- several names ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "names"),
    [
        ("Alice", ["Alice"]),
        ("Alice, Bob", ["Alice", "Bob"]),
        ("Alice;Bob", ["Alice", "Bob"]),  # semicolon too
        ("  Alice  ,   Bob  ", ["Alice", "Bob"]),  # trimmed
        ("Ann  Lee, Bob", ["Ann Lee", "Bob"]),  # inner spaces collapse
        ("Alice,,Bob,", ["Alice", "Bob"]),  # empty names dropped
        ("Żółw, zolw, ZÓŁW", ["Żółw"]),  # repeats (ignoring case and diacritics)
        (",  ,", []),
        ("", []),
    ],
)
def test_split_names(query: str, names: list[str]) -> None:
    assert split_names(query) == names


def _roster() -> list[Player]:
    return [
        _player(1, "Alice", 3),
        _player(2, "Alicja", 1),
        _player(3, "Bob", 2),
        _player(4, "Carol", 4),
    ]


@pytest.mark.req("FR-09", "AC-27")
def test_several_names_union_in_rank_order_once_each() -> None:
    """AC-27: a player matched by two names gets one card, in rank order."""
    result = search_names(_roster(), "bob, ali, alice")

    assert [p.id for p in result.matches] == [2, 3, 1]  # Alice once
    assert [(n.name, n.found, n.more) for n in result.names] == [
        ("bob", 1, 0),
        ("ali", 2, 0),
        ("alice", 1, 0),
    ]
    assert result.skipped == 0


def test_each_name_keeps_its_own_limit() -> None:
    result = search_names(_roster(), "a, bob", limit=1)

    assert [(n.name, n.found, n.more) for n in result.names] == [
        ("a", 3, 2),
        ("bob", 1, 0),
    ]
    assert [p.id for p in result.matches] == [2, 3]


def test_name_without_a_match_is_reported_not_dropped() -> None:
    """AC-27: "No players match “zed”." is built from this."""
    result = search_names(_roster(), "bob, zed")

    assert [(n.name, n.found) for n in result.names] == [("bob", 1), ("zed", 0)]


@pytest.mark.req("AC-27")
@pytest.mark.parametrize(("given", "skipped"), [(9, 0), (10, 0), (11, 1), (13, 3)])
def test_at_most_ten_names_are_searched(given: int, skipped: int) -> None:
    """AC-27: names past the tenth are counted, not searched."""
    query = ", ".join(f"name{n}" for n in range(given))

    result = search_names(_roster(), query)

    assert len(result.names) == min(given, MAX_NAMES) == min(given, 10)
    assert result.skipped == skipped
