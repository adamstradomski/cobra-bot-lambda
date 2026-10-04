"""The top-cut bracket as a PNG image in an embed (`/cobra bracket`).

Laid out like Cobra's bracket page: one column per bracket round, the upper
bracket above the lower one, each game a box with its number on the left and
lines from a game to the game its winner plays next in the same bracket. A
game's earlier games centre it. Unlike Cobra: no faction logos, short ID names
(`identities.py`), no pronouns. A slot whose player is not known yet says where
the player comes from (`Seed 3`, `Winner of 13`, `Loser of 21`).

Pure drawing in memory, fonts injected, like `formatting.image`.
"""

import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image, ImageDraw

from cobra_bot import messages
from cobra_bot.domain.bracket import (
    BracketGame,
    BracketSlot,
    BracketView,
    LoserOf,
    Reseeded,
    Seed,
    Source,
    WinnerOf,
)
from cobra_bot.domain.models import Seat, Tournament
from cobra_bot.formatting.chunking import Embed, ImagePage
from cobra_bot.formatting.document import EMBED_COLOR, data_line, heading
from cobra_bot.formatting.image import (
    BACKGROUND,
    CORP,
    RULE,
    RUNNER,
    SECONDARY,
    STRIPE,
    TEXT,
    Font,
    Fonts,
)
from cobra_bot.formatting.text import (
    bracket_url,
    code_text,
    corp_label,
    fit,
    runner_label,
)

# Bump when the drawing changes in a way `bracket_key` does not show.
RENDER_VERSION = 1
NAME_CHARS = 18
FILENAME = "bracket-1.png"

# Pixels, at twice the displayed size like `formatting.image`.
PADDING = 32
SLOT_HEIGHT = 46
BOX_PADDING_X = 18
BOX_PADDING_Y = 6
BOX_HEIGHT = 2 * SLOT_HEIGHT + 2 * BOX_PADDING_Y
NAME_ID_GAP = 28
LABEL_GAP = 12  # between the game number and its box
COLUMN_GAP = 64
ROW_GAP = 24
SECTION_LABEL_HEIGHT = 56
SECTION_GAP = 40
LINE = "#5c5f66"
LINE_WIDTH = 3
RADIUS = 10


@dataclass(frozen=True)
class Text:
    text: str
    color: str = TEXT
    bold: bool = False


@dataclass(frozen=True)
class Box:
    game: int
    column: int  # 0-based: the bracket round - 1
    y: int  # top, within its section
    slots: tuple[tuple[Text, Text], tuple[Text, Text]]  # (name, ID) per slot


@dataclass(frozen=True)
class Section:
    label: str | None  # "Upper bracket" / "Lower bracket"; None in single elim
    boxes: tuple[Box, ...]
    links: tuple[tuple[int, int], ...]  # (game, the game its winner plays next)
    height: int


@dataclass(frozen=True)
class Layout:
    columns: int
    sections: tuple[Section, ...]


def bracket_layout(t: Tournament, view: BracketView) -> Layout:
    double = view.template.double
    sections = []
    for upper in (True, False) if double else (True,):
        games = [g for g in view.games if g.spec.upper == upper]
        if not games:
            continue
        label = (
            (messages.UPPER_BRACKET if upper else messages.LOWER_BRACKET)
            if double
            else None
        )
        sections.append(_section(t, games, label))
    return Layout(columns=view.rounds, sections=tuple(sections))


def _section(t: Tournament, games: list[BracketGame], label: str | None) -> Section:
    """Games in their round's column; the first column evenly spaced, a later
    game centred between the games whose winners it takes (Cobra's layout)."""
    numbers = {g.spec.number for g in games}
    first_round = min(g.spec.round for g in games)
    middle: dict[int, int] = {}  # game -> its box's vertical middle
    boxes = []
    for rnd in sorted({g.spec.round for g in games}):
        column = [g for g in games if g.spec.round == rnd]
        for index, game in enumerate(column):
            feeders = [
                middle[g.spec.number]
                for g in games
                if g.spec.winner_game == game.spec.number and g.spec.number in middle
            ]
            if rnd != first_round and feeders:
                top = (min(feeders) + max(feeders)) // 2 - BOX_HEIGHT // 2
            else:
                top = index * (BOX_HEIGHT + ROW_GAP)
            middle[game.spec.number] = top + BOX_HEIGHT // 2
            boxes.append(
                Box(
                    game=game.spec.number,
                    column=rnd - 1,
                    y=top,
                    slots=(_slot(t, game, game.slot1), _slot(t, game, game.slot2)),
                )
            )
    links = tuple(
        (g.spec.number, g.spec.winner_game)
        for g in games
        if g.spec.winner_game in numbers
    )
    height = max(b.y for b in boxes) + BOX_HEIGHT
    return Section(label, tuple(boxes), links, height)


def _slot(t: Tournament, game: BracketGame, slot: BracketSlot) -> tuple[Text, Text]:
    """The player's name and the short ID of the side they play; the winner
    bold, the loser secondary. Unknown: where the player comes from."""
    if slot.player_id is None:
        return Text(_placeholder(slot.source), SECONDARY), Text("")
    player = t.player(slot.player_id)
    name = fit(code_text(player.name), NAME_CHARS) if player else None
    shown = name or messages.UNKNOWN_PLAYER
    pairing = game.pairing
    if pairing is None:
        return Text(shown), Text("")
    seat = pairing.seat1 if pairing.seat1.player_id == slot.player_id else pairing.seat2
    decided = any(s.winner for s in (pairing.seat1, pairing.seat2))
    if not decided:
        style = Text(shown)
    elif seat.winner:
        style = Text(shown, TEXT, bold=True)
    else:
        style = Text(shown, SECONDARY)
    return style, _side(
        seat,
        player.corp_identity if player else None,
        player.runner_identity if player else None,
    )


def _side(seat: Seat, corp_identity: str | None, runner_identity: str | None) -> Text:
    if seat.role == "corp":
        label = corp_label(corp_identity)
        color = CORP
    elif seat.role == "runner":
        label = runner_label(runner_identity)
        color = RUNNER
    else:
        return Text("")
    if label == messages.UNKNOWN_IDENTITY:
        return Text(label, SECONDARY)
    return Text(label, color)


def _placeholder(source: Source) -> str:
    match source:
        case Seed(position=position):
            return messages.seed_slot(position)
        case WinnerOf(game=game):
            return messages.winner_of(game)
        case LoserOf(game=game):
            return messages.loser_of(game)
        case Reseeded():
            return messages.TBD


# --- drawing ----------------------------------------------------------------------


def render_png(layout: Layout, fonts: Fonts) -> bytes:
    slots = [slot for s in layout.sections for b in s.boxes for slot in b.slots]
    name_width = max(_width(fonts, name) for name, _ in slots)
    id_width = max(_width(fonts, identity) for _, identity in slots)
    label_width = max(
        _width(fonts, Text(str(b.game))) for s in layout.sections for b in s.boxes
    )
    box_width = 2 * BOX_PADDING_X + name_width + NAME_ID_GAP + id_width
    pitch = label_width + LABEL_GAP + box_width + COLUMN_GAP
    width = 2 * PADDING + layout.columns * pitch - COLUMN_GAP
    labels = SECTION_LABEL_HEIGHT if any(s.label for s in layout.sections) else 0
    height = (
        2 * PADDING
        + sum(labels + s.height for s in layout.sections)
        + SECTION_GAP * (len(layout.sections) - 1)
    )
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    top = PADDING
    for section in layout.sections:
        if section.label:
            draw.text(
                (PADDING, top + SECTION_LABEL_HEIGHT // 2),
                section.label,
                fill=SECONDARY,
                font=fonts.bold,
                anchor="lm",
            )
            top += labels
        where = {b.game: b for b in section.boxes}

        def column_x(column: int) -> int:
            return PADDING + column * pitch

        def box_x(box: Box) -> int:
            return column_x(box.column) + label_width + LABEL_GAP

        for game, target in section.links:
            a, b = where[game], where[target]
            x1, y1 = box_x(a) + box_width, top + a.y + BOX_HEIGHT // 2
            x2, y2 = column_x(b.column), top + b.y + BOX_HEIGHT // 2
            mx = (x1 + x2) // 2
            draw.line(
                [(x1, y1), (mx, y1), (mx, y2), (x2, y2)],
                fill=LINE,
                width=LINE_WIDTH,
                joint="curve",
            )
        for box in section.boxes:
            x, y = box_x(box), top + box.y
            draw.text(
                (column_x(box.column), y + BOX_HEIGHT // 2),
                str(box.game),
                fill=SECONDARY,
                font=fonts.regular,
                anchor="lm",
            )
            draw.rounded_rectangle(
                [(x, y), (x + box_width, y + BOX_HEIGHT)],
                radius=RADIUS,
                fill=STRIPE,
                outline=RULE,
                width=2,
            )
            for index, (name, identity) in enumerate(box.slots):
                middle = y + BOX_PADDING_Y + index * SLOT_HEIGHT + SLOT_HEIGHT // 2
                _text(draw, fonts, (x + BOX_PADDING_X, middle), name, "lm")
                _text(
                    draw, fonts, (x + box_width - BOX_PADDING_X, middle), identity, "rm"
                )
        top += section.height + SECTION_GAP
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _font(fonts: Fonts, text: Text) -> Font:
    return fonts.bold if text.bold else fonts.regular


def _width(fonts: Fonts, text: Text) -> int:
    return int(_font(fonts, text).getlength(text.text)) + 1 if text.text else 0


def _text(
    draw: ImageDraw.ImageDraw,
    fonts: Fonts,
    at: tuple[int, int],
    text: Text,
    anchor: str,
) -> None:
    if text.text:
        draw.text(
            at, text.text, fill=text.color, font=_font(fonts, text), anchor=anchor
        )


def bracket_key(layout: Layout, fonts: Fonts) -> str:
    """SHA-256 of everything the image shows, fonts included, for the image cache."""
    payload = {
        "version": RENDER_VERSION,
        "fonts": fonts.digest,
        "kind": "bracket",
        "columns": layout.columns,
        "sections": [
            [
                s.label,
                [
                    [
                        b.game,
                        b.column,
                        b.y,
                        [[[x.text, x.color, x.bold] for x in slot] for slot in b.slots],
                    ]
                    for b in s.boxes
                ],
                list(s.links),
            ]
            for s in layout.sections
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


# --- message ----------------------------------------------------------------------


# The image cache: (key, draw) -> PNG (`ImageCache.png`).
type Cached = Callable[[str, Callable[[], bytes]], bytes]


def bracket_images(
    t: Tournament,
    view: BracketView,
    fonts: Fonts,
    *,
    private: bool = False,
    png: Cached | None = None,
) -> tuple[ImagePage, ...]:
    """One embed with the bracket image. `png(key, draw)` reuses a drawn image
    (the image cache); without it the image is drawn."""
    layout = bracket_layout(t, view)

    def draw() -> bytes:
        return render_png(layout, fonts)

    body = png(bracket_key(layout, fonts), draw) if png else draw()
    games = sum(len(s.boxes) for s in layout.sections)
    embed = Embed(
        description="\n".join(
            [
                heading(
                    messages.bracket_header(
                        view.template.size, view.template.double, view.status
                    )
                ),
                data_line(t, private=private),
            ]
        ),
        title=t.name,
        url=bracket_url(t.id),
        footer=messages.compact_bracket_footer(games),
        color=EMBED_COLOR,
        image=FILENAME,
    )
    return (ImagePage(embed, FILENAME, body),)
