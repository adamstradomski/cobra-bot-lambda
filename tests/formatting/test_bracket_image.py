"""The bracket image: layout (Cobra's), slot texts, drawing, cache key, message."""

import io
from collections.abc import Callable

from PIL import Image

from builders import FETCHED_AT, pairing, player, seat, tournament
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.bracket import BracketView, bracket_view
from cobra_bot.domain.models import EliminationPlayer, Pairing, Round, Tournament
from cobra_bot.formatting import bracket_image as bi
from cobra_bot.formatting import image
from cobra_bot.formatting.image import Fonts

type LoadRaw = Callable[[str], object]

TOP4 = tuple(
    player(n, f"Player {n}", rank=n, corp="Nuvem SA: X", runner="Zahya Sadeghi: Y")
    for n in range(1, 5)
)


def _game(number: int, a: int, b: int, winner: int | None = None) -> Pairing:
    return pairing(
        number,
        seat(a, "corp", winner=None if winner is None else winner == a),
        seat(b, "runner", winner=None if winner is None else winner == b),
        elimination=True,
    )


def _top4(*rounds: Round, players: tuple = TOP4) -> Tournament:  # type: ignore[type-arg]
    swiss = (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),)
    return tournament(
        swiss,
        *rounds,
        players=players,
        cut_to_top=4,
        elimination_players=tuple(
            EliminationPlayer(n, None, None) for n in range(1, 5)
        ),
    )


def _view(t: Tournament) -> BracketView:
    view = bracket_view(t)
    assert isinstance(view, BracketView)
    return view


def _layout(t: Tournament) -> bi.Layout:
    return bi.bracket_layout(t, _view(t))


def _boxes(layout: bi.Layout) -> dict[int, bi.Box]:
    return {b.game: b for s in layout.sections for b in s.boxes}


# --- layout ---------------------------------------------------------------------------


def test_double_elimination_has_upper_and_lower_sections() -> None:
    layout = _layout(_top4())

    assert [s.label for s in layout.sections] == ["Upper bracket", "Lower bracket"]
    assert [b.game for b in layout.sections[0].boxes] == [1, 2, 3, 6]
    assert [b.game for b in layout.sections[1].boxes] == [4, 5]
    assert layout.columns == 4


def test_single_elimination_is_one_section_without_label() -> None:
    t = _top4((_game(1, 1, 4, 1), _game(2, 2, 3, 2)), (_game(3, 1, 2),))

    (section,) = _layout(t).sections

    assert section.label is None
    assert [b.game for b in section.boxes] == [1, 2, 3]


def test_columns_are_bracket_rounds() -> None:
    boxes = _boxes(_layout(_top4()))

    assert {g: b.column for g, b in boxes.items()} == {
        1: 0,
        2: 0,
        3: 1,
        4: 1,
        5: 2,
        6: 3,
    }


def test_first_column_evenly_spaced_and_a_later_game_centred_on_its_feeders() -> None:
    boxes = _boxes(_layout(_top4()))
    step = bi.BOX_HEIGHT + bi.ROW_GAP

    assert (boxes[1].y, boxes[2].y) == (0, step)
    assert boxes[3].y == step // 2  # between games 1 and 2
    assert boxes[6].y == boxes[3].y  # its only upper feeder


def test_lower_section_starts_at_its_first_round() -> None:
    boxes = _boxes(_layout(_top4()))

    assert (boxes[4].y, boxes[5].y) == (0, 0)


def test_links_stay_within_a_section() -> None:
    upper, lower = _layout(_top4()).sections

    assert upper.links == ((1, 3), (2, 3), (3, 6))
    assert lower.links == ((4, 5),)  # 5 -> 6 crosses into the upper bracket


# --- slots ----------------------------------------------------------------------------


def _slot_texts(layout: bi.Layout, game: int) -> list[tuple[str, str]]:
    return [(n.text, i.text) for n, i in _boxes(layout)[game].slots]


def test_unknown_slots_say_where_the_player_comes_from() -> None:
    layout = _layout(_top4())

    assert _slot_texts(layout, 3) == [("Winner of 1", ""), ("Winner of 2", "")]
    assert _slot_texts(layout, 4) == [("Loser of 1", ""), ("Loser of 2", "")]


def test_seeded_slots_before_pairing_show_the_player_without_an_id() -> None:
    assert _slot_texts(_layout(_top4()), 1) == [("Player 1", ""), ("Player 4", "")]


def test_reseeded_slot_is_tbd() -> None:
    """Single elimination top 8: game 5's players are known once paired."""
    t = tournament(
        _top4().rounds[0],
        (_game(1, 1, 8), _game(2, 2, 7), _game(3, 3, 6), _game(4, 4, 5)),
        players=tuple(player(n, rank=n) for n in range(1, 9)),
        cut_to_top=8,
    )

    assert _slot_texts(_layout(t), 5) == [("TBD", ""), ("TBD", "")]


def test_paired_game_shows_the_side_ids_in_their_colours() -> None:
    layout = _layout(_top4((_game(1, 1, 4), _game(2, 2, 3))))

    corp, runner = _boxes(layout)[1].slots

    assert (corp[1].text, corp[1].color) == ("Nuvem", image.CORP)
    assert (runner[1].text, runner[1].color) == ("Zahya", image.RUNNER)


def test_winner_bold_loser_secondary_unreported_plain() -> None:
    layout = _layout(_top4((_game(1, 1, 4, 4), _game(2, 2, 3))))
    boxes = _boxes(layout)

    loser, winner = boxes[1].slots
    assert (winner[0].bold, winner[0].color) == (True, image.TEXT)
    assert (loser[0].bold, loser[0].color) == (False, image.SECONDARY)
    assert all(not s[0].bold and s[0].color == image.TEXT for s in boxes[2].slots)


def test_long_names_are_cut_and_made_safe() -> None:
    players = (player(1, "A" * 40 + "`", rank=1), *TOP4[1:])
    layout = _layout(_top4(players=players))

    name = _boxes(layout)[1].slots[0][0].text

    assert len(name) == bi.NAME_CHARS
    assert name.endswith("…")


def test_unknown_player_and_unknown_id() -> None:
    """Player 1 has no IDs in the export; player 4 is missing from it."""
    players = (player(1, "Player 1", rank=1), *TOP4[1:3])
    t = _top4((_game(1, 1, 4), _game(2, 2, 3)), players=players)

    slot1, slot2 = _boxes(_layout(t))[1].slots

    assert (slot1[1].text, slot1[1].color) == ("—", image.SECONDARY)
    assert slot2[0].text == "Unknown player"


# --- drawing and cache key ------------------------------------------------------------


def test_render_draws_a_png_wide_enough_for_every_column(
    raw_fixture: LoadRaw, fonts: Fonts
) -> None:
    t = parse_tournament(
        raw_fixture("large_top_cut"), tournament_id=4990, fetched_at=FETCHED_AT
    )
    layout = bi.bracket_layout(t, _view(t))

    png = bi.render_png(layout, fonts)

    with Image.open(io.BytesIO(png)) as drawn:
        width, height = drawn.size
    assert png.startswith(b"\x89PNG")
    assert width > layout.columns * bi.COLUMN_GAP
    assert height > sum(s.height for s in layout.sections)


def test_key_is_stable_and_follows_what_is_shown() -> None:
    before = _layout(_top4((_game(1, 1, 4), _game(2, 2, 3))))
    same = _layout(_top4((_game(1, 1, 4), _game(2, 2, 3))))
    reported = _layout(_top4((_game(1, 1, 4, 1), _game(2, 2, 3))))

    assert bi.bracket_key(before) == bi.bracket_key(same)
    assert bi.bracket_key(before) != bi.bracket_key(reported)


# --- message --------------------------------------------------------------------------


def test_bracket_message(fonts: Fonts) -> None:
    t = _top4((_game(1, 1, 4), _game(2, 2, 3)))

    (page,) = bi.bracket_images(t, _view(t), fonts)

    assert page.filename == page.embed.image == "bracket-1.png"
    assert page.embed.title == "Test Cup"
    assert (
        page.embed.url == "https://tournaments.nullsignal.games/tournaments/1/bracket"
    )
    assert page.embed.description == (
        "**Top 4 bracket (double elimination) — in progress**\n"
        "Data from <t:1790856000:R>"
    )
    assert page.embed.footer == "6 games · bold = winner"


def test_bracket_message_uses_the_image_cache(fonts: Fonts) -> None:
    t = _top4()
    keys: list[str] = []

    def cached(key: str, draw: Callable[[], bytes]) -> bytes:
        keys.append(key)
        return b"cached"

    (page,) = bi.bracket_images(t, _view(t), fonts, png=cached)

    assert page.png == b"cached"
    assert keys == [bi.bracket_key(_layout(t))]
