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
from cobra_bot.formatting.standings import (
    format_standings,
    standings_columns,
    standings_row,
)

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


def test_ac01_finished_tournament(raw_fixture: LoadRaw) -> None:
    t = parse_tournament(
        raw_fixture("single_sided_top8"), tournament_id=4909, fetched_at=FETCHED_AT
    )
    doc = format_standings(t, _view(t))

    assert doc.header == ("**Standings after round 8**", f"Data from {FETCHED_AT_TAG}")
    assert _lines(doc.entries[0].text) == [
        " 1 Player0042       22  1.821",
        "   Nuvem · Arissana",
    ]
    assert len(doc.entries) == 46
    assert doc.url == (
        "https://tournaments.nullsignal.games/tournaments/4909/players/standings"
    )
    assert doc.footer == "Round 8 · 46 players · Corp · Runner on 2nd line"


def test_ac08_no_completed_round_lists_players_in_rank_order() -> None:
    players = (player(10, "Bob", rank=2), player(11, "Alice", rank=1))
    t = tournament((pairing(1, seat(10, "corp"), seat(11, "runner")),), players=players)
    doc = format_standings(t, _view(t))

    assert doc.header[0] == "**No completed rounds yet**"
    assert [plain(e.text).split()[1] for e in doc.entries] == ["Alice", "Bob"]
    assert doc.footer == "2 players · Corp · Runner on 2nd line"


def test_row_layout_and_colours() -> None:
    """S-1, S-2: rank, bold name, yellow points, grey SoS; then blue Corp, grey
    `·`, pink Runner. Every line ends with a reset (A-0)."""
    p = player(
        1,
        "Alice",
        rank=1,
        points=22,
        sos="1.821",
        corp="Nuvem SA: Law of the Land",
        runner="Arissana Rocha Nahu: Street Artist",
    )

    assert standings_row(p) == (
        f"{PRIMARY} 1 {STRONG}Alice           {SCORE} 22  {SECONDARY}1.821{PRIMARY}\n"
        f"   {CORP}Nuvem{SECONDARY} · {RUNNER}Arissana{PRIMARY}"
    )


def test_header_and_rule_are_secondary() -> None:
    """S-2: the rule is 2 columns wider than the header, as wide as a row."""
    header, rule = standings_columns()

    assert header == f"{SECONDARY} # Player          Pts  SoS{PRIMARY}"
    assert rule == f"{SECONDARY}{'─' * 29}{PRIMARY}"


def test_sos_is_shown_with_three_decimals() -> None:
    assert _lines(standings_row(player(1, sos="3.75")))[0].endswith("  3.750")
    assert _lines(standings_row(player(1, sos="0")))[0].endswith("  0.000")


def test_missing_identities_show_a_secondary_dash() -> None:
    """A-4."""
    row = standings_row(player(1, "Bob", rank=12))

    assert _lines(row)[1] == "   — · —"
    assert row.split("\n")[1] == f"   {SECONDARY}—{SECONDARY} · {SECONDARY}—{PRIMARY}"


def test_names_are_literal_in_the_code_block() -> None:
    """AC-21 data: markdown is not escaped inside a code block."""
    assert " *bold_name~ " in plain(standings_row(player(1, "*bold_name~")))


@pytest.mark.parametrize(
    ("length", "shown"),
    [(14, "A" * 14 + "  "), (15, "A" * 15 + " "), (16, "A" * 14 + "… ")],
    ids=["below-limit", "at-limit", "one-above"],
)
def test_long_names_are_cut_to_15_columns(length: int, shown: str) -> None:
    """C-7: names longer than 15 columns become 14 columns plus `…`."""
    row = _lines(standings_row(player(1, "A" * length, points=22)))[0]

    assert row == f" 1 {shown} 22  0.000"


def test_wide_characters_keep_the_columns_aligned() -> None:
    """C-5: padding counts display width, not characters."""
    emoji = chr(0x1F600)
    row = _lines(standings_row(player(1, f"{emoji}Ace", points=22)))[0]

    assert row == f" 1 {emoji}Ace{' ' * 11} 22  0.000"


def test_blank_line_between_point_groups() -> None:
    """S-5."""
    players = (
        player(1, rank=1, points=6),
        player(2, rank=2, points=3),
        player(3, rank=3, points=3),
        player(4, rank=4, points=0),
    )
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=players
    )

    doc = format_standings(t, _view(t))

    assert [e.gap for e in doc.entries] == [False, True, False, True]


def test_three_digit_ranks_widen_the_rank_column() -> None:
    """S-3: for the whole table, including the header, rule and ID lines."""
    players = tuple(player(i, rank=i) for i in range(1, 101))
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=players
    )

    doc = format_standings(t, _view(t))

    assert plain(doc.columns[0]) == "  # Player          Pts  SoS"
    assert plain(doc.columns[1]) == "─" * 30
    assert _lines(doc.entries[0].text) == [
        "  1 Player1           0  0.000",
        "    — · —",
    ]
    assert _lines(doc.entries[-1].text)[0].startswith("100 Player100 ")


def test_stale_private_notice() -> None:
    t = tournament((pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), stale=True)

    doc = format_standings(t, _view(t), private=True)

    assert doc.header == (
        "**Standings after round 1**",
        f"Tournament is now private — data from {FETCHED_AT_TAG}",
    )
