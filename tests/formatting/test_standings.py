from collections.abc import Callable

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


def _view(t: Tournament) -> StandingsView:
    view = standings_view(t)
    assert isinstance(view, StandingsView)
    return view


def test_ac01_finished_tournament(raw_fixture: LoadRaw) -> None:
    t = parse_tournament(
        raw_fixture("single_sided_top8"), tournament_id=4909, fetched_at=FETCHED_AT
    )
    doc = format_standings(t, _view(t))

    assert doc.header == ("**Standings after round 8**", f"Data from {FETCHED_AT_TAG}")
    assert plain(doc.entries[0].text).startswith(" 1  Player0042       22  ")
    assert len(doc.entries) == 46
    assert doc.url == (
        "https://tournaments.nullsignal.games/tournaments/4909/players/standings"
    )
    assert doc.footer == "Round 8 · 46 players · Pts / SoS / Corp / Runner"


def test_ac08_no_completed_round_lists_players_in_rank_order() -> None:
    players = (player(10, "Bob", rank=2), player(11, "Alice", rank=1))
    t = tournament((pairing(1, seat(10, "corp"), seat(11, "runner")),), players=players)
    doc = format_standings(t, _view(t))

    assert doc.header[0] == "**No completed rounds yet**"
    assert [plain(e.text).split()[1] for e in doc.entries] == ["Alice", "Bob"]
    assert doc.footer == "2 players · Pts / SoS / Corp / Runner"


def test_row_format() -> None:
    """Column layout and colours as in the design."""
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
        f"{ESC}[0;37m 1  {ESC}[1mAlice           {ESC}[1;33m 22  "
        f"{ESC}[0;37m1.821  {ESC}[0;34mNuvem     {ESC}[0;35mArissana{ESC}[0m"
    )


def test_columns() -> None:
    heading, rule = standings_columns()

    assert heading == (
        f"{ESC}[1;37m #  Player          Pts  SoS    Corp      Runner{ESC}[0m"
    )
    assert plain(rule) == "─" * 51


def test_sos_is_shown_with_three_decimals() -> None:
    assert " 3.750  " in plain(standings_row(player(1, sos="3.75")))
    assert " 0.000  " in plain(standings_row(player(1, sos="0")))


def test_missing_identities_show_placeholder() -> None:
    assert plain(standings_row(player(1, "Bob", rank=12))).endswith("—         —")


def test_names_are_literal_in_the_code_block() -> None:
    """AC-21 data: markdown is not escaped inside a code block."""
    assert " *bold_name~ " in plain(standings_row(player(1, "*bold_name~")))


def test_long_name_is_cut_to_the_column() -> None:
    """C-7: names longer than 16 columns become 15 columns plus `…`."""
    at_limit = plain(standings_row(player(1, "A" * 16, points=22)))
    over = plain(standings_row(player(1, "A" * 17, points=22)))

    assert f" {'A' * 16} 22  " in at_limit
    assert f" {'A' * 15}… 22  " in over


def test_wide_characters_keep_the_columns_aligned() -> None:
    """C-6 / acceptance 4: padding counts display width, not characters."""
    emoji = chr(0x1F600)
    row = plain(standings_row(player(1, f"{emoji}Ace", points=22)))

    assert row.startswith(f" 1  {emoji}Ace{' ' * 11} 22  ")


def test_blank_line_between_point_groups() -> None:
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
    players = tuple(player(i, rank=i) for i in range(1, 101))
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=players
    )

    doc = format_standings(t, _view(t))

    assert plain(doc.columns[0]).startswith("  #  Player")
    assert plain(doc.entries[0].text).startswith("  1  Player1 ")
    assert plain(doc.entries[-1].text).startswith("100  Player100 ")
    assert plain(doc.columns[1]) == "─" * 52


def test_stale_private_notice() -> None:
    t = tournament((pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), stale=True)

    doc = format_standings(t, _view(t), private=True)

    assert doc.header == (
        "**Standings after round 1**",
        f"Tournament is now private — data from {FETCHED_AT_TAG}",
    )
