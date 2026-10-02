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
from cobra_bot.formatting.pairings import (
    format_pairings,
    pairing_rows,
    pairings_columns,
)

type LoadRaw = Callable[[str], object]

ESC = chr(0x1B)
STRONG, MUTED, PLAIN = f"{ESC}[1m", f"{ESC}[0;37m", f"{ESC}[0m"

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


def _rows(p: Pairing) -> list[str]:
    return plain(pairing_rows(_t(), p)).split("\n")


# --- acceptance criteria -----------------------------------------------------------


def test_ac02_round_1_table_21_is_a_bye(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")
    doc = format_pairings(t, _view(t, 1))

    assert "T21 Player0023       BYE" in [plain(e.text) for e in doc.entries]


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
    assert doc.footer == (
        "Round 8 · 23 tables · Corp left, Runner right · score from Corp side"
    )


def test_ac22_double_sided_pairing_shows_both_games(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "dss")
    doc = format_pairings(t, _view(t, 1))
    games = [plain(e.text) for e in doc.entries if "BYE" not in e.text]

    assert len(games) == 15
    for entry in games:
        total, game1, ids1, game2, ids2 = entry.split("\n")
        assert total.startswith("T")
        assert game1.startswith("↳ ")
        assert game2.startswith("↳ ")
        assert ids1.startswith("    ")
        assert ids2.startswith("    ")


def test_ac07_in_progress_header(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "dss")
    doc = format_pairings(t, _view(t))

    assert doc.header[0] == "**Round 3 pairings — in progress**"


# --- rows ---------------------------------------------------------------------------


def test_columns() -> None:
    heading, rule = pairings_columns()

    assert heading == f"{ESC}[1;37mT   Corp            Score Runner{ESC}[0m"
    assert plain(rule) == "─" * 44


def test_single_sided_corp_won() -> None:
    """Layout and colours as in the design: the winner bold white, the loser grey."""
    p = pairing(3, seat(1, "corp", 3), seat(2, "runner", 0))

    assert pairing_rows(_t(), p) == (
        f"{MUTED}T3  {STRONG}Alice           {ESC}[1;33m 3–0  {MUTED}Bob{ESC}[0m\n"
        f"    {ESC}[0;34mNuvem                 {ESC}[0;35mZahya{ESC}[0m"
    )


def test_runner_in_seat_1_is_shown_on_the_right() -> None:
    p = pairing(3, seat(1, "runner", 3), seat(2, "corp", 0))

    rows = pairing_rows(_t(), p)

    assert plain(rows).split("\n") == [
        "T3  Bob              0–3  Alice",
        "    HB                    Arissana",
    ]
    assert f"{MUTED}Bob " in rows
    assert f"{STRONG}Alice" in rows


def test_unreported_shows_vs_and_plain_names() -> None:
    p = pairing(3, seat(2, "corp"), seat(1, "runner"))

    rows = pairing_rows(_t(), p)

    assert plain(rows).split("\n")[0] == "T3  Bob               vs  Alice"
    assert f"{PLAIN}Bob " in rows
    assert f"{PLAIN}Alice" in rows


def test_intentional_draw_shows_id_and_plain_names() -> None:
    p = pairing(5, seat(1, "corp", 1), seat(2, "runner", 1), intentional_draw=True)

    rows = pairing_rows(_t(), p)

    assert plain(rows).split("\n")[0] == "T5  Alice             ID  Bob"
    assert f"{PLAIN}Alice " in rows
    assert f"{PLAIN}Bob" in rows


@pytest.mark.parametrize(
    "bye",
    [
        pairing(21, seat(3, None, 6), seat(None)),
        pairing(21, seat(None), seat(3, None, 6)),
    ],
    ids=["player2-empty", "player1-empty"],
)
def test_bye(bye: Pairing) -> None:
    assert _rows(bye) == ["T21 Carol            BYE"]


def test_missing_identity_shows_placeholder() -> None:
    p = pairing(1, seat(3, "corp", 3), seat(1, "runner", 0))

    assert _rows(p)[1] == "    —                     Arissana"


def test_unknown_player_id() -> None:
    p = pairing(1, seat(99, "corp"), seat(1, "runner"))

    assert _rows(p)[0] == "T1  Unknown player    vs  Alice"


def test_double_sided_entry() -> None:
    """Seat 1 won as Corp, seat 2 won as Corp: 3–3 split."""
    p = pairing(
        4,
        seat(1, None, 3, corp=3, runner=0),
        seat(2, None, 3, corp=3, runner=0),
    )

    assert _rows(p) == [
        "T4  Alice            3–3  Bob",
        "↳   Alice            3–0  Bob",
        "    Nuvem                 Zahya",
        "↳   Bob              3–0  Alice",
        "    HB                    Arissana",
    ]


def test_double_sided_one_game_reported() -> None:
    p = pairing(4, seat(1, None, 3, corp=3), seat(2, None, 0, runner=0))

    rows = _rows(p)

    assert rows[1] == "↳   Alice            3–0  Bob"
    assert rows[3] == "↳   Bob               vs  Alice"


def test_names_are_literal_and_cannot_close_the_code_block() -> None:
    """AC-21 data: markdown stays literal in a code block; C-8: ` -> '."""
    t = tournament(players=(player(1, "*bold_name~"), player(2, "```@everyone")))
    p = pairing(1, seat(1, "corp", 3), seat(2, "runner", 0))

    first = plain(pairing_rows(t, p)).split("\n")[0]

    assert first == "T1  *bold_name~      3–0  '''@everyone"


@pytest.mark.parametrize(
    ("length", "shown"),
    [(16, "A" * 16), (17, "A" * 15 + "…")],
    ids=["at-limit", "one-above"],
)
def test_long_names_are_cut_to_the_column(length: int, shown: str) -> None:
    """C-7: names longer than 16 columns become 15 columns plus `…`."""
    t = tournament(players=(player(1, "A" * length), player(2, "B" * length)))
    p = pairing(1, seat(1, "corp", 3), seat(2, "runner", 0))

    first = plain(pairing_rows(t, p)).split("\n")[0]

    assert first == f"T1  {shown} 3–0  {shown.replace('A', 'B')}"


def test_wide_characters_keep_the_score_column_aligned() -> None:
    """C-6 / acceptance 4: padding counts display width, not characters."""
    emoji = chr(0x1F600)
    t = tournament(players=(player(1, f"{emoji}Ace"), player(2, "Bob")))
    p = pairing(1, seat(1, "corp", 3), seat(2, "runner", 0))

    first = plain(pairing_rows(t, p)).split("\n")[0]

    assert first == f"T1  {emoji}Ace{' ' * 11} 3–0  Bob"


def test_entries_are_sorted_by_table_and_header_has_no_top_cut_note() -> None:
    rnd = (
        pairing(7, seat(1, "corp"), seat(2, "runner")),
        pairing(2, seat(3, None, 3), seat(None)),
    )
    t = tournament(rnd, players=(ALICE, BOB, CAROL))
    doc = format_pairings(t, _view(t))

    assert [plain(e.text).split(" ")[0] for e in doc.entries] == ["T2", "T7"]
    assert doc.header == (
        "**Round 1 pairings — in progress**",
        f"Data from {FETCHED_AT_TAG}",
    )
    assert doc.footer == (
        "Round 1 · 2 tables · Corp left, Runner right · score from Corp side"
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

    assert plain(doc.columns[0]).startswith("T    Corp ")
    assert plain(doc.entries[0].text).startswith("T1   Player1 ")
    assert plain(doc.entries[-1].text).startswith("T100 Player199 ")


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
