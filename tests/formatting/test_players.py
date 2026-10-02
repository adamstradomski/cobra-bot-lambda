from builders import FETCHED_AT_TAG, pairing, plain, player, seat, tournament
from cobra_bot.domain.models import Player, Round, Tournament
from cobra_bot.domain.search import SearchResult
from cobra_bot.formatting.players import format_player_cards, player_card

ALICE = player(1, "Alice", rank=1, points=6, corp="Nuvem SA: X", runner="Arissana: Y")
BOB = player(2, "Bob", rank=2, points=3, corp="Haas-Bioroid: X", runner="Zahya: Y")
CAROL = player(3, "Carol", rank=3, points=3)

ROUND_1 = (
    pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),
    pairing(2, seat(3, None, 3), seat(None)),
)
ROUND_2 = (pairing(1, seat(2, "corp"), seat(1, "runner")),)
TOP_CUT = (
    pairing(
        1,
        seat(1, "corp", winner=True),
        seat(2, "runner", winner=False),
        elimination=True,
    ),
)

ALICE_ROW = " 1  Alice             6  0.000  Nuvem     Arissana"


def _t(*rounds: Round) -> Tournament:
    return tournament(*rounds, players=(ALICE, BOB, CAROL))


def _result(*players: Player, more: int = 0) -> SearchResult:
    return SearchResult(matches=players, more=more)


def test_player_with_opponent() -> None:
    card = plain(player_card(_t(ROUND_1, ROUND_2), ALICE))

    assert card.split("\n") == [
        ALICE_ROW,
        "Round 2",
        "T1  Bob               vs  Alice",
        "    HB                    Arissana",
    ]


def test_player_with_bye() -> None:
    card = plain(player_card(_t(ROUND_1), CAROL))

    assert card.split("\n")[1:] == ["Round 1", "T2  Carol            BYE"]


def test_player_during_top_cut_shows_latest_swiss_round_and_note() -> None:
    t = _t(ROUND_1, TOP_CUT)
    doc = format_player_cards(t, _result(ALICE), "ali")

    assert doc.header == (
        "**Players matching “ali”**",
        "-# Top cut in progress — not supported yet",
        f"Data from {FETCHED_AT_TAG}",
    )
    lines = plain(doc.entries[0].text).split("\n")
    assert lines[1:3] == ["Round 1", "T1  Alice            3–0  Bob"]


def test_player_not_paired_in_latest_round() -> None:
    card = plain(player_card(_t(ROUND_1, ROUND_2), CAROL))

    assert card.split("\n")[1:] == ["Round 2: not paired"]


def test_tournament_without_rounds_shows_standings_row_only() -> None:
    assert plain(player_card(_t(), ALICE)) == ALICE_ROW


def test_cards_are_separated_and_more_matches_note_comes_after() -> None:
    doc = format_player_cards(_t(ROUND_1), _result(ALICE, BOB, CAROL, more=4), "a")

    assert len(doc.entries) == 3
    assert all(e.gap for e in doc.entries)
    assert doc.notes == ("…and 4 more matched",)
    assert doc.header == ("**Players matching “a”**", f"Data from {FETCHED_AT_TAG}")
    assert doc.footer == "Pts / SoS / Corp / Runner · pairing: Corp left, Runner right"


def test_no_match() -> None:
    """AC-11 output."""
    doc = format_player_cards(_t(ROUND_1), _result(), "nobody")

    assert doc.entries == ()
    assert doc.notes == ("No players match.",)


def test_query_is_escaped() -> None:
    doc = format_player_cards(_t(ROUND_1), _result(), "*x_")

    assert doc.header[0] == "**Players matching “\\*x\\_”**"
