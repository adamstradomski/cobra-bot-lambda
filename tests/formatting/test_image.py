"""Standings and pairings as PNG images (SPEC §9), drawn with the bundled fonts."""

import io
from collections.abc import Callable
from dataclasses import replace

import pytest
from PIL import Image

from builders import FETCHED_AT, pairing, player, seat, tournament
from cobra_bot import fonts as bundled_fonts
from cobra_bot import messages
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.bracket import CutEntry, TopCutView
from cobra_bot.domain.models import Tournament
from cobra_bot.domain.rounds import (
    PairingsView,
    StandingsView,
    pairings_view,
    standings_view,
)
from cobra_bot.formatting import image as c
from cobra_bot.formatting.embed import EMBED_COLOR
from cobra_bot.formatting.image import Cell, Column, Fonts, Table
from cobra_bot.formatting.text import corp_label, runner_label

type LoadRaw = Callable[[str], object]


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
    assert (corp.text, corp.color) == ("Nuvem", c.CORP)
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
    assert corp.text == "X" * 8 + "…"  # not in the map: its fallback, 9 columns


def _id_cell(identity: str, color: str) -> str:
    return c._identity(identity, color).text


@pytest.mark.parametrize(
    ("identity", "color", "shown"),
    [
        ("Nuvem SA: Law of the Land", c.CORP, "Nuvem"),
        ("Haas-Bioroid: Precision Design", c.CORP, "HB PD"),
        ("Weyland Consortium: X", c.CORP, "Weyland"),
        ("Magdalene Keino-Chemutai: X", c.RUNNER, "Magdalene"),
        ("Captain Padma Isbister: X", c.RUNNER, "Padma"),  # an override
        ("Lat: Ethical Freelancer", c.RUNNER, "Lat"),
        ("Abcdefghijklmno: X", c.CORP, "Abcdefgh…"),  # unknown: the fallback
    ],
)
def test_ids_are_always_the_short_name(identity: str, color: str, shown: str) -> None:
    """The same short names as every other reply (identities.py)."""
    assert _id_cell(identity, color) == shown


@pytest.mark.parametrize(
    ("identity", "color", "label"),
    [
        ("Nuvem SA: X", c.CORP, corp_label),
        ("Haas-Bioroid: X", c.CORP, corp_label),
        ("Zahya Sadeghi: X", c.RUNNER, runner_label),
        ('René "Loup" Arcemont: X', c.RUNNER, runner_label),
    ],
)
def test_image_ids_match_the_text_replies(
    identity: str, color: str, label: object
) -> None:
    assert _id_cell(identity, color) == label(identity)  # type: ignore[operator]


def test_unknown_identity_is_the_secondary_dash() -> None:
    cell = c._identity("", c.RUNNER)

    assert (cell.text, cell.color) == ("—", c.SECONDARY)


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
        ["T3", "Alice", "Corp", "Nuvem", "3"],
        ["", "Bob", "Runner", "Zahya", "0"],
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
        ["T2", "Alice", "C Nuvem", "3", "R —", "0", "3"],
        ["", "Bob", "R Zahya", "0", "C —", "–", "0"],
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
    return [
        tuple((Cell(f"{n}.{i}"),) for i in range(size)) for n, size in enumerate(sizes)
    ]


def _sizes(pages: list[tuple[tuple[tuple[Cell, ...], ...], ...]]) -> list[list[int]]:
    return [[len(g) for g in page] for page in pages]


@pytest.mark.parametrize("split", [True, False])
def test_paginate_groups_up_to_max_rows(split: bool) -> None:
    groups = _groups(2, 2, 1)

    assert _sizes(c.paginate_groups(groups, 5, split=split)) == [[2, 2, 1]]


def test_paginate_whole_groups_move_to_the_next_page() -> None:
    """Pairings: a table is never split."""
    assert _sizes(c.paginate_groups(_groups(2, 2, 1), 3, split=False)) == [[2], [2, 1]]


def test_paginate_split_fills_every_page() -> None:
    """Standings: players on equal points may continue on the next page."""
    assert _sizes(c.paginate_groups(_groups(2, 2, 1), 3, split=True)) == [
        [2, 1],
        [1, 1],
    ]


@pytest.mark.parametrize("split", [True, False])
def test_paginate_splits_a_group_longer_than_a_page(split: bool) -> None:
    assert _sizes(c.paginate_groups(_groups(1, 6), 4, split=split)) == (
        [[1, 3], [3]] if split else [[1], [4], [2]]
    )


def test_paginate_keeps_row_order(split: bool = True) -> None:
    groups = _groups(3, 4, 2)

    pages = c.paginate_groups(groups, 4, split=split)

    rows = [row for page in pages for group in page for row in group]
    assert rows == [row for group in groups for row in group]


@pytest.mark.parametrize("split", [True, False])
def test_paginate_empty_is_one_page(split: bool) -> None:
    assert c.paginate_groups([], 4, split=split) == [()]


def _standings_cup(players: int, points: int = 3) -> Tournament:
    roster = tuple(player(n, rank=n, points=points) for n in range(1, players + 1))
    return tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),),
        players=roster,
        tid=4909,
    )


def test_standings_image_message(fonts: Fonts) -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),),
        players=PLAYERS,
        tid=4909,
    )

    (page,) = c.standings_images(t, _standings(t), fonts)

    assert page.filename == "standings-1.png"
    assert page.png.startswith(b"\x89PNG")
    assert page.embed.image == "standings-1.png"
    assert page.embed.title == "Test Cup"
    assert page.embed.url is not None
    assert page.embed.url.endswith("/tournaments/4909/players/standings")
    assert page.embed.description == (
        "**Standings after round 1**\n"
        "-# No top cut on Cobra yet\n"
        "Data from <t:1790856000:R>"
    )
    assert page.embed.footer == "Round 1 · 2 players"  # no page number
    assert page.embed.color == EMBED_COLOR


def test_pages_after_the_first_have_only_image_and_legend(
    fonts: Fonts, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(c, "MAX_ROWS", 2)
    t = _standings_cup(5)

    pages = c.standings_images(t, _standings(t), fonts)

    assert [p.filename for p in pages] == [f"standings-{n}.png" for n in (1, 2, 3)]
    assert [p.embed.footer for p in pages] == [
        f"Round 1 · 5 players · {n} / 3" for n in (1, 2, 3)
    ]
    for later in pages[1:]:
        assert (later.embed.title, later.embed.url, later.embed.description) == (
            None,
            None,
            "",
        )


@pytest.mark.parametrize(
    ("players", "messages_sent", "omitted"),
    [(10, 5, 0), (11, 5, 1), (9, 5, 0), (12, 5, 2)],
)
def test_at_most_five_messages_and_the_rest_counted(
    fonts: Fonts,
    monkeypatch: pytest.MonkeyPatch,
    players: int,
    messages_sent: int,
    omitted: int,
) -> None:
    """FR-14 / AC-15: 5 messages; past them, the last one says how many players
    are missing and links to Cobra. Pages of 2 rows: 10 players fit exactly."""
    monkeypatch.setattr(c, "MAX_ROWS", 2)
    t = _standings_cup(players)

    pages = c.standings_images(t, _standings(t), fonts)

    assert len(pages) == min(messages_sent, -(-players // 2))
    last = pages[-1].embed.description
    if omitted:
        assert last == messages.omitted_entries(
            omitted,
            "https://tournaments.nullsignal.games/tournaments/4909/players/standings",
        )
    else:
        assert "more" not in last


def test_pairings_count_omitted_tables_not_rows(
    fonts: Fonts, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pages of 2 rows hold one table; 7 tables leave 2 out."""
    monkeypatch.setattr(c, "MAX_ROWS", 2)
    players = tuple(player(n) for n in range(1, 15))
    rnd = tuple(
        pairing(n, seat(2 * n - 1, "corp", 3), seat(2 * n, "runner", 0))
        for n in range(1, 8)
    )
    t = tournament(rnd, players=players)

    pages = c.pairings_images(t, _pairings(t), fonts)

    assert len(pages) == 5
    assert pages[-1].embed.description.startswith("…and 2 more — ")


def test_one_page_header_and_omission_together(
    fonts: Fonts, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(c, "MAX_ROWS", 2)
    monkeypatch.setattr(c, "MAX_PAGES", 1)
    t = _standings_cup(3)

    (page,) = c.standings_images(t, _standings(t), fonts)

    header, _, _, note = page.embed.description.split("\n")
    assert header == "**Standings after round 1**"
    assert note.startswith("…and 1 more — ")


def test_large_tournament_fits_the_limits(raw_fixture: LoadRaw, fonts: Fonts) -> None:
    """AC-14: 235 players: at most 5 messages, one image each, under Discord's
    10 MB attachment limit, every player once, in rank order."""
    t = parse_tournament(
        raw_fixture("large_top_cut"), tournament_id=7, fetched_at=FETCHED_AT
    )

    pages = c.standings_images(t, _standings(t), fonts)

    assert len(pages) <= 5
    assert all(len(p.png) < 10_000_000 for p in pages)
    table = c.standings_table(_standings(t))
    shown = [
        row[0].text
        for page in c.paginate_groups(table.groups, c.MAX_ROWS, split=True)
        for group in page
        for row in group
    ]
    assert shown == [str(p.rank) for p in _standings(t).players]
    assert "more" not in pages[-1].embed.description


def test_worlds_sized_pairings_fit_in_five_messages() -> None:
    """145 single-sided tables (World Championship 2026, round 1) are 290 rows:
    they must all fit in the 5 messages."""
    players = tuple(player(n) for n in range(1, 291))
    rnd = tuple(
        pairing(n, seat(2 * n - 1, "corp"), seat(2 * n, "runner"))
        for n in range(1, 146)
    )
    t = tournament(rnd, players=players)

    table = c.pairings_table(t, _pairings(t))

    assert len(c.paginate_groups(table.groups, c.MAX_ROWS, split=False)) <= 5


def test_pairings_legend_has_no_game_key(raw_fixture: LoadRaw, fonts: Fonts) -> None:
    """The image's column headings name the games."""
    t = parse_tournament(raw_fixture("dss"), tournament_id=7, fetched_at=FETCHED_AT)

    (page,) = c.pairings_images(t, _pairings(t), fonts)

    assert page.embed.footer == "Round 3 · 16 tables"


def test_stale_header_is_kept(fonts: Fonts) -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),),
        players=PLAYERS,
        stale=True,
    )

    (page,) = c.standings_images(t, _standings(t), fonts, private=True)

    assert "Tournament is now private — data from" in page.embed.description


# --- fonts --------------------------------------------------------------------------


def test_bundled_fonts_draw_polish_and_accented_letters() -> None:
    """Noto Sans has the Latin Extended letters in names; Pillow's built-in
    font has none of them."""
    loaded = bundled_fonts.load()
    for font in (loaded.regular, loaded.bold):
        missing = bytes(font.getmask(""))  # private use: no glyph
        for letter in "ŻółęąśćńëèïüØōā–—·…":
            assert bytes(font.getmask(letter)) != missing, letter


def test_bundled_fonts_have_their_licence() -> None:
    from importlib import resources

    licence = resources.files("cobra_bot.fonts") / "OFL.txt"
    assert "SIL Open Font License" in licence.read_text(encoding="utf-8")


# --- acceptance criteria on the image tables --------------------------------------


def test_ac01_standings_first_row(raw_fixture: LoadRaw) -> None:
    """AC-01: after round 8, player 1042 first with 22 points."""
    t = parse_tournament(
        raw_fixture("single_sided_top8"), tournament_id=4909, fetched_at=FETCHED_AT
    )
    view = _standings(t)

    first = c.standings_table(view).groups[0][0]

    assert view.after_round == 8
    assert (first[0].text, first[1].text, first[4].text) == ("1", "Player0042", "22")


def test_ac02_bye_at_table_21(raw_fixture: LoadRaw) -> None:
    """AC-02: round 1, table 21 is player 1023's bye."""
    t = parse_tournament(
        raw_fixture("single_sided_top8"), tournament_id=4909, fetched_at=FETCHED_AT
    )
    view = pairings_view(t, 1)
    assert isinstance(view, PairingsView)

    rows = _texts(c.pairings_table(t, view))

    assert ["T21", "Player0023", messages.BYE, "", ""] in rows


def test_ac22_double_sided_shows_both_games(raw_fixture: LoadRaw) -> None:
    """AC-22: every double-sided table shows game 1 and game 2 per player."""
    t = parse_tournament(raw_fixture("dss"), tournament_id=5018, fetched_at=FETCHED_AT)
    view = pairings_view(t, 2)
    assert isinstance(view, PairingsView)

    table = c.pairings_table(t, view)

    assert [col.heading for col in table.columns][2:5:2] == ["Game 1", "Game 2"]
    for group in table.groups:
        if len(group) == 2:  # not a bye
            first, second = group
            assert first[2].text.startswith("C ") and first[4].text.startswith("R ")
            assert second[2].text.startswith("R ") and second[4].text.startswith("C ")


# --- player search ----------------------------------------------------------------


def _player_row(t: Tournament, pid: int) -> list[str]:
    player_ = t.player(pid)
    assert player_ is not None
    (group,) = c.players_table(t, [player_]).groups
    return [cell.text for cell in group[0]]


def test_players_table_columns_after_a_round() -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=PLAYERS
    )

    table = c.players_table(t, list(PLAYERS))

    assert [col.heading for col in table.columns] == [
        "#",
        "Player",
        "Corp",
        "Runner",
        "Pts",
        "SoS",
        "Round 1",
        "Side",
        "Opponent",
        "Score",
    ]
    assert len(table.groups) == 2  # one stripe per player


def test_players_table_before_any_round_has_standings_columns_only() -> None:
    t = tournament(players=PLAYERS)

    table = c.players_table(t, list(PLAYERS))

    assert [col.heading for col in table.columns][-1] == "SoS"
    assert all(len(row) == 6 for group in table.groups for row in group)


def test_player_row_single_sided_from_each_side() -> None:
    """Seat order does not matter: each row is from that player's side."""
    t = tournament(
        (pairing(4, seat(2, "runner", 0), seat(1, "corp", 3)),), players=PLAYERS
    )

    assert _player_row(t, 1)[6:] == ["T4", "Corp", "Bob", "3 – 0"]
    assert _player_row(t, 2)[6:] == ["T4", "Runner", "Alice", "0 – 3"]


def test_player_score_won_bold_lost_secondary() -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=PLAYERS
    )

    (won,) = c.players_table(t, [PLAYERS[0]]).groups[0]
    (lost,) = c.players_table(t, [PLAYERS[1]]).groups[0]

    assert (won[9].color, won[9].bold) == (c.SCORE, True)
    assert (lost[9].color, lost[9].bold) == (c.SECONDARY, False)
    assert (won[7].color, lost[7].color) == (c.CORP, c.RUNNER)


@pytest.mark.parametrize(
    ("first", "second", "draw", "score"),
    [(None, None, False, "–"), (1, 1, True, "ID"), (1, 1, False, "1 – 1")],
)
def test_player_score_without_a_winner(
    first: int | None, second: int | None, draw: bool, score: str
) -> None:
    p = pairing(
        1, seat(1, "corp", first), seat(2, "runner", second), intentional_draw=draw
    )
    t = tournament((p,), players=PLAYERS)

    assert _player_row(t, 1)[9] == score


def test_player_row_double_sided_shows_both_games_and_the_total() -> None:
    t = tournament(
        (pairing(2, seat(1, corp=3, runner=0), seat(2, corp=3, runner=None)),),
        players=PLAYERS,
    )

    assert _player_row(t, 1)[6:] == ["T2", "C 3 · R 0", "Bob", "3 – 3"]
    assert _player_row(t, 2)[6:] == ["T2", "C 3 · R –", "Alice", "3 – 3"]


def test_player_row_bye_and_not_paired() -> None:
    t = tournament((pairing(5, seat(1, None, 3), seat(None)),), players=PLAYERS)

    assert _player_row(t, 1)[6:] == ["T5", "", messages.BYE, ""]
    assert _player_row(t, 2)[6:] == ["—", "", "not paired", ""]


def test_player_row_uses_the_latest_round_during_top_cut(
    raw_fixture: LoadRaw,
) -> None:
    t = parse_tournament(
        raw_fixture("single_sided_top8"), tournament_id=4909, fetched_at=FETCHED_AT
    )

    table = c.players_table(t, [t.players[0]])

    assert table.columns[6].heading == "Round 14"


def test_player_images_message(fonts: Fonts) -> None:
    from cobra_bot.domain.search import search_names

    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=PLAYERS
    )

    (page,) = c.player_images(
        t, search_names(t.players, "alice, zed"), "alice, zed", fonts
    )

    assert page.filename == "players-1.png"
    assert page.embed.footer == "Round 1 · 1 player"
    assert page.embed.description.startswith("**Players matching “alice, zed”**")
    assert page.embed.description.endswith("No players match “zed”.")


# --- image cache key --------------------------------------------------------------


def _table(text: str = "Alice", color: str = c.TEXT, bold: bool = False) -> Table:
    return Table(
        columns=(Column("Player"), Column("Pts", "right")),
        groups=(((Cell(text, color, bold), Cell("3", c.SCORE, True)),),),
    )


def test_table_key_is_stable_for_equal_tables(fonts: Fonts) -> None:
    assert c.table_key(_table(), fonts) == c.table_key(_table(), fonts)
    assert len(c.table_key(_table(), fonts)) == 64


@pytest.mark.parametrize(
    "changed",
    [
        _table(text="Bob"),
        _table(color=c.SECONDARY),
        _table(bold=True),
        Table((Column("Name"), Column("Pts", "right")), _table().groups),
        Table((Column("Player"), Column("Pts")), _table().groups),
        Table(_table().columns, (*_table().groups, *_table().groups)),
    ],
)
def test_table_key_changes_with_anything_drawn(changed: Table, fonts: Fonts) -> None:
    assert c.table_key(changed, fonts) != c.table_key(_table(), fonts)


def test_table_key_changes_with_the_render_version(
    monkeypatch: pytest.MonkeyPatch, fonts: Fonts
) -> None:
    before = c.table_key(_table(), fonts)
    monkeypatch.setattr(c, "RENDER_VERSION", c.RENDER_VERSION + 1)

    assert c.table_key(_table(), fonts) != before


def test_table_key_changes_with_the_colours(
    monkeypatch: pytest.MonkeyPatch, fonts: Fonts
) -> None:
    before = c.table_key(_table(), fonts)
    monkeypatch.setattr(c, "STRIPE", "#000000")

    assert c.table_key(_table(), fonts) != before


def test_table_key_changes_with_the_fonts(fonts: Fonts) -> None:
    """New font files draw new images even if `RENDER_VERSION` is not bumped."""
    other = replace(fonts, digest="0" * 64)

    assert c.table_key(_table(), other) != c.table_key(_table(), fonts)


def test_draw_replaces_render_png(fonts: Fonts) -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=PLAYERS
    )
    seen: list[Table] = []

    def draw(table: Table) -> bytes:
        seen.append(table)
        return b"cached"

    (page,) = c.standings_images(t, _standings(t), fonts, draw=draw)

    assert page.png == b"cached"
    assert seen == [c.standings_table(_standings(t))]


# --- top cut ------------------------------------------------------------------------


def _cut_game(winner: int | None) -> Tournament:
    """One cut game: Alice (Corp) against Bob (Runner)."""
    return tournament(
        (
            pairing(
                7,
                seat(1, "corp", winner=None if winner is None else winner == 1),
                seat(2, "runner", winner=None if winner is None else winner == 2),
                elimination=True,
            ),
        ),
        players=PLAYERS,
    )


def test_cut_pairings_columns_name_the_game_and_the_result() -> None:
    table = c.pairings_table(_cut_game(2), _pairings(_cut_game(2)))

    assert [col.heading for col in table.columns] == [
        "Game",
        "Player",
        "Side",
        "ID",
        "W/L",
    ]


def test_cut_game_winner_bold_with_w_loser_secondary_with_l() -> None:
    t = _cut_game(2)
    ((corp, runner),) = c.pairings_table(t, _pairings(t)).groups

    assert [cell.text for cell in corp] == ["G7", "Alice", "Corp", "Nuvem", "L"]
    assert (corp[1].color, corp[1].bold) == (c.SECONDARY, False)
    assert [cell.text for cell in runner] == ["", "Bob", "Runner", "Zahya", "W"]
    assert (runner[1].color, runner[1].bold) == (c.TEXT, True)


def test_unreported_cut_game_shows_dashes_and_plain_names() -> None:
    t = _cut_game(None)
    ((corp, runner),) = c.pairings_table(t, _pairings(t)).groups

    assert (corp[4].text, runner[4].text) == ("–", "–")
    assert not corp[1].bold and not runner[1].bold


def test_player_row_in_a_cut_game_shows_w_or_l() -> None:
    t = _cut_game(2)

    rows = _texts(c.players_table(t, list(PLAYERS)))

    assert rows[0][6:] == ["G7", "Corp", "Bob", "L"]
    assert rows[1][6:] == ["G7", "Runner", "Alice", "W"]


def test_player_row_in_an_unreported_cut_game() -> None:
    t = _cut_game(None)

    assert _texts(c.players_table(t, list(PLAYERS)))[0][9] == "–"


def _entry(rank: int | None, pid: int, *, out: bool, seed: int | None = 1) -> CutEntry:
    p = PLAYERS[pid - 1]
    return CutEntry(rank, pid, p, seed, 2, 1 if not out else 2, out)


def test_top_cut_table_columns() -> None:
    view = TopCutView(2, "in_progress", (_entry(None, 1, out=False),))

    assert [col.heading for col in c.top_cut_table(view).columns] == [
        "#",
        "Player",
        "Corp",
        "Runner",
        "W–L",
        "Seed",
    ]


def test_top_cut_rows_still_in_bold_out_secondary_undecided_rank_blank() -> None:
    view = TopCutView(
        2,
        "in_progress",
        (_entry(None, 1, out=False, seed=2), _entry(2, 2, out=True, seed=None)),
    )

    first, second = (row for group in c.top_cut_table(view).groups for row in group)

    assert [cell.text for cell in first] == ["", "Alice", "Nuvem", "—", "2–1", "2"]
    assert (first[1].bold, first[4].bold) == (True, True)
    assert [cell.text for cell in second] == ["2", "Bob", "—", "Zahya", "2–2", ""]
    assert (second[1].color, second[4].bold) == (c.SECONDARY, False)


def test_top_cut_row_without_a_swiss_record() -> None:
    view = TopCutView(1, "finished", (CutEntry(1, 9, None, 1, 3, 0, False),))

    (row,) = (r for group in c.top_cut_table(view).groups for r in group)

    assert [cell.text for cell in row][:4] == ["1", "Unknown player", "—", "—"]


def test_top_cut_images_message(raw_fixture: LoadRaw, fonts: Fonts) -> None:
    from cobra_bot.domain.bracket import top_cut_view

    t = parse_tournament(
        raw_fixture("single_sided_top8"), tournament_id=4909, fetched_at=FETCHED_AT
    )
    view = top_cut_view(t)
    assert isinstance(view, TopCutView)

    (page,) = c.top_cut_images(t, view, fonts)

    assert page.filename == "top-cut-1.png"
    assert page.png.startswith(b"\x89PNG")
    assert page.embed.description == (
        "**Top 8 cut — finished**\nData from <t:1790856000:R>"
    )
    assert page.embed.footer == "Top 8 · 8 players · W–L = games won and lost"
    assert page.embed.url is not None
    assert page.embed.url.endswith("/tournaments/4909/players/standings")


def test_cut_pairings_image_footer_counts_games(
    raw_fixture: LoadRaw, fonts: Fonts
) -> None:
    t = parse_tournament(
        raw_fixture("single_sided_top8"), tournament_id=4909, fetched_at=FETCHED_AT
    )
    from cobra_bot.domain.rounds import pairings_view

    view = pairings_view(t, 9)
    assert isinstance(view, PairingsView)

    (page,) = c.pairings_images(t, view, fonts)

    assert page.embed.footer == "Round 9 · 4 games"
    assert page.embed.description.startswith("**Top cut round 1 pairings — complete**")
