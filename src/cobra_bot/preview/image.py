"""Layout C: the table as a PNG image in an embed.

Full colours on every client, real columns with headings, names and IDs not cut
to code-block widths. The text cannot be selected or searched. The embed keeps
format A's title link, header lines and a short legend; a long table is split
into pages of at most `MAX_ROWS` rows, one message each.

Drawn with Pillow (a dev dependency: the bot does not ship it) in a system font
that has Latin Extended glyphs (Pillow's built-in font has none of `Żółw`).
"""

import io
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from cobra_bot import messages
from cobra_bot.discord.api import Attachment
from cobra_bot.domain.models import Pairing, Player, Seat, Tournament
from cobra_bot.domain.rounds import PairingsView, StandingsView
from cobra_bot.formatting.document import EMBED_COLOR, Document
from cobra_bot.formatting.pairings import format_pairings
from cobra_bot.formatting.standings import format_standings
from cobra_bot.formatting.text import code_text, fit, short_identity

MAX_ROWS = 40  # per image
NAME_CHARS = 28
ID_CHARS = 24

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

_WINDOWS_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_DEJAVU = Path("/usr/share/fonts/truetype/dejavu")
_MACOS_FONTS = Path("/System/Library/Fonts/Supplemental")
# (regular, bold) font files to try, in order: Windows, Linux, macOS.
FONT_CANDIDATES: tuple[tuple[Path, Path], ...] = (
    (_WINDOWS_FONTS / "segoeui.ttf", _WINDOWS_FONTS / "segoeuib.ttf"),
    (_DEJAVU / "DejaVuSans.ttf", _DEJAVU / "DejaVuSans-Bold.ttf"),
    (_MACOS_FONTS / "Arial.ttf", _MACOS_FONTS / "Arial Bold.ttf"),
)

type Font = ImageFont.FreeTypeFont | ImageFont.ImageFont
type Align = Literal["left", "right"]


class FontNotFound(Exception):
    """No usable font file; pass one explicitly."""


@dataclass(frozen=True)
class Fonts:
    regular: Font
    bold: Font


def load_fonts(
    path: Path | None = None,
    bold_path: Path | None = None,
    candidates: Sequence[tuple[Path, Path]] = FONT_CANDIDATES,
) -> Fonts:
    """`path` (and `bold_path`, default: `path`), else the first pair in
    `candidates` whose files both exist."""
    if path is not None:
        return Fonts(_truetype(path), _truetype(bold_path or path))
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            return Fonts(_truetype(regular), _truetype(bold))
    raise FontNotFound("no system font found; pass one with --font")


def _truetype(path: Path) -> Font:
    try:
        return ImageFont.truetype(path, FONT_SIZE)
    except OSError as err:
        raise FontNotFound(f"cannot load font {path}") from err


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
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


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
    return Table(
        columns=(
            Column(messages.TABLE),
            Column(messages.PLAYER),
            Column(messages.SIDE),
            Column(messages.IDENTITY),
            Column(messages.POINTS, "right"),
        ),
        groups=tuple(_single_sided(t, p) for p in ordered),
    )


def _single_sided(t: Tournament, pairing: Pairing) -> Group:
    label = f"T{pairing.table}"
    if pairing.is_bye:
        return (_bye_row(t, pairing, columns=5),)
    s1, s2 = pairing.seat1, pairing.seat2
    corp, runner = (s1, s2) if s1.role == "corp" else (s2, s1)
    styles = _styles(pairing, corp.combined_score, runner.combined_score)
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
    """Points as shown and the name style: the winner bold, the loser secondary
    (as in format A)."""
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
    label = short_identity(identity)
    if label == messages.UNKNOWN_IDENTITY:
        return Cell(label, SECONDARY)
    return Cell(fit(code_text(label), ID_CHARS), color)


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


# --- messages ---------------------------------------------------------------

type ImageMessage = tuple[dict[str, object], Attachment]


def c_standings(
    t: Tournament, view: StandingsView, fonts: Fonts, *, private: bool = False
) -> list[ImageMessage]:
    doc = format_standings(t, view, private=private)
    footer = messages.compact_standings_footer(view.after_round, len(view.players))
    return _messages(doc, standings_table(view), footer, fonts, "standings")


def c_pairings(
    t: Tournament, view: PairingsView, fonts: Fonts, *, private: bool = False
) -> list[ImageMessage]:
    doc = format_pairings(t, view, private=private)
    footer = messages.compact_pairings_footer(view.round_number, len(view.pairings))
    return _messages(doc, pairings_table(t, view), footer, fonts, "pairings")


def paginate_groups(groups: Sequence[Group], max_rows: int) -> list[tuple[Group, ...]]:
    """Pages of whole groups, at most `max_rows` rows each (a larger group gets
    a page of its own); always at least one page."""
    pages: list[list[Group]] = [[]]
    rows = 0
    for group in groups:
        if pages[-1] and rows + len(group) > max_rows:
            pages.append([])
            rows = 0
        pages[-1].append(group)
        rows += len(group)
    return [tuple(page) for page in pages]


def _messages(
    doc: Document, table: Table, footer: str, fonts: Fonts, name: str
) -> list[ImageMessage]:
    pages = paginate_groups(table.groups, MAX_ROWS)
    out: list[ImageMessage] = []
    for number, groups in enumerate(pages, start=1):
        filename = f"{name}-{number}.png"
        png = render_png(Table(table.columns, groups), fonts)
        page_footer = (
            f"{footer} · {messages.page_indicator(number, len(pages))}"
            if len(pages) > 1
            else footer
        )
        embed: dict[str, object] = {
            "title": doc.title,
            "url": doc.url,
            "color": EMBED_COLOR,
            "description": "\n".join([*doc.header, *doc.notes]),
            "image": {"url": f"attachment://{filename}"},
            "footer": {"text": page_footer},
        }
        payload: dict[str, object] = {
            "embeds": [embed],
            "allowed_mentions": {"parse": []},
            "attachments": [{"id": 0, "filename": filename}],
        }
        out.append((payload, Attachment(filename, png, "image/png")))
    return out
