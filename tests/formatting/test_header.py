from collections.abc import Callable

import pytest

from builders import FETCHED_AT, FETCHED_AT_TAG, pairing, player, seat, tournament
from cobra_bot import messages
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.models import Player, Tournament
from cobra_bot.domain.rounds import (
    PairingsView,
    StandingsView,
    pairings_view,
    standings_view,
)
from cobra_bot.domain.search import NameResult, NamesResult
from cobra_bot.formatting import header

type LoadRaw = Callable[[str], object]

ALICE = player(1, "Alice", rank=1, points=6)
BOB = player(2, "Bob", rank=2, points=3)
ROUND_1 = (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),)


def _fixture(raw_fixture: LoadRaw, name: str, tid: int = 4909) -> Tournament:
    return parse_tournament(raw_fixture(name), tournament_id=tid, fetched_at=FETCHED_AT)


def _pairings(t: Tournament, requested: int | None = None) -> PairingsView:
    view = pairings_view(t, requested)
    assert isinstance(view, PairingsView)
    return view


def _standings(t: Tournament) -> StandingsView:
    view = standings_view(t)
    assert isinstance(view, StandingsView)
    return view


# --- pairings -----------------------------------------------------------------------


def test_ac03_default_pairings_header_names_the_top_cut_round(
    raw_fixture: LoadRaw,
) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")
    head = header.pairings(t, _pairings(t))

    assert head.lines == (
        "**Top cut round 6 pairings — complete**",
        f"Data from {FETCHED_AT_TAG}",
    )
    assert head.title == "Single-Sided Top 8 Fixture"
    assert head.url == "https://tournaments.nullsignal.games/tournaments/4909"


def test_swiss_round_header(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")

    assert header.pairings(t, _pairings(t, 8)).lines == (
        "**Round 8 pairings — complete**",
        f"Data from {FETCHED_AT_TAG}",
    )


def test_ac07_in_progress_header(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "dss", 5018)

    assert header.pairings(t, _pairings(t)).lines[0] == (
        "**Round 3 pairings — in progress**"
    )


@pytest.mark.parametrize(
    ("private", "line"),
    [
        (False, f"Cobra unavailable — data from {FETCHED_AT_TAG}"),
        (True, f"Tournament is now private — data from {FETCHED_AT_TAG}"),
    ],
)
def test_stale_notice(private: bool, line: str) -> None:
    t = tournament(ROUND_1, players=(ALICE, BOB), stale=True)

    assert header.pairings(t, _pairings(t), private=private).lines[-1] == line


# --- standings ----------------------------------------------------------------------


def test_ac01_finished_tournament_header(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")
    head = header.standings(t, _standings(t))

    assert head.lines == (
        "**Standings after round 8**",
        "-# Top 8 cut finished — see `/cobra top-cut` and `/cobra bracket`",
        f"Data from {FETCHED_AT_TAG}",
    )
    assert head.url == (
        "https://tournaments.nullsignal.games/tournaments/4909/players/standings"
    )


def test_ac08_no_completed_round_header() -> None:
    t = tournament((pairing(1, seat(1, "corp"), seat(2, "runner")),))

    assert header.standings(t, _standings(t)).lines == (
        "**No completed rounds yet**",
        f"Data from {FETCHED_AT_TAG}",
    )


def test_ac26_registration_header() -> None:
    t = tournament(players=(player(1, "Ann"), player(2, "Bob")))

    assert header.standings(t, _standings(t)).lines[0] == (
        "**Registered players — not started yet**"
    )


def test_stale_private_notice() -> None:
    t = tournament(ROUND_1, stale=True)

    assert header.standings(t, _standings(t), private=True).lines == (
        "**Standings after round 1**",
        "-# No top cut on Cobra yet",
        f"Tournament is now private — data from {FETCHED_AT_TAG}",
    )


@pytest.mark.parametrize(
    ("status", "note"),
    [
        ("none", "No top cut on Cobra yet"),
        ("announced", "Top 16 cut announced — not started yet"),
        (
            "in_progress",
            "Top 16 cut in progress — see `/cobra top-cut` and `/cobra bracket`",
        ),
        ("finished", "Top 16 cut finished — see `/cobra top-cut` and `/cobra bracket`"),
    ],
)
def test_cut_note_per_status(status: str, note: str) -> None:
    assert messages.cut_note(status, 16) == note


def test_cut_note_sits_between_the_title_and_the_data_line() -> None:
    t = tournament(
        ROUND_1, players=(player(1, rank=1, points=3), player(2, rank=2)), cut_to_top=2
    )

    assert header.standings(t, _standings(t)).lines == (
        "**Standings after round 1**",
        "-# Top 2 cut announced — not started yet",
        f"Data from {FETCHED_AT_TAG}",
    )


# --- players ------------------------------------------------------------------------


def _result(*players: Player, more: int = 0) -> NamesResult:
    """One name that matched `players` and `more` not shown."""
    return NamesResult(
        matches=players, names=(NameResult("q", len(players) + more, more),), skipped=0
    )


def _names(*names: tuple[str, int, int], skipped: int = 0) -> NamesResult:
    return NamesResult(
        matches=(ALICE,), names=tuple(NameResult(*n) for n in names), skipped=skipped
    )


def _t() -> Tournament:
    return tournament(ROUND_1, players=(ALICE, BOB))


def test_players_header_names_the_query() -> None:
    head = header.players(_t(), _result(ALICE), "ali")

    assert head.lines == ("**Players matching “ali”**", f"Data from {FETCHED_AT_TAG}")
    assert head.notes == ()
    assert head.url == "https://tournaments.nullsignal.games/tournaments/1"


def test_more_matches_note() -> None:
    head = header.players(_t(), _result(ALICE, BOB, more=4), "a")

    assert head.notes == ("…and 4 more matched",)


def test_no_match() -> None:
    """AC-11 output."""
    assert header.players(_t(), _result(), "nobody").notes == ("No players match.",)


def test_query_is_escaped() -> None:
    head = header.players(_t(), _result(), "*x_")

    assert head.lines[0] == "**Players matching “\\*x\\_”**"


def test_several_names_note_each_name_without_a_match() -> None:
    head = header.players(_t(), _names(("ali", 1, 0), ("zed", 0, 0)), "ali, zed")

    assert head.notes == ("No players match “zed”.",)


def test_several_names_note_each_name_with_more_matches() -> None:
    head = header.players(_t(), _names(("ali", 1, 0), ("player", 7, 4)), "q")

    assert head.notes == ("…and 4 more matched “player”",)


def test_several_names_are_escaped_in_notes() -> None:
    head = header.players(_t(), _names(("ali", 1, 0), ("*x_", 0, 0)), "q")

    assert head.notes == (r"No players match “\*x\_”.",)


def test_names_past_the_limit_are_reported() -> None:
    head = header.players(_t(), _names(("ali", 1, 0), skipped=2), "q")

    assert head.notes == ("Only the first 10 names were searched (2 more given).",)


def test_one_name_keeps_the_single_name_notes() -> None:
    result = NamesResult(matches=(), names=(NameResult("zed", 0, 0),), skipped=0)

    assert header.players(_t(), result, "zed").notes == ("No players match.",)
