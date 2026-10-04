from builders import FETCHED_AT_TAG, pairing, plain, player, seat, tournament
from cobra_bot.domain.models import Player, Round, Tournament
from cobra_bot.domain.search import NameResult, NamesResult
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

ALICE_ROWS = [" 1. Alice            6", "    Nuvem        0.000", "    Arissana"]


def _t(*rounds: Round) -> Tournament:
    return tournament(*rounds, players=(ALICE, BOB, CAROL))


def _result(*players: Player, more: int = 0) -> NamesResult:
    """One name that matched `players` and `more` not shown."""
    return NamesResult(
        matches=players, names=(NameResult("q", len(players) + more, more),), skipped=0
    )


def test_player_with_opponent() -> None:
    card = plain(player_card(_t(ROUND_1, ROUND_2), ALICE))

    assert card.split("\n") == [
        *ALICE_ROWS,
        "Round 2",
        "T1   – Bob · HB",
        "     – Alice · Arissana",
    ]


def test_player_with_bye() -> None:
    card = plain(player_card(_t(ROUND_1), CAROL))

    assert card.split("\n")[3:] == ["Round 1", "T2  BYE Carol"]


def test_player_during_top_cut_shows_the_latest_cut_game_and_no_note() -> None:
    t = _t(ROUND_1, TOP_CUT)
    doc = format_player_cards(t, _result(ALICE), "ali")

    assert doc.header == ("**Players matching “ali”**", f"Data from {FETCHED_AT_TAG}")
    lines = plain(doc.entries[0].text).split("\n")
    assert lines[3:6] == ["Round 2", "G1   W Alice · Nuvem", "     L Bob · Zahya"]


def test_player_not_paired_in_latest_round() -> None:
    card = plain(player_card(_t(ROUND_1, ROUND_2), CAROL))

    assert card.split("\n")[3:] == ["Round 2: not paired"]


def test_tournament_without_rounds_shows_standings_row_only() -> None:
    assert plain(player_card(_t(), ALICE)).split("\n") == ALICE_ROWS


def test_cards_are_separated_and_more_matches_note_comes_after() -> None:
    doc = format_player_cards(_t(ROUND_1), _result(ALICE, BOB, CAROL, more=4), "a")

    assert len(doc.entries) == 3
    assert all(e.gap for e in doc.entries)
    assert doc.notes == ("…and 4 more matched",)
    assert doc.header == ("**Players matching “a”**", f"Data from {FETCHED_AT_TAG}")
    assert doc.footer == (
        "Corp + SoS on line 2, Runner on line 3 · pairing: Corp first · "
        "number = points scored"
    )


def test_no_match() -> None:
    """AC-11 output."""
    doc = format_player_cards(_t(ROUND_1), _result(), "nobody")

    assert doc.entries == ()
    assert doc.notes == ("No players match.",)


def test_query_is_escaped() -> None:
    doc = format_player_cards(_t(ROUND_1), _result(), "*x_")

    assert doc.header[0] == "**Players matching “\\*x\\_”**"


# --- several names ----------------------------------------------------------------


def _names(*names: tuple[str, int, int], skipped: int = 0) -> NamesResult:
    return NamesResult(
        matches=(ALICE,),
        names=tuple(NameResult(*n) for n in names),
        skipped=skipped,
    )


def test_several_names_note_each_name_without_a_match() -> None:
    doc = format_player_cards(
        _t(ROUND_1), _names(("ali", 1, 0), ("zed", 0, 0)), "ali, zed"
    )

    assert doc.notes == ("No players match “zed”.",)


def test_several_names_note_each_name_with_more_matches() -> None:
    doc = format_player_cards(
        _t(ROUND_1), _names(("ali", 1, 0), ("player", 7, 4)), "ali, player"
    )

    assert doc.notes == ("…and 4 more matched “player”",)


def test_several_names_are_escaped_in_notes() -> None:
    doc = format_player_cards(_t(ROUND_1), _names(("ali", 1, 0), ("*x_", 0, 0)), "q")

    assert doc.notes == (r"No players match “\*x\_”.",)


def test_names_past_the_limit_are_reported() -> None:
    doc = format_player_cards(_t(ROUND_1), _names(("ali", 1, 0), skipped=2), "q")

    assert doc.notes == ("Only the first 10 names were searched (2 more given).",)


def test_one_name_keeps_the_single_name_notes() -> None:
    result = NamesResult(matches=(), names=(NameResult("zed", 0, 0),), skipped=0)

    doc = format_player_cards(_t(ROUND_1), result, "zed")

    assert doc.notes == ("No players match.",)
