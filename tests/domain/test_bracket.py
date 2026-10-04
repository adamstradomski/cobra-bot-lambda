"""Top cut: Cobra's brackets, the cut's state, the bracket and the cut ranking."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from builders import pairing, player, seat, tournament
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain import bracket as b
from cobra_bot.domain.models import EliminationPlayer, Pairing, Round, Tournament

type LoadRaw = Callable[[str], object]

FETCHED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _fixture(raw_fixture: LoadRaw, name: str) -> Tournament:
    return parse_tournament(raw_fixture(name), tournament_id=1, fetched_at=FETCHED_AT)


def _game(number: int, a: int, b_: int, winner: int | None = None) -> Pairing:
    """A cut game; seat 1 is `a` (the Corp), seat 2 `b_`."""
    return pairing(
        number,
        seat(a, "corp", winner=None if winner is None else winner == a),
        seat(b_, "runner", winner=None if winner is None else winner == b_),
        elimination=True,
    )


def _cut(size: int, *rounds: Round, placed: dict[int, int] | None = None) -> Tournament:
    """`size` players seeded 1..size by Swiss rank (IDs 1..size), one Swiss
    round, then `rounds` of the cut. `placed`: rank -> player in the cut ranking."""
    players = tuple(player(n, rank=n) for n in range(1, size + 1))
    swiss: Round = tuple(
        pairing(n, seat(2 * n - 1, "corp", 3), seat(2 * n, "runner", 0))
        for n in range(1, size // 2 + 1)
    )
    ranking = tuple(
        EliminationPlayer(rank, (placed or {}).get(rank), None)
        for rank in range(1, size + 1)
    )
    return tournament(
        swiss,
        *rounds,
        players=players,
        cut_to_top=size,
        elimination_players=ranking,
    )


# --- templates (copied from Cobra's app/services/bracket/*.rb) ---------------------


ALL_TEMPLATES = [t for options in b.TEMPLATES.values() for t in options]


@pytest.mark.parametrize("c", ALL_TEMPLATES, ids=lambda c: f"{c.size}-{c.double}")
def test_template_links_point_at_later_games_of_the_same_bracket(
    c: b.Template,
) -> None:
    for spec in c.games:
        for target in (spec.winner_game, spec.loser_game):
            if target is not None:
                later = c.game(target)
                assert later is not None and later.round > spec.round


@pytest.mark.parametrize("c", ALL_TEMPLATES, ids=lambda c: f"{c.size}-{c.double}")
def test_every_winner_and_loser_source_matches_the_feeding_game(
    c: b.Template,
) -> None:
    """A slot taking the winner (loser) of game g is in the game g sends its
    winner (loser) to, and the other way round."""
    for spec in c.games:
        for source in (spec.slot1, spec.slot2):
            match source:
                case b.WinnerOf(game=g):
                    assert c.game(g).winner_game == spec.number  # type: ignore[union-attr]
                case b.LoserOf(game=g):
                    assert c.game(g).loser_game == spec.number  # type: ignore[union-attr]
    for spec in c.games:
        if spec.winner_game is not None and c.double:
            target = c.game(spec.winner_game)
            assert target is not None
            assert b.WinnerOf(spec.number) in (target.slot1, target.slot2)


@pytest.mark.parametrize("c", ALL_TEMPLATES, ids=lambda c: f"{c.size}-{c.double}")
def test_round_one_seats_every_seed_once(c: b.Template) -> None:
    seeds = [
        s.position for g in c.games for s in (g.slot1, g.slot2) if isinstance(s, b.Seed)
    ]
    assert sorted(seeds) == list(range(1, c.size + 1))


def test_every_cut_size_cobra_supports_has_a_template() -> None:
    """Cobra's Bracket::Factory: double elimination for 4, 8, 16; single for
    2, 3, 4, 8, 16."""
    assert {(c.size, c.double) for c in ALL_TEMPLATES} == {
        (4, True),
        (8, True),
        (16, True),
        (2, False),
        (3, False),
        (4, False),
        (8, False),
        (16, False),
    }


@pytest.mark.parametrize(
    ("fixture", "size"), [("single_sided_top8", 8), ("large_top_cut", 16)]
)
def test_real_cuts_fit_the_double_elimination_template(
    raw_fixture: LoadRaw, fixture: str, size: int
) -> None:
    c = b.template(_fixture(raw_fixture, fixture))

    assert c is not None
    assert (c.size, c.double) == (size, True)


# --- format detection ---------------------------------------------------------------


def test_top8_single_elimination_is_told_by_round_one_seeds() -> None:
    t = _cut(8, (_game(1, 1, 8), _game(2, 2, 7), _game(3, 3, 6), _game(4, 4, 5)))

    assert b.template(t) == b.SINGLE_TOP8


def test_top8_double_elimination_round_one() -> None:
    t = _cut(8, (_game(1, 1, 8), _game(2, 4, 5), _game(3, 2, 7), _game(4, 3, 6)))

    assert b.template(t) == b.DOUBLE_TOP8


def test_top4_round_one_fits_both_and_double_wins() -> None:
    t = _cut(4, (_game(1, 1, 4, 1), _game(2, 2, 3, 2)))

    assert b.template(t) == b.DOUBLE_TOP4


def test_top4_round_two_with_only_the_final_is_single_elimination() -> None:
    t = _cut(4, (_game(1, 1, 4, 1), _game(2, 2, 3, 2)), (_game(3, 1, 2),))

    assert b.template(t) == b.SINGLE_TOP4


def test_no_round_paired_yet_is_double_elimination() -> None:
    assert b.template(_cut(16)) == b.DOUBLE_TOP16


def test_games_matching_no_template_give_no_template() -> None:
    t = _cut(8, (_game(1, 1, 2), _game(2, 3, 4), _game(3, 5, 6), _game(4, 7, 8)))

    assert b.template(t) is None
    assert b.bracket_view(t) == b.BracketUnavailable(8)


def test_unknown_game_number_gives_no_template() -> None:
    t = _cut(4, (_game(1, 1, 4), _game(9, 2, 3)))

    assert b.template(t) is None


def test_cut_size_without_a_bracket() -> None:
    t = _cut(6)

    assert b.bracket_view(t) == b.BracketUnavailable(6)


# --- cut status -----------------------------------------------------------------------


def test_status_none_without_a_cut() -> None:
    t = tournament((pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),))

    assert b.cut_status(t) == "none"
    assert b.bracket_view(t) == b.NoTopCut()
    assert b.top_cut_view(t) == b.NoTopCut()


def test_status_announced_once_the_cut_is_made() -> None:
    assert b.cut_status(_cut(8)) == "announced"


def test_status_in_progress_with_a_cut_round() -> None:
    assert b.cut_status(_cut(4, (_game(1, 1, 4), _game(2, 2, 3)))) == "in_progress"


def test_status_finished_once_cobra_places_the_winner() -> None:
    t = _cut(4, (_game(1, 1, 4, 1), _game(2, 2, 3, 2)), placed={1: 1})

    assert b.cut_status(t) == "finished"


def test_status_in_progress_while_only_lower_places_are_decided() -> None:
    t = _cut(4, (_game(1, 1, 4, 1), _game(2, 2, 3, 2)), placed={4: 4})

    assert b.cut_status(t) == "in_progress"


# --- seeds --------------------------------------------------------------------------


def test_seeds_are_the_swiss_ranks_of_the_cut() -> None:
    assert b.seeds(_cut(4)) == {1: 1, 2: 2, 3: 3, 4: 4}


def test_exported_seeds_override_the_swiss_rank() -> None:
    t = _cut(4)
    t = tournament(
        *t.rounds,
        players=t.players,
        cut_to_top=4,
        elimination_players=(EliminationPlayer(4, 4, 3), EliminationPlayer(3, 3, 4)),
    )

    assert b.seeds(t) == {1: 1, 2: 2, 3: 4, 4: 3}


def test_real_cut_seeds_match_cobras(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "large_top_cut")
    by_rank = {p.id: p.rank for p in t.players}

    assert all(by_rank[e.player_id] == e.seed for e in t.elimination_players)  # type: ignore[index]


# --- bracket view -------------------------------------------------------------------


def test_before_round_one_the_first_games_show_the_seeds() -> None:
    view = b.bracket_view(_cut(4))

    assert isinstance(view, b.BracketView)
    first = view.games[0]
    assert (first.spec.number, first.slot1.player_id, first.slot2.player_id) == (
        1,
        1,
        4,
    )
    assert first.pairing is None


def test_a_later_game_takes_decided_winners_and_losers_before_it_is_paired() -> None:
    view = b.bracket_view(_cut(4, (_game(1, 1, 4, 4), _game(2, 2, 3, 2))))

    assert isinstance(view, b.BracketView)
    games = {g.spec.number: g for g in view.games}
    assert (games[3].slot1.player_id, games[3].slot2.player_id) == (4, 2)
    assert (games[4].slot1.player_id, games[4].slot2.player_id) == (1, 3)
    assert games[5].slot1.player_id is None
    assert games[5].slot1.source == b.LoserOf(3)


def test_an_unreported_game_decides_no_later_slot() -> None:
    view = b.bracket_view(_cut(4, (_game(1, 1, 4), _game(2, 2, 3, 2))))

    assert isinstance(view, b.BracketView)
    game3 = next(g for g in view.games if g.spec.number == 3)
    assert (game3.slot1.player_id, game3.slot2.player_id) == (None, 2)


def test_the_reset_final_is_left_out_until_paired() -> None:
    view = b.bracket_view(_cut(4))

    assert isinstance(view, b.BracketView)
    assert [g.spec.number for g in view.games] == [1, 2, 3, 4, 5, 6]
    assert view.rounds == 4


def test_the_reset_final_is_shown_once_paired() -> None:
    rounds = (
        (_game(1, 1, 4, 1), _game(2, 2, 3, 2)),
        (_game(3, 1, 2, 1), _game(4, 4, 3, 4)),
        (_game(5, 2, 4, 2),),
        (_game(6, 1, 2, 2),),
        (_game(7, 2, 1),),
    )
    view = b.bracket_view(_cut(4, *rounds))

    assert isinstance(view, b.BracketView)
    assert view.games[-1].spec.number == 7
    assert view.rounds == 5


def test_paired_slots_follow_the_seats_order() -> None:
    view = b.bracket_view(_cut(4, (_game(1, 4, 1), _game(2, 2, 3))))

    assert isinstance(view, b.BracketView)
    assert (view.games[0].slot1.player_id, view.games[0].slot2.player_id) == (4, 1)


def test_single_elimination_later_games_are_unknown_until_paired() -> None:
    t = _cut(
        8, (_game(1, 1, 8, 1), _game(2, 2, 7, 2), _game(3, 3, 6, 3), _game(4, 4, 5, 4))
    )

    view = b.bracket_view(t)

    assert isinstance(view, b.BracketView)
    game5 = next(g for g in view.games if g.spec.number == 5)
    assert game5.slot1 == b.BracketSlot(None, b.Reseeded())


# --- winner / loser -------------------------------------------------------------------


def test_winner_and_loser_of_a_reported_game() -> None:
    game = _game(1, 1, 2, 2)

    assert (b.winner(game), b.loser(game)) == (2, 1)


def test_winner_and_loser_of_an_unreported_game_are_unknown() -> None:
    game = _game(1, 1, 2)

    assert (b.winner(game), b.loser(game)) == (None, None)
    assert (b.winner(None), b.loser(None)) == (None, None)


# --- top-cut ranking -----------------------------------------------------------------


def test_placed_players_take_their_places_and_the_rest_wait_above_them() -> None:
    """Top 4 double elimination after round 2: 3 lost to 2 and to 4 (out, not
    placed yet: Cobra places 3rd and 4th together); 1 and 2 still in."""
    rounds = (
        (_game(1, 1, 4, 1), _game(2, 2, 3, 2)),
        (_game(3, 1, 2, 1), _game(4, 4, 3, 4)),
    )
    view = b.top_cut_view(_cut(4, *rounds, placed={4: 3}))

    assert isinstance(view, b.TopCutView)
    assert [(e.rank, e.player_id) for e in view.entries] == [
        (None, 1),
        (None, 2),
        (None, 4),
        (4, 3),
    ]


def test_still_playing_before_out_and_later_out_higher() -> None:
    """Top 8 double after round 2 of the cut: losers of game 7 and 8 are out
    in round 2, losers of round 1 who won in round 2 still play."""
    rounds = (
        (_game(1, 1, 8, 1), _game(2, 4, 5, 4), _game(3, 2, 7, 2), _game(4, 3, 6, 3)),
        (_game(5, 1, 4, 1), _game(6, 2, 3, 2), _game(7, 8, 5, 8), _game(8, 7, 6, 7)),
    )
    view = b.top_cut_view(_cut(8, *rounds))

    assert isinstance(view, b.TopCutView)
    ids = [e.player_id for e in view.entries]
    assert ids[:6] == [1, 2, 3, 4, 7, 8]  # still in, by seed
    assert ids[6:] == [5, 6]  # out, by seed
    assert all(e.rank is None for e in view.entries)


def test_wins_and_losses_count_reported_games_only() -> None:
    rounds = ((_game(1, 1, 4, 4), _game(2, 2, 3)),)
    view = b.top_cut_view(_cut(4, *rounds))

    assert isinstance(view, b.TopCutView)
    record = {e.player_id: (e.wins, e.losses) for e in view.entries}
    assert record == {1: (0, 1), 2: (0, 0), 3: (0, 0), 4: (1, 0)}


def test_double_elimination_is_out_after_two_losses() -> None:
    rounds = ((_game(1, 1, 4, 4), _game(2, 2, 3, 2)), (_game(4, 1, 3, 3),))
    t = _cut(4, *rounds)
    entries = {e.player_id: e for e in b.top_cut_view(t).entries}  # type: ignore[union-attr]

    assert entries[1].eliminated
    assert not entries[3].eliminated  # one loss


def test_single_elimination_is_out_after_one_loss() -> None:
    t = _cut(
        8, (_game(1, 1, 8, 8), _game(2, 2, 7, 2), _game(3, 3, 6, 3), _game(4, 4, 5, 4))
    )
    entries = {e.player_id: e for e in b.top_cut_view(t).entries}  # type: ignore[union-attr]

    assert entries[1].eliminated
    assert not entries[8].eliminated


def test_the_champion_is_not_out(raw_fixture: LoadRaw) -> None:
    view = b.top_cut_view(_fixture(raw_fixture, "single_sided_top8"))

    assert isinstance(view, b.TopCutView)
    assert view.status == "finished"
    champion, *others = view.entries
    assert (champion.rank, champion.eliminated) == (1, False)
    assert all(e.eliminated for e in others)
    assert [e.rank for e in view.entries] == list(range(1, 9))


def test_announced_cut_lists_the_seeds() -> None:
    view = b.top_cut_view(_cut(4))

    assert isinstance(view, b.TopCutView)
    assert [(e.player_id, e.seed, e.wins, e.losses) for e in view.entries] == [
        (1, 1, 0, 0),
        (2, 2, 0, 0),
        (3, 3, 0, 0),
        (4, 4, 0, 0),
    ]


def test_cut_player_missing_from_players_has_no_record() -> None:
    t = _cut(2)
    t = tournament(
        *t.rounds,
        players=t.players[:1],
        cut_to_top=2,
        elimination_players=(EliminationPlayer(1, 1, 1), EliminationPlayer(2, 9, 2)),
    )
    view = b.top_cut_view(t)

    assert isinstance(view, b.TopCutView)
    assert [(e.player_id, e.player is None) for e in view.entries] == [
        (1, False),
        (9, True),
    ]


def test_a_seed_missing_from_the_export_does_not_break_the_fit() -> None:
    t = _cut(4, (_game(1, 1, 4), _game(2, 2, 3)))
    t = tournament(*t.rounds, players=t.players[:3], cut_to_top=4)

    assert b.template(t) == b.DOUBLE_TOP4
