"""Standings, pairings, top cut and players found as a PNG image in an embed
(docs/spec/output.md).

Full colours on every client and real columns with headings. The text cannot be
selected or searched. The embed holds the title link and header lines
(`formatting.header`) and a short legend; a long table is split evenly into
pages of at most `MAX_ROWS` rows, at most `MAX_PAGES`, an embed each, all sent
in one message.

Drawing is in memory and the fonts are injected (`cobra_bot.fonts.load`), so
this module touches no files.
"""

import hashlib
import io
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from cobra_bot import messages
from cobra_bot.domain.bracket import CutEntry, TopCutView
from cobra_bot.domain.models import Pairing, Player, Seat, Tournament
from cobra_bot.domain.rounds import PairingsView, StandingsView
from cobra_bot.domain.search import NamesResult
from cobra_bot.formatting import header
from cobra_bot.formatting.embed import EMBED_COLOR, MAX_PAGES, Embed, ImagePage
from cobra_bot.formatting.header import Header
from cobra_bot.formatting.text import code_text, corp_label, fit, runner_label

# Bump when the drawing changes in a way the cells, style constants and fonts in
# `table_key` do not show, so cached images are not reused (image_cache.py).
RENDER_VERSION = 1
MAX_ROWS = 60  # per image: 145 Worlds tables (290 rows) fit in 5 pages
CUT_SIZES = (8, 16, 32)  # rows the first of several pages holds at least
NAME_CHARS = 28

# Discord's dark theme.
BACKGROUND = "#2b2d31"
STRIPE = "#313338"
RULE = "#3f4147"
TEXT = "#dbdee1"
SECONDARY = "#949ba4"
SCORE = "#f0b232"
CORP = "#7998ec"  # NSG Corp card-back blue (hue 224), lightened to read on BACKGROUND
RUNNER = "#dd4847"  # NSG Runner card-back red

# Pixels, drawn at twice the displayed size so text stays sharp.
FONT_SIZE = 30
ROW_HEIGHT = 46
HEADING_HEIGHT = 52
PADDING_X = 28
PADDING_Y = 18
COLUMN_GAP = 34

type Font = ImageFont.FreeTypeFont | ImageFont.ImageFont
type Draw = Callable[[Table], bytes]  # a page's table -> its PNG
type Align = Literal["left", "right"]


@dataclass(frozen=True)
class Fonts:
    regular: Font
    bold: Font
    digest: str  # SHA-256 of the font files, so new fonts draw new cached images


@dataclass(frozen=True)
class Cell:
    text: str
    color: str = TEXT
    bold: bool = False


@dataclass(frozen=True)
class Column:
    heading: str
    align: Align = "left"


type Row = tuple[Cell, ...]
type Group = tuple[Row, ...]  # rows on one background stripe


@dataclass(frozen=True)
class Table:
    columns: tuple[Column, ...]
    groups: tuple[Group, ...]  # stripes alternate between groups


def render_png(table: Table, fonts: Fonts) -> bytes:
    widths = _column_widths(table, fonts)
    width = 2 * PADDING_X + sum(widths) + COLUMN_GAP * (len(widths) - 1)
    rows = sum(len(group) for group in table.groups)
    height = 2 * PADDING_Y + HEADING_HEIGHT + rows * ROW_HEIGHT
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    y = PADDING_Y
    headings = tuple(Cell(c.heading, SECONDARY, bold=True) for c in table.columns)
    _draw_row(draw, fonts, table.columns, widths, headings, y, HEADING_HEIGHT)
    y += HEADING_HEIGHT
    draw.line([(PADDING_X, y - 1), (width - PADDING_X, y - 1)], fill=RULE, width=2)
    for index, group in enumerate(table.groups):
        if index % 2 == 1:
            bottom = y + len(group) * ROW_HEIGHT - 1
            draw.rectangle([(0, y), (width, bottom)], fill=STRIPE)
        for row in group:
            _draw_row(draw, fonts, table.columns, widths, row, y, ROW_HEIGHT)
            y += ROW_HEIGHT
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def table_key(table: Table, fonts: Fonts) -> str:
    """SHA-256 of everything the image of `table` shows: cells, columns, the
    style constants, the fonts and `RENDER_VERSION`. Equal keys draw equal PNGs."""
    payload = {
        "version": RENDER_VERSION,
        "fonts": fonts.digest,
        "style": [
            FONT_SIZE,
            ROW_HEIGHT,
            HEADING_HEIGHT,
            PADDING_X,
            PADDING_Y,
            COLUMN_GAP,
            BACKGROUND,
            STRIPE,
            RULE,
        ],
        "columns": [[c.heading, c.align] for c in table.columns],
        "groups": [
            [[[cell.text, cell.color, cell.bold] for cell in row] for row in group]
            for group in table.groups
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def _column_widths(table: Table, fonts: Fonts) -> list[int]:
    widths = [_text_width(fonts.bold, c.heading) for c in table.columns]
    for group in table.groups:
        for row in group:
            for i, cell in enumerate(row):
                font = fonts.bold if cell.bold else fonts.regular
                widths[i] = max(widths[i], _text_width(font, cell.text))
    return widths


def _text_width(font: Font, text: str) -> int:
    return int(font.getlength(text)) + 1 if text else 0


def _draw_row(
    draw: ImageDraw.ImageDraw,
    fonts: Fonts,
    columns: Sequence[Column],
    widths: Sequence[int],
    row: Row,
    top: int,
    height: int,
) -> None:
    x = PADDING_X
    middle = top + height // 2
    for column, width, cell in zip(columns, widths, row, strict=True):
        if cell.text:
            font = fonts.bold if cell.bold else fonts.regular
            right = column.align == "right"
            draw.text(
                (x + width if right else x, middle),
                cell.text,
                fill=cell.color,
                font=font,
                anchor="rm" if right else "lm",
            )
        x += width + COLUMN_GAP


# --- tables -----------------------------------------------------------------


def standings_table(view: StandingsView) -> Table:
    groups: list[list[Row]] = []
    previous: Player | None = None
    for p in view.players:
        if previous is None or p.match_points != previous.match_points:
            groups.append([])
        groups[-1].append(
            (
                Cell(str(p.rank)),
                Cell(_name(p), bold=True),
                _identity(p.corp_identity, CORP),
                _identity(p.runner_identity, RUNNER),
                Cell(str(p.match_points), SCORE, bold=True),
                Cell(f"{p.sos:.3f}", SECONDARY),
            )
        )
        previous = p
    return Table(
        columns=(
            Column(messages.RANK, "right"),
            Column(messages.PLAYER),
            Column(messages.CORP),
            Column(messages.RUNNER),
            Column(messages.POINTS, "right"),
            Column(messages.SOS, "right"),
        ),
        groups=tuple(tuple(g) for g in groups),
    )


def pairings_table(t: Tournament, view: PairingsView) -> Table:
    ordered = sorted(view.pairings, key=lambda p: p.table)
    if any(p.double_sided for p in ordered):
        return Table(
            columns=(
                Column(messages.TABLE),
                Column(messages.PLAYER),
                Column(messages.game_heading(1)),
                Column("", "right"),
                Column(messages.game_heading(2)),
                Column("", "right"),
                Column(messages.TOTAL, "right"),
            ),
            groups=tuple(_double_sided(t, p) for p in ordered),
        )
    elimination = any(p.elimination for p in ordered)
    return Table(
        columns=(
            Column(messages.GAME if elimination else messages.TABLE),
            Column(messages.PLAYER),
            Column(messages.SIDE),
            Column(messages.IDENTITY),
            Column(messages.RESULT if elimination else messages.POINTS, "right"),
        ),
        groups=tuple(_single_sided(t, p) for p in ordered),
    )


def table_label(pairing: Pairing) -> str:
    """`T12` for a table, `G12` for a top-cut game."""
    return f"{'G' if pairing.elimination else 'T'}{pairing.table}"


def _single_sided(t: Tournament, pairing: Pairing) -> Group:
    label = table_label(pairing)
    if pairing.is_bye:
        return (_bye_row(t, pairing, columns=5),)
    s1, s2 = pairing.seat1, pairing.seat2
    corp, runner = (s1, s2) if s1.role == "corp" else (s2, s1)
    styles = (
        _results(corp.winner, runner.winner)
        if pairing.elimination
        else _styles(pairing, corp.combined_score, runner.combined_score)
    )
    rows = []
    for seat, side, color, (points, style), label_text in (
        (corp, messages.CORP, CORP, styles[0], label),
        (runner, messages.RUNNER, RUNNER, styles[1], ""),
    ):
        player = _player(t, seat)
        identity = (
            (player.corp_identity if side == messages.CORP else player.runner_identity)
            if player
            else None
        )
        rows.append(
            (
                Cell(label_text),
                Cell(_seat_name(player), *style),
                Cell(side, color),
                _identity(identity, color),
                Cell(points, SCORE, bold=True),
            )
        )
    return tuple(rows)


def _double_sided(t: Tournament, pairing: Pairing) -> Group:
    label = f"T{pairing.table}"
    if pairing.is_bye:
        return (_bye_row(t, pairing, columns=7),)
    s1, s2 = pairing.seat1, pairing.seat2
    styles = _styles(pairing, _total(s1), _total(s2))
    p1, p2 = _player(t, s1), _player(t, s2)
    return (
        (
            Cell(label),
            Cell(_seat_name(p1), *styles[0][1]),
            _game(messages.CORP_TAG, p1.corp_identity if p1 else None, CORP),
            Cell(_shown(s1.corp_score), SCORE),
            _game(messages.RUNNER_TAG, p1.runner_identity if p1 else None, RUNNER),
            Cell(_shown(s1.runner_score), SCORE),
            Cell(styles[0][0], SCORE, bold=True),
        ),
        (
            Cell(""),
            Cell(_seat_name(p2), *styles[1][1]),
            _game(messages.RUNNER_TAG, p2.runner_identity if p2 else None, RUNNER),
            Cell(_shown(s2.runner_score), SCORE),
            _game(messages.CORP_TAG, p2.corp_identity if p2 else None, CORP),
            Cell(_shown(s2.corp_score), SCORE),
            Cell(styles[1][0], SCORE, bold=True),
        ),
    )


type Style = tuple[str, bool]  # colour, bold


def _styles(
    pairing: Pairing, first: int | None, second: int | None
) -> tuple[tuple[str, Style], tuple[str, Style]]:
    """Points as shown and the name style: the winner bold, the loser
    secondary."""
    plain: Style = (TEXT, False)
    if pairing.intentional_draw:
        return (messages.INTENTIONAL_DRAW, plain), (messages.INTENTIONAL_DRAW, plain)
    shown = (_shown(first), _shown(second))
    if first is None or second is None or first == second:
        return (shown[0], plain), (shown[1], plain)
    won: Style = (TEXT, True)
    lost: Style = (SECONDARY, False)
    return (
        (shown[0], won if first > second else lost),
        (shown[1], lost if first > second else won),
    )


def _results(
    first: bool | None, second: bool | None
) -> tuple[tuple[str, Style], tuple[str, Style]]:
    """A top-cut game: the winner `W` and bold, the loser `L` and secondary;
    `–` and plain while unreported."""
    if not first and not second:
        plain: Style = (TEXT, False)
        return (messages.NO_RESULT, plain), (messages.NO_RESULT, plain)
    won: tuple[str, Style] = (messages.WIN, (TEXT, True))
    lost: tuple[str, Style] = (messages.LOSS, (SECONDARY, False))
    return (won, lost) if first else (lost, won)


def _bye_row(t: Tournament, pairing: Pairing, *, columns: int) -> Row:
    """Table, player, `BYE` in the third column, the rest empty."""
    (player_id,) = pairing.player_ids or (None,)
    player = t.player(player_id) if player_id is not None else None
    cells = (
        Cell(f"T{pairing.table}"),
        Cell(_seat_name(player)),
        Cell(messages.BYE, SECONDARY),
    )
    return cells + (Cell(""),) * (columns - len(cells))


def _game(tag: str, identity: str | None, color: str) -> Cell:
    cell = _identity(identity, color)
    return Cell(f"{tag} {cell.text}", cell.color)


def _identity(identity: str | None, color: str) -> Cell:
    """The ID's short name from `identities.py` (`Weyland Consortium` ->
    `Weyland`), the same as in every other reply; `color` is CORP or RUNNER and
    picks the side's map. An unknown ID is the secondary `—`."""
    label = (corp_label if color == CORP else runner_label)(identity)
    if label == messages.UNKNOWN_IDENTITY:
        return Cell(label, SECONDARY)
    return Cell(label, color)


def _name(p: Player) -> str:
    return fit(code_text(p.name), NAME_CHARS)


def _seat_name(player: Player | None) -> str:
    return _name(player) if player else messages.UNKNOWN_PLAYER


def _player(t: Tournament, seat: Seat) -> Player | None:
    return t.player(seat.player_id) if seat.player_id is not None else None


def _shown(points: int | None) -> str:
    return messages.NO_RESULT if points is None else str(points)


def _total(seat: Seat) -> int | None:
    if seat.corp_score is None and seat.runner_score is None:
        return None
    return (seat.corp_score or 0) + (seat.runner_score or 0)


def players_table(t: Tournament, players: Sequence[Player]) -> Table:
    """One row per player: the standings columns, then the player's table in
    the latest round (Swiss or top cut), the side played there, the opponent
    and the score from the player's side. Before any round only the standings
    columns."""
    latest = len(t.rounds)
    columns: tuple[Column, ...] = (
        Column(messages.RANK, "right"),
        Column(messages.PLAYER),
        Column(messages.CORP),
        Column(messages.RUNNER),
        Column(messages.POINTS, "right"),
        Column(messages.SOS, "right"),
    )
    if latest:
        columns += (
            Column(messages.player_round(latest)),
            Column(messages.SIDE),
            Column(messages.OPPONENT),
            Column(messages.SCORE, "right"),
        )
    rows = []
    for p in players:
        row: Row = (
            Cell(str(p.rank)),
            Cell(_name(p), bold=True),
            _identity(p.corp_identity, CORP),
            _identity(p.runner_identity, RUNNER),
            Cell(str(p.match_points), SCORE, bold=True),
            Cell(f"{p.sos:.3f}", SECONDARY),
        )
        if latest:
            row += _latest_pairing(t, p, latest)
        rows.append((row,))
    return Table(columns=columns, groups=tuple(rows))


def _latest_pairing(t: Tournament, p: Player, number: int) -> Row:
    pairing = next((x for x in t.rounds[number - 1] if p.id in x.player_ids), None)
    if pairing is None:
        return (
            Cell(messages.UNKNOWN_IDENTITY, SECONDARY),
            Cell(""),
            Cell(messages.NOT_PAIRED, SECONDARY),
            Cell(""),
        )
    label = Cell(table_label(pairing))
    if pairing.is_bye:
        return (label, Cell(""), Cell(messages.BYE, SECONDARY), Cell(""))
    mine, theirs = (
        (pairing.seat1, pairing.seat2)
        if pairing.seat1.player_id == p.id
        else (pairing.seat2, pairing.seat1)
    )
    if pairing.double_sided:
        side = Cell(
            f"{messages.CORP_TAG} {_shown(mine.corp_score)} · "
            f"{messages.RUNNER_TAG} {_shown(mine.runner_score)}",
            SECONDARY,
        )
        points = (_total(mine), _total(theirs))
    else:
        corp = mine.role == "corp"
        side = Cell(
            messages.CORP if corp else messages.RUNNER, CORP if corp else RUNNER
        )
        points = (mine.combined_score, theirs.combined_score)
    if pairing.elimination:
        (shown, (color, bold)), _ = _results(mine.winner, theirs.winner)
        result = (
            Cell(shown, SECONDARY)
            if color == SECONDARY or shown == messages.NO_RESULT
            else Cell(shown, SCORE, bold)
        )
        return (label, side, Cell(_seat_name(_player(t, theirs))), result)
    return (
        label,
        side,
        Cell(_seat_name(_player(t, theirs))),
        _score(pairing, *points),
    )


def _score(pairing: Pairing, mine: int | None, theirs: int | None) -> Cell:
    """`3 – 0` from the player's side: bold when won, secondary when lost; `–`
    while unreported, `ID` for an intentional draw."""
    (shown, (color, bold)), (other, _) = _styles(pairing, mine, theirs)
    if pairing.intentional_draw:
        return Cell(messages.INTENTIONAL_DRAW, SCORE)
    if mine is None and theirs is None:
        return Cell(messages.NO_RESULT, SECONDARY)
    return Cell(f"{shown} – {other}", SECONDARY if color == SECONDARY else SCORE, bold)


def top_cut_table(view: TopCutView) -> Table:
    """Like standings: place (blank while not decided), player, IDs, games won
    and lost in the cut, seed. Players still in the cut bold, those out
    secondary."""
    return Table(
        columns=(
            Column(messages.RANK, "right"),
            Column(messages.PLAYER),
            Column(messages.CORP),
            Column(messages.RUNNER),
            Column(messages.RECORD, "right"),
            Column(messages.SEED, "right"),
        ),
        groups=tuple((_cut_row(e),) for e in view.entries),
    )


def _cut_row(e: CutEntry) -> Row:
    p = e.player
    name = _name(p) if p else messages.UNKNOWN_PLAYER
    return (
        Cell(str(e.rank) if e.rank is not None else ""),
        Cell(name, SECONDARY) if e.eliminated else Cell(name, bold=True),
        _identity(p.corp_identity if p else None, CORP),
        _identity(p.runner_identity if p else None, RUNNER),
        Cell(messages.record(e.wins, e.losses), SCORE, bold=not e.eliminated),
        Cell(str(e.seed) if e.seed is not None else "", SECONDARY),
    )


# --- messages ---------------------------------------------------------------


def standings_images(
    t: Tournament,
    view: StandingsView,
    fonts: Fonts,
    *,
    private: bool = False,
    draw: Draw | None = None,
) -> tuple[ImagePage, ...]:
    footer = messages.compact_standings_footer(view.after_round, len(view.players))
    return image_pages(
        header.standings(t, view, private=private),
        standings_table(view),
        footer,
        fonts,
        "standings",
        row_entries=True,
        draw=draw,
    )


def pairings_images(
    t: Tournament,
    view: PairingsView,
    fonts: Fonts,
    *,
    private: bool = False,
    draw: Draw | None = None,
) -> tuple[ImagePage, ...]:
    footer = (
        messages.compact_cut_pairings_footer(view.round_number, len(view.pairings))
        if view.cut_round
        else messages.compact_pairings_footer(view.round_number, len(view.pairings))
    )
    return image_pages(
        header.pairings(t, view, private=private),
        pairings_table(t, view),
        footer,
        fonts,
        "pairings",
        row_entries=False,
        draw=draw,
    )


def top_cut_images(
    t: Tournament,
    view: TopCutView,
    fonts: Fonts,
    *,
    private: bool = False,
    draw: Draw | None = None,
) -> tuple[ImagePage, ...]:
    footer = messages.compact_top_cut_footer(view.size, len(view.entries))
    return image_pages(
        header.top_cut(t, view, private=private),
        top_cut_table(view),
        footer,
        fonts,
        "top-cut",
        row_entries=True,
        draw=draw,
    )


def player_images(
    t: Tournament,
    result: NamesResult,
    query: str,
    fonts: Fonts,
    *,
    private: bool = False,
    draw: Draw | None = None,
) -> tuple[ImagePage, ...]:
    """The players found, as rows (`players_table`); the header names the
    query and the notes say which names matched nobody or more."""
    footer = messages.compact_players_footer(len(t.rounds) or None, len(result.matches))
    return image_pages(
        header.players(t, result, query, private=private),
        players_table(t, result.matches),
        footer,
        fonts,
        "players",
        row_entries=True,
        draw=draw,
    )


def paginate_groups(
    groups: Sequence[Group],
    max_rows: int,
    *,
    split: bool,
    max_pages: int | None = None,
) -> list[tuple[Group, ...]]:
    """Pages of at most `max_rows` rows; always at least one page.

    As few pages as full pages need, with the rows spread evenly over them, so
    the images are about the same size and Discord shows their text at the same
    size; the first page is then grown to the next of `CUT_SIZES` (the top 8,
    16 or 32 stay on one image). With more pages than `max_pages` every page is
    full instead: the pages past it are not sent.

    With `split`, a group may continue on the next page (standings: a group is
    the players on equal points). Without it, a group moves whole to the next
    page unless it alone is longer than the page (pairings: a group is a
    table)."""
    full = _fill(groups, max_rows, max_rows, split=split)
    if len(full) == 1 or (max_pages is not None and len(full) > max_pages):
        return full
    total = sum(len(group) for group in groups)
    for limit in range(-(-total // len(full)), max_rows):
        first = min(max_rows, next((n for n in CUT_SIZES if n >= limit), limit))
        pages = _fill(groups, first, limit, split=split)
        if len(pages) <= len(full):
            return pages
    return full


def _fill(
    groups: Sequence[Group], first: int, limit: int, *, split: bool
) -> list[tuple[Group, ...]]:
    """Pages filled in order: at most `first` rows on the first page, `limit`
    on the others."""
    pages: list[list[Group]] = [[]]
    rows = 0
    for group in groups:
        rest = group
        while rest:
            room = (first if len(pages) == 1 else limit) - rows
            if not split and len(rest) > room and pages[-1]:
                room = 0
            if room == 0:
                pages.append([])
                rows = 0
                continue
            piece, rest = rest[:room], rest[room:]
            pages[-1].append(piece)
            rows += len(piece)
    return [tuple(page) for page in pages]


def image_pages(
    head: Header,
    table: Table,
    footer: str,
    fonts: Fonts,
    name: str,
    *,
    row_entries: bool,
    draw: Draw | None = None,
) -> tuple[ImagePage, ...]:
    """One embed and image per page, at most `MAX_PAGES` pages. The first has
    the title, link and header; every one has the legend, and the page number
    when there are several. Pages past the limit are dropped and the last says how
    many entries are missing, with the Cobra link (FR-14). An entry is a row
    with `row_entries` (a player; groups may then break across pages), else a
    group (a table, kept whole). `draw` replaces `render_png` (image cache)."""
    pages = paginate_groups(
        table.groups, MAX_ROWS, split=row_entries, max_pages=MAX_PAGES
    )
    kept = pages[:MAX_PAGES]
    omitted = sum(
        sum(len(g) for g in page) if row_entries else len(page)
        for page in pages[MAX_PAGES:]
    )
    out = []
    for number, groups in enumerate(kept, start=1):
        first, last = number == 1, number == len(kept)
        lines = [*head.lines, *head.notes] if first else []
        if last and omitted:
            lines.append(messages.omitted_entries(omitted, head.url))
        filename = f"{name}-{number}.png"
        embed = Embed(
            description="\n".join(lines),
            title=head.title if first else None,
            url=head.url if first else None,
            footer=(
                f"{footer} · {messages.page_indicator(number, len(kept))}"
                if len(kept) > 1
                else footer
            ),
            color=EMBED_COLOR,
            image=filename,
        )
        page_table = Table(table.columns, groups)
        png = draw(page_table) if draw else render_png(page_table, fonts)
        out.append(ImagePage(embed, filename, png))
    return tuple(out)
