from collections.abc import Callable

import pytest

from builders import (
    FETCHED_AT,
    FETCHED_AT_TAG,
    pairing,
    plain,
    player,
    seat,
    tournament,
)
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.models import Tournament
from cobra_bot.domain.rounds import StandingsView, standings_view
from cobra_bot.formatting.standings import format_standings, standings_row
from cobra_bot.formatting.text import display_width

type LoadRaw = Callable[[str], object]

ESC = chr(0x1B)
PRIMARY, STRONG, SECONDARY = f"{ESC}[0m", f"{ESC}[0m{ESC}[1m", f"{ESC}[0;37m"
SCORE, CORP, RUNNER = f"{ESC}[1;33m", f"{ESC}[0;34m", f"{ESC}[0;35m"


def _view(t: Tournament) -> StandingsView:
    view = standings_view(t)
    assert isinstance(view, StandingsView)
    return view


def _lines(text: str) -> list[str]:
    return plain(text).split("\n")


def _round_one(*players: object) -> Tournament:
    return tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),),
        players=players,  # type: ignore[arg-type]
    )


def test_ac01_finished_tournament(raw_fixture: LoadRaw) -> None:
    t = parse_tournament(
        raw_fixture("single_sided_top8"), tournament_id=4909, fetched_at=FETCHED_AT
    )
    doc = format_standings(t, _view(t))

    assert doc.header == (
        "**Standings after round 8**",
        "-# Top 8 cut finished — see `/cobra top-cut` and `/cobra bracket`",
        f"Data from {FETCHED_AT_TAG}",
    )
    assert _lines(doc.entries[0].text) == [
        " 1. Player0042      22",
        "    Nuvem        1.821",
        "    Arissana",
    ]
    assert len(doc.entries) == 46
    assert doc.url == (
        "https://tournaments.nullsignal.games/tournaments/4909/players/standings"
    )
    assert doc.footer == (
        "Round 8 · 46 players · Corp + SoS on line 2, Runner on line 3"
    )


def test_ac08_no_completed_round_lists_players_in_rank_order() -> None:
    players = (player(10, "Bob", rank=2), player(11, "Alice", rank=1))
    t = tournament((pairing(1, seat(10, "corp"), seat(11, "runner")),), players=players)
    doc = format_standings(t, _view(t))

    assert doc.header[0] == "**No completed rounds yet**"
    assert [plain(e.text).split()[1] for e in doc.entries] == ["Alice", "Bob"]
    assert doc.footer == "2 players · Corp + SoS on line 2, Runner on line 3"


def test_no_column_headings() -> None:
    """S-2: the table starts with the first player."""
    t = _round_one(player(1, rank=1), player(2, rank=2))

    doc = format_standings(t, _view(t))

    assert plain(doc.entries[0].text).startswith(" 1. ")


def test_row_layout_and_colours() -> None:
    """S-1, S-2: rank, bold name, yellow points; blue Corp, grey SoS; pink Runner.
    Every line ends with a reset (A-0)."""
    p = player(
        1,
        "Alice",
        rank=1,
        points=22,
        sos="1.821",
        corp="Nuvem SA: Law of the Land",
        runner="Arissana Rocha Nahu: Street Artist",
    )

    assert standings_row(p).split("\n") == [
        f"{PRIMARY} 1. {STRONG}Alice          {SCORE} 22{PRIMARY}",
        f"    {CORP}Nuvem        {SECONDARY}1.821{PRIMARY}",
        f"    {RUNNER}Arissana{PRIMARY}",
    ]


def test_longest_lines_are_22_columns() -> None:
    """C-5: a 15-column name with 2-digit points; a 9-column Corp ID with SoS."""
    p = player(1, "A" * 15, rank=99, points=22, sos="1.5", corp="Earth Station: X")

    assert [display_width(line) for line in _lines(standings_row(p))] == [22, 22, 5]


def test_sos_ends_under_the_points() -> None:
    """S-1: the SoS is right-aligned to the end of the points."""
    first, second, _ = _lines(standings_row(player(1, points=9, sos="2.25")))

    assert len(first) == len(second) == 22


def test_sos_is_shown_with_three_decimals() -> None:
    assert _lines(standings_row(player(1, sos="3.75")))[1].endswith(" 3.750")
    assert _lines(standings_row(player(1, sos="0")))[1].endswith(" 0.000")


def test_missing_identities_show_a_secondary_dash() -> None:
    """A-4."""
    row = standings_row(player(1, "Bob", rank=12))

    assert _lines(row)[1:] == ["    —            0.000", "    —"]
    assert row.split("\n")[1:] == [
        f"    {SECONDARY}—            {SECONDARY}0.000{PRIMARY}",
        f"    {SECONDARY}—{PRIMARY}",
    ]


def test_names_are_literal_in_the_code_block() -> None:
    """AC-21 data: markdown is not escaped inside a code block."""
    assert " *bold_name~ " in plain(standings_row(player(1, "*bold_name~")))


@pytest.mark.parametrize(
    ("length", "shown"),
    [(14, "A" * 14 + " "), (15, "A" * 15), (16, "A" * 14 + "…")],
    ids=["below-limit", "at-limit", "one-above"],
)
def test_long_names_are_cut_to_15_columns(length: int, shown: str) -> None:
    """C-7: names longer than 15 columns become 14 columns plus `…`."""
    row = _lines(standings_row(player(1, "A" * length, points=22)))[0]

    assert row == f" 1. {shown} 22"


def test_wide_characters_keep_the_columns_aligned() -> None:
    """C-5: padding counts display width, not characters."""
    emoji = chr(0x1F600)
    row = _lines(standings_row(player(1, f"{emoji}Ace", points=22)))[0]

    assert row == f" 1. {emoji}Ace{' ' * 10} 22"


def test_blank_line_between_point_groups() -> None:
    """S-5."""
    t = _round_one(
        player(1, rank=1, points=6),
        player(2, rank=2, points=3),
        player(3, rank=3, points=3),
        player(4, rank=4, points=0),
    )

    doc = format_standings(t, _view(t))

    assert [e.gap for e in doc.entries] == [False, True, False, True]


def test_two_digit_ranks_keep_the_narrow_column() -> None:
    """S-3 boundary: rank 99 does not widen the column."""
    t = _round_one(*(player(i, rank=i) for i in range(1, 100)))

    doc = format_standings(t, _view(t))

    assert _lines(doc.entries[0].text)[0] == " 1. Player1          0"
    assert _lines(doc.entries[-1].text)[0] == "99. Player99         0"


def test_three_digit_ranks_widen_the_rank_column() -> None:
    """S-3: for the whole table, the ID lines included; the name column gives up
    the column, so lines stay within 22 (C-5)."""
    t = _round_one(*(player(i, rank=i) for i in range(1, 101)))

    doc = format_standings(t, _view(t))

    assert _lines(doc.entries[0].text) == [
        "  1. Player1         0",
        "     —           0.000",
        "     —",
    ]
    assert _lines(doc.entries[-1].text)[0] == "100. Player100       0"


def test_three_digit_ranks_cut_names_at_14_columns() -> None:
    """S-3, C-5: with a 3-column rank, names longer than 14 columns are cut."""
    p = player(1, "A" * 15, rank=100, points=22)

    assert _lines(standings_row(p, 3))[0] == f"100. {'A' * 13}… 22"


def test_stale_private_notice() -> None:
    t = tournament((pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), stale=True)

    doc = format_standings(t, _view(t), private=True)

    assert doc.header == (
        "**Standings after round 1**",
        "-# No top cut on Cobra yet",
        f"Tournament is now private — data from {FETCHED_AT_TAG}",
    )


def test_ac26_registration_header() -> None:
    t = tournament(players=(player(1, "Ann"), player(2, "Bob")))
    view = standings_view(t)
    assert isinstance(view, StandingsView)

    doc = format_standings(t, view)

    assert doc.header[0] == "**Registered players — not started yet**"


# --- the top cut's state -------------------------------------------------------------


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
    from cobra_bot import messages

    assert messages.cut_note(status, 16) == note


def test_cut_note_sits_between_the_title_and_the_data_line() -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),),
        players=(player(1, rank=1, points=3), player(2, rank=2)),
        cut_to_top=2,
    )

    doc = format_standings(t, _view(t))

    assert doc.header == (
        "**Standings after round 1**",
        "-# Top 2 cut announced — not started yet",
        f"Data from {FETCHED_AT_TAG}",
    )


def test_no_cut_note_while_a_round_is_played() -> None:
    t = tournament((pairing(1, seat(1, "corp"), seat(2, "runner")),))

    doc = format_standings(t, _view(t))

    assert doc.header == ("**No completed rounds yet**", f"Data from {FETCHED_AT_TAG}")
