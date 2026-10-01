from collections.abc import Callable

from builders import FETCHED_AT, FETCHED_AT_TAG, pairing, player, seat, tournament
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.models import Tournament
from cobra_bot.domain.rounds import StandingsView, standings_view
from cobra_bot.formatting.standings import format_standings, standings_entry

type LoadRaw = Callable[[str], object]


def _view(t: Tournament) -> StandingsView:
    view = standings_view(t)
    assert isinstance(view, StandingsView)
    return view


def test_ac01_finished_tournament(raw_fixture: LoadRaw) -> None:
    t = parse_tournament(
        raw_fixture("single_sided_top8"), tournament_id=4909, fetched_at=FETCHED_AT
    )
    doc = format_standings(t, _view(t))

    assert doc.header == ("Standings after round 8", f"Data from {FETCHED_AT_TAG}")
    assert doc.entries[0].startswith("1\\. Player0042 — 22 pts — SoS ")
    assert len(doc.entries) == 46
    assert doc.url == (
        "https://tournaments.nullsignal.games/tournaments/4909/players/standings"
    )


def test_ac08_no_completed_round_lists_players_in_rank_order() -> None:
    players = (player(10, "Bob", rank=2), player(11, "Alice", rank=1))
    t = tournament((pairing(1, seat(10, "corp"), seat(11, "runner")),), players=players)
    doc = format_standings(t, _view(t))

    assert doc.header[0] == "No completed rounds yet"
    assert [e.split(" ")[1] for e in doc.entries] == ["Alice", "Bob"]


def test_entry_format() -> None:
    p = player(
        1,
        "Alice",
        rank=1,
        points=22,
        sos="1.821",
        corp="Nuvem SA: Law of the Land",
        runner="Arissana Rocha Nahu: Street Artist",
    )

    assert standings_entry(p) == (
        "1\\. Alice — 22 pts — SoS 1.821 — Nuvem SA / Arissana Rocha Nahu"
    )


def test_sos_is_shown_with_three_decimals() -> None:
    assert " SoS 3.750 " in standings_entry(player(1, sos="3.75"))
    assert " SoS 0.000 " in standings_entry(player(1, sos="0"))


def test_missing_identities_and_escaped_name() -> None:
    entry = standings_entry(player(1, "*bold_name~", rank=12))

    assert entry == r"12\. \*bold\_name\~ — 0 pts — SoS 0.000 — ? / ?"


def test_stale_private_notice() -> None:
    t = tournament((pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), stale=True)

    doc = format_standings(t, _view(t), private=True)

    assert doc.header == (
        "Standings after round 1",
        f"Tournament is now private — data from {FETCHED_AT_TAG}",
    )
