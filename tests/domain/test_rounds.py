from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from builders import player, tournament
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.models import Pairing, Player, Round, Seat, Tournament
from cobra_bot.domain.rounds import (
    NotStarted,
    PairingsView,
    RoundOutOfRange,
    StandingsView,
    TopCutNotSupported,
    is_pairing_complete,
    name_order,
    pairings_view,
    standings_view,
)

FETCHED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

type LoadRaw = Callable[[str], object]


def _fixture(raw_fixture: LoadRaw, name: str) -> Tournament:
    return parse_tournament(raw_fixture(name), tournament_id=1, fetched_at=FETCHED_AT)


def _player(pid: int, rank: int) -> Player:
    return Player(
        pid, f"P{pid}", rank, 0, Decimal(0), Decimal(0), None, None, None, None
    )


def _single(table: int, a: int, b: int, score: int | None) -> Pairing:
    def seat(pid: int, role: str) -> Seat:
        return Seat(pid, role, score, None, None, None)  # type: ignore[arg-type]

    return Pairing(table, seat(a, "corp"), seat(b, "runner"), False, False, False)


def _double(corp: int | None, runner: int | None) -> Pairing:
    def seat(pid: int) -> Seat:
        # Worst case: a partial sum is already present when only one game is in.
        reported = [g for g in (corp, runner) if g is not None]
        combined = sum(reported) if reported else None
        return Seat(pid, None, combined, corp, runner, None)

    return Pairing(1, seat(1), seat(2), False, False, False)


def _tournament(*rounds: Round, players: tuple[Player, ...] = ()) -> Tournament:
    return Tournament(1, "T", None, 0, len(rounds), players, rounds, FETCHED_AT, False)


# --- AC-03, AC-04, AC-05: single-sided with top cut --------------------------------


def test_ac03_default_pairings_show_last_swiss_round_with_top_cut_note(
    raw_fixture: LoadRaw,
) -> None:
    view = pairings_view(_fixture(raw_fixture, "single_sided_top8"))

    assert isinstance(view, PairingsView)
    assert (view.round_number, view.complete, view.top_cut_in_progress) == (
        8,
        True,
        True,
    )


def test_ac04_elimination_round_is_not_supported(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")

    assert pairings_view(t, 9) == TopCutNotSupported(round_number=9)


@pytest.mark.parametrize("requested", [0, 15, -1])
def test_ac05_round_out_of_range(raw_fixture: LoadRaw, requested: int) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")

    assert pairings_view(t, requested) == RoundOutOfRange(requested, last_round=14)


def test_requested_swiss_round(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "single_sided_top8")
    view = pairings_view(t, 1)

    assert isinstance(view, PairingsView)
    assert (view.round_number, view.complete) == (1, True)
    assert view.pairings == t.rounds[0]


def test_finished_tournament_standings_after_last_swiss_round(
    raw_fixture: LoadRaw,
) -> None:
    """AC-01 logic: standings after round 8, rank 1 first."""
    view = standings_view(_fixture(raw_fixture, "single_sided_top8"))

    assert isinstance(view, StandingsView)
    assert view.after_round == 8
    assert view.players[0].id == 1042


# --- AC-06: not started -----------------------------------------------------------


def test_ac06_no_rounds_means_not_started(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "not_started")

    assert pairings_view(t) == NotStarted()
    assert pairings_view(t, 1) == NotStarted()
    assert standings_view(t) == NotStarted()


# --- AC-07, AC-08: live rounds ----------------------------------------------------


def test_ac07_round_in_progress(raw_fixture: LoadRaw) -> None:
    """dss: rounds 1-2 complete, round 3 paired with only the bye reported."""
    t = _fixture(raw_fixture, "dss")
    pairings = pairings_view(t)
    standings = standings_view(t)

    assert isinstance(pairings, PairingsView)
    assert (pairings.round_number, pairings.complete) == (3, False)
    assert not pairings.top_cut_in_progress
    assert isinstance(standings, StandingsView)
    assert standings.after_round == 2


def test_ac08_round_1_without_results_lists_players_in_rank_order() -> None:
    players = (_player(10, 2), _player(11, 1), _player(12, 3))
    t = _tournament((_single(1, 10, 11, None),), players=players)

    view = standings_view(t)

    assert isinstance(view, StandingsView)
    assert view.after_round == 0
    assert [p.id for p in view.players] == [11, 10, 12]


def test_last_complete_round_is_used_when_a_later_round_is_partial() -> None:
    t = _tournament(
        (_single(1, 1, 2, 3),),
        (_single(1, 1, 2, 3), _single(2, 3, 4, None)),
    )

    view = standings_view(t)

    assert isinstance(view, StandingsView)
    assert view.after_round == 1


# --- AC-22: double-sided completion ----------------------------------------------


@pytest.mark.parametrize(
    ("corp", "runner", "complete"),
    [(3, 0, True), (3, None, False), (None, 3, False), (None, None, False)],
)
def test_ac22_double_sided_pairing_needs_both_games(
    corp: int | None, runner: int | None, complete: bool
) -> None:
    assert is_pairing_complete(_double(corp, runner)) is complete


def test_ac22_dss_completed_rounds(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "dss")

    assert [pairings_view(t, n).complete for n in (1, 2, 3)] == [True, True, False]  # type: ignore[union-attr]


# --- other pairing rules ----------------------------------------------------------


def test_bye_counts_as_complete() -> None:
    bye = Pairing(
        1,
        Seat(1, None, 3, None, None, None),
        Seat(None, None, None, None, None, None),
        False,
        False,
        False,
    )

    assert is_pairing_complete(bye)


def test_single_sided_needs_both_scores() -> None:
    pairing = _single(1, 1, 2, 3)
    half = Pairing(
        1, pairing.seat1, Seat(2, "runner", None, None, None, None), False, False, False
    )

    assert is_pairing_complete(pairing)
    assert not is_pairing_complete(half)


def test_tournament_with_only_elimination_rounds_reports_top_cut() -> None:
    elim = Pairing(
        1,
        Seat(1, "corp", None, None, None, True),
        Seat(2, "runner", None, None, None, False),
        False,
        False,
        True,
    )
    t = _tournament((elim,))

    assert pairings_view(t) == TopCutNotSupported(round_number=1)


# --- before the first round (AC-26) ---------------------------------------------


def _registered(*names: str) -> Tournament:
    return tournament(
        players=tuple(
            player(1000 + n, name, rank=len(names) - n)  # export rank: another order
            for n, name in enumerate(names)
        )
    )


def test_ac26_registered_players_listed_by_name_like_cobra() -> None:
    """Cobra's own order for World Championship 2026 before round 1."""
    t = _registered("ajjr82", "AJarr", "AbyssStaresBack", "Ajar", "34Witches")

    view = standings_view(t)

    assert isinstance(view, StandingsView)
    assert [p.name for p in view.players] == [
        "34Witches",
        "AbyssStaresBack",
        "Ajar",
        "AJarr",
        "ajjr82",
    ]
    assert [p.rank for p in view.players] == [1, 2, 3, 4, 5]
    assert (view.after_round, view.started) == (0, False)


def test_registered_players_with_the_same_name_keep_id_order() -> None:
    t = _registered("Bob", "bob", "BOB")

    view = standings_view(t)

    assert isinstance(view, StandingsView)
    assert [p.id for p in view.players] == [1000, 1001, 1002]


def test_registered_players_keep_their_other_fields() -> None:
    t = _registered("Zed")

    view = standings_view(t)

    assert isinstance(view, StandingsView)
    (only,) = view.players
    assert only == replace(t.players[0], rank=1)


def test_registration_does_not_start_pairings() -> None:
    t = _registered("Ann", "Bob")

    assert pairings_view(t) == NotStarted()


def test_started_tournament_is_marked_started(raw_fixture: LoadRaw) -> None:
    view = standings_view(_fixture(raw_fixture, "dss"))

    assert isinstance(view, StandingsView)
    assert view.started


@pytest.mark.parametrize(
    "cobra_order",
    [
        ["34Witches", "AbyssStaresBack"],  # digits before letters
        ["Ajar", "AJarr", "ajjr82"],  # case ignored
        ["metronome", "M.G.K.", "Michael kwan"],  # punctuation ignored
        ["TheComforter1212", "The king", "ThePaleKing"],  # spaces ignored
        ["Yidaho", "Yi Sun", "Zeebag"],
        ["Slapdash", "S@nit1zedPumpk1n", "soarix"],  # symbols ignored
        ["laura_42", "laurh2010"],  # underscores ignored
        ["Victor524287", "VØRT3X", "WarriorforC"],  # Ø as O
        ["Zahya", "Żółw", "Zz"],  # diacritics ignored
    ],
)
def test_name_order_matches_cobra(cobra_order: list[str]) -> None:
    """Pairs as Cobra lists them (World Championship 2026, before round 1)."""
    assert sorted(cobra_order[::-1], key=name_order) == cobra_order
