"""Layout C: the table as a PNG. Tests use Pillow's built-in font, so they do not
depend on the fonts installed on the machine."""

import io
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image, ImageFont

from builders import FETCHED_AT, pairing, player, seat, tournament
from cobra_bot import messages
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.models import Tournament
from cobra_bot.domain.rounds import (
    PairingsView,
    StandingsView,
    pairings_view,
    standings_view,
)
from cobra_bot.preview import image as c
from cobra_bot.preview.image import Cell, Column, Fonts, Table

type LoadRaw = Callable[[str], object]


@pytest.fixture(scope="module")
def fonts() -> Fonts:
    font = ImageFont.load_default(c.FONT_SIZE)
    return Fonts(font, font)


def _standings(t: Tournament) -> StandingsView:
    view = standings_view(t)
    assert isinstance(view, StandingsView)
    return view


def _pairings(t: Tournament) -> PairingsView:
    view = pairings_view(t)
    assert isinstance(view, PairingsView)
    return view


def _texts(table: Table) -> list[list[str]]:
    return [[cell.text for cell in row] for group in table.groups for row in group]


PLAYERS = (
    player(1, "Alice", rank=1, points=3, sos="1.5", corp="Nuvem SA: Law of the Land"),
    player(2, "Bob", rank=2, points=0, runner="Zahya Sadeghi: Versatile Smuggler"),
)


# --- standings ----------------------------------------------------------------------


def test_standings_columns_ids_before_points_and_sos() -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=PLAYERS
    )

    table = c.standings_table(_standings(t))

    assert [(col.heading, col.align) for col in table.columns] == [
        (messages.RANK, "right"),
        (messages.PLAYER, "left"),
        (messages.CORP, "left"),
        (messages.RUNNER, "left"),
        (messages.POINTS, "right"),
        (messages.SOS, "right"),
    ]


def test_standings_row_values_and_colours() -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=PLAYERS
    )

    rank, name, corp, runner, points, sos = c.standings_table(_standings(t)).groups[0][
        0
    ]

    assert (rank.text, name.text, points.text, sos.text) == ("1", "Alice", "3", "1.500")
    assert name.bold and points.bold
    assert (points.color, sos.color) == (c.SCORE, c.SECONDARY)
    assert (corp.text, corp.color) == ("Nuvem SA", c.CORP)
    assert (runner.text, runner.color) == (messages.UNKNOWN_IDENTITY, c.SECONDARY)


def test_standings_groups_by_points() -> None:
    players = (
        player(1, rank=1, points=6),
        player(2, rank=2, points=6),
        player(3, rank=3, points=3),
    )
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=players
    )

    groups = c.standings_table(_standings(t)).groups

    assert [len(g) for g in groups] == [2, 1]


def test_long_names_and_ids_are_cut_and_made_safe() -> None:
    p = player(1, "A" * 40 + "\x1b[31m", corp="X" * 40)
    t = tournament((pairing(1, seat(1, "corp", 3), seat(None)),), players=(p,))

    _, name, corp, _, _, _ = c.standings_table(_standings(t)).groups[0][0]

    assert name.text == "A" * (c.NAME_CHARS - 1) + "…"
    assert corp.text == "X" * (c.ID_CHARS - 1) + "…"


# --- pairings -----------------------------------------------------------------------


def test_single_sided_corp_first_winner_bold_loser_secondary() -> None:
    t = tournament(players=PLAYERS)
    view = PairingsView(
        1, (pairing(3, seat(2, "runner", 0), seat(1, "corp", 3)),), True, False
    )

    table = c.pairings_table(t, view)

    assert [col.heading for col in table.columns] == [
        messages.TABLE,
        messages.PLAYER,
        messages.SIDE,
        messages.IDENTITY,
        messages.POINTS,
    ]
    assert _texts(table) == [
        ["T3", "Alice", "Corp", "Nuvem SA", "3"],
        ["", "Bob", "Runner", "Zahya Sadeghi", "0"],
    ]
    (winner, loser) = table.groups[0]
    assert winner[1].bold and winner[1].color == c.TEXT
    assert not loser[1].bold and loser[1].color == c.SECONDARY


@pytest.mark.parametrize(
    ("first", "second", "draw", "shown"),
    [
        (None, None, False, ["–", "–"]),
        (1, 1, False, ["1", "1"]),
        (1, 1, True, ["ID", "ID"]),
    ],
)
def test_no_winner_leaves_both_names_plain(
    first: int | None, second: int | None, draw: bool, shown: list[str]
) -> None:
    t = tournament(players=PLAYERS)
    p = pairing(
        1, seat(1, "corp", first), seat(2, "runner", second), intentional_draw=draw
    )

    table = c.pairings_table(t, PairingsView(1, (p,), True, False))

    rows = table.groups[0]
    assert [row[4].text for row in rows] == shown
    assert all(not row[1].bold and row[1].color == c.TEXT for row in rows)


def test_double_sided_columns_and_game_cells() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(2, seat(1, corp=3, runner=0), seat(2, corp=None, runner=0))

    table = c.pairings_table(t, PairingsView(1, (p,), False, False))

    assert [col.heading for col in table.columns] == [
        messages.TABLE,
        messages.PLAYER,
        "Game 1",
        "",
        "Game 2",
        "",
        messages.TOTAL,
    ]
    assert _texts(table) == [
        ["T2", "Alice", "C Nuvem SA", "3", "R —", "0", "3"],
        ["", "Bob", "R Zahya Sadeghi", "0", "C —", "–", "0"],
    ]


@pytest.mark.parametrize(("sides", "columns"), [("corp", 5), (None, 7)])
def test_bye_row_fills_every_column(sides: str | None, columns: int) -> None:
    t = tournament(players=PLAYERS)
    other = (
        pairing(1, seat(1, "corp", 3), seat(2, "runner", 0))
        if sides
        else pairing(1, seat(1, corp=3, runner=0), seat(2, corp=0, runner=3))
    )
    bye = pairing(2, seat(None), seat(1, None, 3))

    table = c.pairings_table(t, PairingsView(1, (bye, other), True, False))

    bye_row = _texts(table)[-1]
    assert bye_row == ["T2", "Alice", messages.BYE] + [""] * (columns - 3)


def test_tables_in_table_order() -> None:
    t = tournament(players=PLAYERS)
    view = PairingsView(
        1,
        (
            pairing(5, seat(1, "corp"), seat(2, "runner")),
            pairing(1, seat(2, "corp"), seat(1, "runner")),
        ),
        False,
        False,
    )

    assert [g[0][0].text for g in c.pairings_table(t, view).groups] == ["T1", "T5"]


# --- drawing ------------------------------------------------------------------------


def test_render_png_size_follows_rows(fonts: Fonts) -> None:
    table = Table(
        columns=(Column("A"), Column("B", "right")),
        groups=(
            ((Cell("x"), Cell("1")), (Cell("y"), Cell(""))),
            ((Cell("z"), Cell("2")),),
        ),
    )

    png = c.render_png(table, fonts)

    with Image.open(io.BytesIO(png)) as img:
        assert img.format == "PNG"
        assert img.height == 2 * c.PADDING_Y + c.HEADING_HEIGHT + 3 * c.ROW_HEIGHT
        assert img.getpixel((1, 1)) == (0x2B, 0x2D, 0x31)  # BACKGROUND


def test_render_png_stripes_every_other_group(fonts: Fonts) -> None:
    table = Table(
        columns=(Column("A"),),
        groups=(((Cell("x"),),), ((Cell("y"),),)),
    )

    with Image.open(io.BytesIO(c.render_png(table, fonts))) as img:
        first = c.PADDING_Y + c.HEADING_HEIGHT + 2
        second = first + c.ROW_HEIGHT
        assert img.getpixel((1, first)) == (0x2B, 0x2D, 0x31)
        assert img.getpixel((1, second)) == (0x31, 0x33, 0x38)  # STRIPE


def test_fixture_renders(raw_fixture: LoadRaw, fonts: Fonts) -> None:
    t = parse_tournament(raw_fixture("dss"), tournament_id=7, fetched_at=FETCHED_AT)

    png = c.render_png(c.pairings_table(t, _pairings(t)), fonts)

    assert png.startswith(b"\x89PNG")


# --- pages and messages -------------------------------------------------------------


def _groups(*sizes: int) -> list[tuple[tuple[Cell, ...], ...]]:
    return [tuple((Cell(str(i)),) for i in range(size)) for size in sizes]


def test_paginate_groups_up_to_max_rows() -> None:
    groups = _groups(2, 2, 1)

    assert [len(p) for p in c.paginate_groups(groups, 5)] == [3]
    assert [len(p) for p in c.paginate_groups(groups, 4)] == [2, 1]


def test_paginate_groups_keeps_an_oversized_group_whole() -> None:
    groups = _groups(1, 6, 1)

    assert [len(p) for p in c.paginate_groups(groups, 4)] == [1, 1, 1]


def test_paginate_groups_empty_is_one_page() -> None:
    assert c.paginate_groups([], 4) == [()]


def test_c_standings_message_embeds_the_image(fonts: Fonts) -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),),
        players=PLAYERS,
        tid=4909,
    )

    ((payload, file),) = c.c_standings(t, _standings(t), fonts)

    (embed,) = payload["embeds"]  # type: ignore[misc]
    assert embed["title"] == "Test Cup"
    assert embed["url"].endswith("/tournaments/4909/players/standings")
    assert embed["image"] == {"url": "attachment://standings-1.png"}
    assert embed["description"].startswith("**Standings after round 1**")
    assert embed["footer"] == {"text": "Round 1 · 2 players"}
    assert payload["attachments"] == [{"id": 0, "filename": "standings-1.png"}]
    assert payload["allowed_mentions"] == {"parse": []}
    assert (file.filename, file.content_type) == ("standings-1.png", "image/png")
    assert file.content.startswith(b"\x89PNG")


def test_c_pages_number_their_files_and_footers(
    fonts: Fonts, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(c, "MAX_ROWS", 1)
    players = (player(1, rank=1, points=3), player(2, rank=2, points=0))
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=players
    )

    pages = c.c_standings(t, _standings(t), fonts)

    assert [f.filename for _, f in pages] == ["standings-1.png", "standings-2.png"]
    footers = [p["embeds"][0]["footer"]["text"] for p, _ in pages]  # type: ignore[index]
    assert footers == ["Round 1 · 2 players · 1 / 2", "Round 1 · 2 players · 2 / 2"]


def test_c_pairings_legend_has_no_game_key(raw_fixture: LoadRaw, fonts: Fonts) -> None:
    """The image's column headings name the games."""
    t = parse_tournament(raw_fixture("dss"), tournament_id=7, fetched_at=FETCHED_AT)

    ((payload, _),) = c.c_pairings(t, _pairings(t), fonts)

    assert payload["embeds"][0]["footer"] == {"text": "Round 3 · 16 tables"}  # type: ignore[index]


# --- fonts --------------------------------------------------------------------------


def test_load_fonts_takes_the_first_pair_that_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded: list[Path] = []
    monkeypatch.setattr(c, "_truetype", lambda path: loaded.append(path) or path)
    (tmp_path / "r2.ttf").touch()
    (tmp_path / "b2.ttf").touch()
    (tmp_path / "r1.ttf").touch()  # its bold is missing

    c.load_fonts(
        candidates=[
            (tmp_path / "r1.ttf", tmp_path / "b1.ttf"),
            (tmp_path / "r2.ttf", tmp_path / "b2.ttf"),
        ]
    )

    assert loaded == [tmp_path / "r2.ttf", tmp_path / "b2.ttf"]


def test_load_fonts_without_any_font_fails(tmp_path: Path) -> None:
    with pytest.raises(c.FontNotFound):
        c.load_fonts(candidates=[(tmp_path / "r.ttf", tmp_path / "b.ttf")])


def test_explicit_font_that_cannot_load_fails(tmp_path: Path) -> None:
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"not a font")

    with pytest.raises(c.FontNotFound, match=r"broken.ttf"):
        c.load_fonts(broken)


def test_explicit_font_is_used_for_bold_too(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[Path] = []
    monkeypatch.setattr(c, "_truetype", lambda path: loaded.append(path) or path)

    c.load_fonts(Path("x.ttf"))

    assert loaded == [Path("x.ttf"), Path("x.ttf")]
