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
from cobra_bot.domain.models import Pairing, Tournament
from cobra_bot.domain.rounds import PairingsView, pairings_view
from cobra_bot.formatting.pairings import format_pairings, pairing_rows
from cobra_bot.formatting.text import display_width

type LoadRaw = Callable[[str], object]

ESC = chr(0x1B)
PRIMARY, STRONG, SECONDARY = f"{ESC}[0m", f"{ESC}[0m{ESC}[1m", f"{ESC}[0;37m"
SCORE, CORP, RUNNER = f"{ESC}[1;33m", f"{ESC}[0;34m", f"{ESC}[0;35m"

ALICE = player(1, "Alice", corp="Nuvem SA: Law of the Land", runner="Arissana: Artist")
BOB = player(2, "Bob", corp="Haas-Bioroid: Precision", runner="Zahya: Mercenary")
CAROL = player(3, "Carol")


def _fixture(raw_fixture: LoadRaw, name: str, tid: int = 4909) -> Tournament:
    return parse_tournament(raw_fixture(name), tournament_id=tid, fetched_at=FETCHED_AT)


def _view(t: Tournament, requested: int | None = None) -> PairingsView:
    view = pairings_view(t, requested)
    assert isinstance(view, PairingsView)
    return view


def _t() -> Tournament:
    return tournament(players=(ALICE, BOB, CAROL))


def _rows(p: Pairing, t: Tournament | None = None) -> list[str]:
    return plain(pairing_rows(t or _t(), p)).split("\n")


def _ansi_rows(p: Pairing) -> list[str]:
    return pairing_rows(_t(), p).split("\n")


# --- acceptance criteria -----------------------------------------------------------


def test_ac02_round_1_table_21_is_a_bye(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")
    doc = format_pairings(t, _view(t, 1))

    assert "T21 BYE Player0023" in [plain(e.text) for e in doc.entries]


def test_ac03_default_pairings_header(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")
    doc = format_pairings(t, _view(t))

    assert doc.header == (
        "**Round 8 pairings — complete**",
        "-# Top cut in progress — not supported yet",
        f"Data from {FETCHED_AT_TAG}",
    )
    assert doc.title == "Single-Sided Top 8 Fixture"
    assert doc.url == "https://tournaments.nullsignal.games/tournaments/4909"
    assert doc.footer == ("Round 8 · 23 tables · Corp first · number = points scored")


def test_ac22_double_sided_pairing_shows_both_games(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "dss", 5018)
    doc = format_pairings(t, _view(t, 1))
    tables = [plain(e.text) for e in doc.entries if "BYE" not in e.text]

    assert len(tables) == 15
    for entry in tables:
        name1, games1, name2, games2 = entry.split("\n")
        assert name1.startswith("T")
        assert name2.startswith("    ")
        assert games1.startswith("      C ")
        assert games2.startswith("      R ")
    assert doc.footer == (
        "Round 1 · 16 tables · double-sided · columns = game 1 | game 2"
    )


def test_ac07_in_progress_header(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "dss", 5018)
    doc = format_pairings(t, _view(t))

    assert doc.header[0] == "**Round 3 pairings — in progress**"


# --- single-sided -------------------------------------------------------------------


def test_single_sided_layout_and_colours() -> None:
    """SS-1, SS-2, P-2, P-3: Corp first; the winner bold, the loser secondary."""
    p = pairing(3, seat(1, "corp", 3), seat(2, "runner", 0))

    assert pairing_rows(_t(), p) == (
        f"{PRIMARY}T3  {SCORE} 3 {STRONG}Alice{SECONDARY} · {CORP}Nuvem{PRIMARY}\n"
        f"{PRIMARY}    {SCORE} 0 {SECONDARY}Bob{SECONDARY} · {RUNNER}Zahya{PRIMARY}"
    )


def test_runner_in_seat_1_is_shown_second() -> None:
    """Acceptance 5: `Inermis (Runner) 0–3 Minstrel (Corp)` puts Minstrel first."""
    t = tournament(players=(player(1, "Inermis"), player(2, "Minstrel")))
    p = pairing(3, seat(1, "runner", 0), seat(2, "corp", 3))

    rows = pairing_rows(t, p).split("\n")

    assert [plain(r) for r in rows] == ["T3   3 Minstrel · —", "     0 Inermis · —"]
    assert f"{STRONG}Minstrel" in rows[0]
    assert f"{SECONDARY}Inermis" in rows[1]


def test_unreported_shows_a_dash_and_plain_names() -> None:
    p = pairing(3, seat(2, "corp"), seat(1, "runner"))

    rows = _ansi_rows(p)

    assert [plain(r) for r in rows] == ["T3   – Bob · HB", "     – Alice · Arissana"]
    assert f"{PRIMARY}Bob" in rows[0]
    assert f"{PRIMARY}Alice" in rows[1]


def test_intentional_draw_shows_id_and_plain_names() -> None:
    p = pairing(5, seat(1, "corp", 1), seat(2, "runner", 1), intentional_draw=True)

    rows = _ansi_rows(p)

    assert [plain(r) for r in rows] == ["T5  ID Alice · Nuvem", "    ID Bob · Zahya"]
    assert f"{PRIMARY}Alice" in rows[0]
    assert f"{PRIMARY}Bob" in rows[1]


def test_equal_points_leave_both_names_plain() -> None:
    """P-2: a modified or split result without a winner."""
    p = pairing(5, seat(1, "corp", 1), seat(2, "runner", 1))

    rows = _ansi_rows(p)

    assert f"{SCORE} 1 {PRIMARY}Alice" in rows[0]
    assert f"{SCORE} 1 {PRIMARY}Bob" in rows[1]


@pytest.mark.parametrize(
    "bye",
    [
        pairing(21, seat(3, None, 6), seat(None)),
        pairing(21, seat(None), seat(3, None, 6)),
    ],
    ids=["player2-empty", "player1-empty"],
)
def test_bye(bye: Pairing) -> None:
    """P-4: one line; which ID to show is TBD, so none is shown."""
    assert _rows(bye) == ["T21 BYE Carol"]


def test_missing_identity_shows_a_secondary_dash() -> None:
    """A-4."""
    p = pairing(1, seat(3, "corp", 3), seat(1, "runner", 0))

    rows = _ansi_rows(p)

    assert plain(rows[0]) == "T1   3 Carol · —"
    assert rows[0].endswith(f"{SECONDARY} · {SECONDARY}—{PRIMARY}")


def test_unknown_player_id() -> None:
    p = pairing(1, seat(99, "corp"), seat(1, "runner"))

    assert _rows(p)[0] == "T1   – Unknown player · —"


def test_names_are_literal_and_cannot_close_the_code_block() -> None:
    """AC-21 data: markdown stays literal in a code block; C-7: ` -> '."""
    t = tournament(players=(player(1, "*bold_name~"), player(2, "```@everyone")))
    p = pairing(1, seat(1, "corp", 3), seat(2, "runner", 0))

    assert [r.split(" · ")[0] for r in _rows(p, t)] == [
        "T1   3 *bold_name~",
        "     0 '''@everyone",
    ]


@pytest.mark.parametrize(
    ("length", "shown"),
    [(15, "A" * 15), (16, "A" * 14 + "…")],
    ids=["at-limit", "one-above"],
)
def test_long_names_are_cut_to_15_columns(length: int, shown: str) -> None:
    """C-7: names longer than 15 columns become 14 columns plus `…`."""
    t = tournament(players=(player(1, "A" * length), player(2, "Bob")))
    p = pairing(1, seat(1, "corp", 3), seat(2, "runner", 0))

    assert _rows(p, t)[0] == f"T1   3 {shown} · —"


def test_longest_single_sided_line_is_34_columns() -> None:
    """C-5, SS-2: a 15-column name and a 9-column ID fill the line exactly."""
    t = tournament(players=(player(1, "A" * 15, corp="Editorial Division: X"),))
    p = pairing(10, seat(1, "corp", 3), seat(2, "runner", 0))

    assert display_width(_rows(p, t)[0]) == 34


def test_wide_characters_count_two_columns_towards_the_name_limit() -> None:
    """C-5, acceptance 9: an emoji name is cut by display width, not characters."""
    emoji = chr(0x1F600)
    t = tournament(players=(player(1, emoji * 8, corp="Editorial Division: X"),))
    p = pairing(10, seat(1, "corp", 3), seat(2, "runner", 0))

    first = _rows(p, t)[0]

    assert first == f"T10  3 {emoji * 7}… · Editorial"
    assert display_width(first) == 34


# --- double-sided -------------------------------------------------------------------


def test_double_sided_layout() -> None:
    """Acceptance 6, DS-1–DS-4: seat 1 is Corp in game 1; the columns are games."""
    p = pairing(
        1,
        seat(1, None, 3, corp=0, runner=3),
        seat(3, None, 3, corp=0, runner=3),
    )

    assert _rows(p) == [
        "T1   3 Alice",
        "      C Nuvem     0  R Arissana  3",
        "     3 Carol",
        "      R —         3  C —         0",
    ]


def test_double_sided_colours() -> None:
    """DS-3: tag and ID in the side colour, an unknown ID secondary, points yellow;
    P-2: the round winner bold."""
    p = pairing(
        1,
        seat(1, None, 6, corp=3, runner=3),
        seat(3, None, 0, corp=0, runner=0),
    )

    name1, games1, name2, games2 = _ansi_rows(p)

    assert name1 == f"{PRIMARY}T1  {SCORE} 6 {STRONG}Alice{PRIMARY}"
    assert games1 == (
        f"      {CORP}C {CORP}Nuvem     {SCORE}3{PRIMARY}  "
        f"{RUNNER}R {RUNNER}Arissana  {SCORE}3{PRIMARY}"
    )
    assert name2 == f"{PRIMARY}    {SCORE} 0 {SECONDARY}Carol{PRIMARY}"
    assert games2 == (
        f"      {RUNNER}R {SECONDARY}—         {SCORE}0{PRIMARY}  "
        f"{CORP}C {SECONDARY}—         {SCORE}0{PRIMARY}"
    )


def test_double_sided_without_results() -> None:
    """Acceptance 7: every point is `–`; both players plain, not bold."""
    p = pairing(2, seat(1, None), seat(2, None))

    rows = _ansi_rows(p)

    assert [plain(r) for r in rows] == [
        "T2   – Alice",
        "      C Nuvem     –  R Arissana  –",
        "     – Bob",
        "      R Zahya     –  C HB        –",
    ]
    assert f"{PRIMARY}Alice" in rows[0]
    assert f"{PRIMARY}Bob" in rows[2]


def test_double_sided_one_game_reported() -> None:
    """DS-4: the round total counts the reported game."""
    p = pairing(4, seat(1, None, 3, corp=3), seat(2, None, 0, runner=0))

    assert _rows(p) == [
        "T4   3 Alice",
        "      C Nuvem     3  R Arissana  –",
        "     0 Bob",
        "      R Zahya     0  C HB        –",
    ]


def test_double_sided_intentional_draw_shows_id() -> None:
    p = pairing(
        4,
        seat(1, None, 3, corp=3, runner=0),
        seat(2, None, 3, corp=3, runner=0),
        intentional_draw=True,
    )

    rows = _rows(p)

    assert rows[0] == "T4  ID Alice"
    assert rows[2] == "    ID Bob"


# --- the table ----------------------------------------------------------------------


def test_entries_are_sorted_by_table_and_separated_by_a_blank_line() -> None:
    """P-6, §3: one blank line between tables; C-4: no column headings."""
    rnd = (
        pairing(7, seat(1, "corp"), seat(2, "runner")),
        pairing(2, seat(3, None, 3), seat(None)),
    )
    t = tournament(rnd, players=(ALICE, BOB, CAROL))
    doc = format_pairings(t, _view(t))

    assert [plain(e.text).split(" ")[0] for e in doc.entries] == ["T2", "T7"]
    assert all(e.gap for e in doc.entries)
    assert doc.columns == ()
    assert doc.header == (
        "**Round 1 pairings — in progress**",
        f"Data from {FETCHED_AT_TAG}",
    )


def test_one_table_footer_is_singular() -> None:
    t = tournament(
        (pairing(1, seat(1, "corp"), seat(2, "runner")),), players=(ALICE, BOB)
    )

    assert format_pairings(t, _view(t)).footer.startswith("Round 1 · 1 table · ")


def test_three_digit_tables_widen_the_table_column() -> None:
    rnd = tuple(
        pairing(n, seat(2 * n - 1, "corp"), seat(2 * n, "runner"))
        for n in range(1, 101)
    )
    t = tournament(rnd, players=tuple(player(i) for i in range(1, 201)))
    doc = format_pairings(t, _view(t))

    assert plain(doc.entries[0].text).split("\n") == [
        "T1    – Player1 · —",
        "      – Player2 · —",
    ]
    assert plain(doc.entries[-1].text).startswith("T100  – Player199 ")


@pytest.mark.parametrize(
    ("private", "line"),
    [
        (False, f"Cobra unavailable — data from {FETCHED_AT_TAG}"),
        (True, f"Tournament is now private — data from {FETCHED_AT_TAG}"),
    ],
)
def test_stale_notice(private: bool, line: str) -> None:
    rnd = (pairing(1, seat(1, "corp"), seat(2, "runner")),)
    t = tournament(rnd, players=(ALICE, BOB), stale=True)

    assert format_pairings(t, _view(t), private=private).header[-1] == line
