from collections.abc import Callable

import pytest

from builders import FETCHED_AT, FETCHED_AT_TAG, pairing, player, seat, tournament
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.models import Pairing, Tournament
from cobra_bot.domain.rounds import PairingsView, pairings_view
from cobra_bot.formatting.pairings import format_pairings, pairing_entry

type LoadRaw = Callable[[str], object]

ALICE = player(1, "Alice", corp="Nuvem SA: Law of the Land", runner="Arissana: Artist")
BOB = player(2, "Bob", corp="Haas-Bioroid: Precision", runner="Zahya: Mercenary")
CAROL = player(3, "Carol")


def _fixture(raw_fixture: LoadRaw, name: str, tid: int = 4909) -> Tournament:
    return parse_tournament(raw_fixture(name), tournament_id=tid, fetched_at=FETCHED_AT)


def _view(t: Tournament, requested: int | None = None) -> PairingsView:
    view = pairings_view(t, requested)
    assert isinstance(view, PairingsView)
    return view


# --- acceptance criteria -----------------------------------------------------------


def test_ac02_round_1_table_21_is_a_bye(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")
    doc = format_pairings(t, _view(t, 1))

    assert "T21 · Player0023 — BYE" in doc.entries


def test_ac03_default_pairings_header(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")
    doc = format_pairings(t, _view(t))

    assert doc.header == (
        "Round 8 pairings — complete",
        "Top cut in progress — not supported yet",
        f"Data from {FETCHED_AT_TAG}",
    )
    assert doc.title == "Single-Sided Top 8 Fixture"
    assert doc.url == "https://tournaments.nullsignal.games/tournaments/4909"


def test_ac22_double_sided_pairing_shows_both_games(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "dss")
    doc = format_pairings(t, _view(t, 1))
    games = [e for e in doc.entries if "BYE" not in e]

    assert len(games) == 15
    for entry in games:
        summary, game1, game2 = entry.split("\n")
        assert summary.startswith("T")
        assert game1.startswith("↳ ")
        assert "(Corp, " in game1
        assert "(Runner, " in game1
        assert game2.startswith("↳ ")


def test_ac07_in_progress_header(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "dss")
    doc = format_pairings(t, _view(t))

    assert doc.header[0] == "Round 3 pairings — in progress"


# --- entry formats ------------------------------------------------------------------


def _t() -> Tournament:
    return tournament(players=(ALICE, BOB, CAROL))


def test_single_sided_reported() -> None:
    p = pairing(3, seat(1, "corp", 3), seat(2, "runner", 0))

    assert pairing_entry(_t(), p) == (
        "T3 · Alice (Corp, Nuvem SA) 3–0 Bob (Runner, Zahya)"
    )


def test_single_sided_unreported_shows_vs() -> None:
    p = pairing(3, seat(2, "corp"), seat(1, "runner"))

    assert pairing_entry(_t(), p) == (
        "T3 · Bob (Corp, Haas-Bioroid) vs Alice (Runner, Arissana)"
    )


def test_intentional_draw_shows_id() -> None:
    p = pairing(5, seat(1, "corp", 1), seat(2, "runner", 1), intentional_draw=True)

    assert pairing_entry(_t(), p) == (
        "T5 · Alice (Corp, Nuvem SA) ID Bob (Runner, Zahya)"
    )


@pytest.mark.parametrize(
    "bye",
    [
        pairing(21, seat(3, None, 6), seat(None)),
        pairing(21, seat(None), seat(3, None, 6)),
    ],
    ids=["player2-empty", "player1-empty"],
)
def test_bye(bye: Pairing) -> None:
    assert pairing_entry(_t(), bye) == "T21 · Carol — BYE"


def test_missing_identity_shows_placeholder() -> None:
    p = pairing(1, seat(3, "corp", 3), seat(1, "runner", 0))

    assert pairing_entry(_t(), p) == "T1 · Carol (Corp, ?) 3–0 Alice (Runner, Arissana)"


def test_unknown_player_id() -> None:
    p = pairing(1, seat(99, "corp"), seat(1, "runner"))

    assert pairing_entry(_t(), p).startswith("T1 · Unknown player (Corp, ?) vs")


def test_double_sided_entry() -> None:
    """Seat 1 won as Corp, seat 2 won as Corp: 3–3 split."""
    p = pairing(
        4,
        seat(1, None, 3, corp=3, runner=0),
        seat(2, None, 3, corp=3, runner=0),
    )

    assert pairing_entry(_t(), p) == (
        "T4 · Alice 3–3 Bob\n"
        "↳ Alice (Corp, Nuvem SA) 3–0 Bob (Runner, Zahya)\n"
        "↳ Bob (Corp, Haas-Bioroid) 3–0 Alice (Runner, Arissana)"
    )


def test_double_sided_one_game_reported() -> None:
    p = pairing(4, seat(1, None, 3, corp=3), seat(2, None, 0, runner=0))

    assert pairing_entry(_t(), p).split("\n")[1:] == [
        "↳ Alice (Corp, Nuvem SA) 3–0 Bob (Runner, Zahya)",
        "↳ Bob (Corp, Haas-Bioroid) vs Alice (Runner, Arissana)",
    ]


def test_names_are_escaped() -> None:
    """AC-21 data: markdown in names renders literally."""
    t = tournament(players=(player(1, "*bold_name~"), player(2, "@Mention")))
    p = pairing(1, seat(1, "corp", 3), seat(2, "runner", 0))

    assert pairing_entry(t, p) == (
        r"T1 · \*bold\_name\~ (Corp, ?) 3–0 @Mention (Runner, ?)"
    )


def test_entries_are_sorted_by_table_and_header_has_no_top_cut_note() -> None:
    rnd = (
        pairing(7, seat(1, "corp"), seat(2, "runner")),
        pairing(2, seat(3, None, 3), seat(None)),
    )
    t = tournament(rnd, players=(ALICE, BOB, CAROL))
    doc = format_pairings(t, _view(t))

    assert [e.split(" ")[0] for e in doc.entries] == ["T2", "T7"]
    assert doc.header == (
        "Round 1 pairings — in progress",
        f"Data from {FETCHED_AT_TAG}",
    )


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
