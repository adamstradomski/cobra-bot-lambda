import pytest

from cobra_bot.cobra.refs import (
    InvalidTournamentRef,
    Shortcode,
    TournamentId,
    TournamentRef,
    parse_ref,
)

STANDINGS_URL = (
    "https://tournaments.nullsignal.games/tournaments/4977/players/standings"
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4909", TournamentId(4909)),
        (STANDINGS_URL, TournamentId(4977)),
    ],
)
def test_ac13_valid_references(text: str, expected: TournamentRef) -> None:
    assert parse_ref(text) == expected


@pytest.mark.parametrize("text", ["https://example.com/tournaments/1", "abc!"])
def test_ac13_invalid_references(text: str) -> None:
    with pytest.raises(InvalidTournamentRef):
        parse_ref(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("  4909 ", TournamentId(4909)),
        ("<https://tournaments.nullsignal.games/tournaments/5018>", TournamentId(5018)),
        ("http://tournaments.nullsignal.games/tournaments/5018/", TournamentId(5018)),
        (
            "https://Tournaments.NullSignal.Games/tournaments/5018?x=1#y",
            TournamentId(5018),
        ),
        ("1234", TournamentId(1234)),  # all digits: an ID, never a shortcode
        ("QNSF", Shortcode("QNSF")),
        ("qnsf", Shortcode("QNSF")),
        ("N9WI", Shortcode("N9WI")),
        ("https://tournaments.nullsignal.games/QNSF", Shortcode("QNSF")),
        ("https://tournaments.nullsignal.games/n9wi/", Shortcode("N9WI")),
    ],
)
def test_other_accepted_forms(text: str, expected: TournamentRef) -> None:
    assert parse_ref(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "0",
        "1234567890",  # more than 9 digits
        "QNS",
        "QNSFX",
        "QN-F",
        "https://tournaments.nullsignal.games/",
        "https://tournaments.nullsignal.games/tournaments/",
        "https://tournaments.nullsignal.games/tournaments/QNSF",
        "https://tournaments.nullsignal.games/tournaments/0",
        "https://tournaments.nullsignal.games/1234",
        "https://tournaments.nullsignal.games.evil.com/tournaments/1",
        "https://evil.com/?u=https://tournaments.nullsignal.games/tournaments/1",
        "ftp://tournaments.nullsignal.games/tournaments/1",
        "tournaments.nullsignal.games/tournaments/1",
        "javascript:alert(1)",
    ],
)
def test_rejected_inputs(text: str) -> None:
    with pytest.raises(InvalidTournamentRef):
        parse_ref(text)
