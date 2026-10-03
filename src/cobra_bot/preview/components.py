"""Layout B2: replies as Discord Components V2 messages in plain markdown.

Built to look like format C's image and the same on desktop and mobile, so it
uses nothing a client renders differently: no code blocks (mobile drops ANSI
colours) and no tables (markdown has none). In their place:

- side markers stand in for the image's colours: 🔵 Corp, 🟣 Runner;
- rank and table numbers sit in inline code padded to one width, like a column;
- in standings, a divider between groups of players on the same points stands
  in for the image's stripes;
- the order follows the image's columns: player, IDs, points, SoS.

Standings, two lines per player:

    `  1` **Alice**
    -# 🔵 Nuvem · 🟣 Arissana · **22 pts** · SoS 1.821

Pairings, one line per player, the Corp first; the winner in bold:

    `T1 ` **Alice** · 🔵 Nuvem · **3**
    `   ` Bob · 🟣 Zahya · 0

Double-sided, the round total on the player's line and both games under it:

    `T1 ` **Alice** · **3**
    -# G1 🔵 Nuvem 3 · G2 🟣 Arissana 0

Each page is one message: a container in the bot colour holding the title link
and header, the table, the legend, then the navigation (Prev, the page number,
Next, Refresh, and a round select for pairings). The bot does not handle the
controls yet; the preview swaps them for link buttons.

A V2 message holds at most 4000 characters of text and 40 components (nested
ones included); pages respect both.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from cobra_bot import messages
from cobra_bot.domain.models import Pairing, Player, Seat, Tournament
from cobra_bot.domain.rounds import PairingsView, StandingsView
from cobra_bot.formatting.document import EMBED_COLOR, Document, Entry, subtext
from cobra_bot.formatting.pairings import format_pairings
from cobra_bot.formatting.standings import format_standings
from cobra_bot.formatting.text import corp_label, escape_markdown, runner_label

IS_COMPONENTS_V2 = 1 << 15  # message flag 32768
TEXT_LIMIT = 3600  # of Discord's 4000, leaving room for labels and options
COMPONENT_LIMIT = 40
MAX_SELECT_OPTIONS = 25
# Pads inline-code cells: a no-break space is not trimmed as whitespace and is
# one column wide in the code font.
CELL_PAD = "\u00a0"

# Component types.
ACTION_ROW = 1
BUTTON = 2
STRING_SELECT = 3
TEXT_DISPLAY = 10
SEPARATOR = 14
CONTAINER = 17
SECONDARY_BUTTON = 2  # button style

# Custom IDs the bot would receive when someone uses the controls.
PREV_ID = "cobra:prev"
PAGE_ID = "cobra:page"
NEXT_ID = "cobra:next"
REFRESH_ID = "cobra:refresh"
ROUND_ID = "cobra:round"

type Component = dict[str, object]
type Payload = dict[str, object]


@dataclass(frozen=True)
class Nav:
    """What the round select offers; no rounds means no select."""

    rounds: tuple[int, ...] = ()
    current_round: int | None = None


NO_ROUNDS = Nav()


# --- standings --------------------------------------------------------------------


def b2_standings(
    t: Tournament, view: StandingsView, *, private: bool = False
) -> list[Payload]:
    doc = format_standings(t, view, private=private)
    width = max([1, *(len(str(p.rank)) for p in view.players)])
    entries = []
    previous: Player | None = None
    for p in view.players:
        gap = previous is not None and p.match_points != previous.match_points
        entries.append(Entry(standings_lines(p, width), gap=gap))
        previous = p
    footer = messages.compact_standings_footer(view.after_round, len(view.players))
    return _pages(doc, tuple(entries), footer, NO_ROUNDS, dividers=True)


def standings_lines(p: Player, rank_width: int = 1) -> str:
    """The rank and name, then the IDs, points and SoS in small grey text."""
    details = " · ".join(
        [
            _side(messages.CORP_MARK, _id(corp_label(p.corp_identity))),
            _side(messages.RUNNER_MARK, _id(runner_label(p.runner_identity))),
            f"**{messages.points_label(p.match_points)}**",
            f"{messages.SOS} {p.sos:.3f}",
        ]
    )
    return (
        f"{cell(str(p.rank), rank_width, right=True)} **{escape_markdown(p.name)}**\n"
        + subtext(details)
    )


# --- pairings ---------------------------------------------------------------------


def b2_pairings(
    t: Tournament, view: PairingsView, nav: Nav = NO_ROUNDS, *, private: bool = False
) -> list[Payload]:
    doc = format_pairings(t, view, private=private)
    ordered = sorted(view.pairings, key=lambda p: p.table)
    width = max([2, *(len(f"T{p.table}") for p in ordered)])
    entries = tuple(Entry(pairing_lines(t, p, width), gap=True) for p in ordered)
    footer = messages.compact_pairings_footer(view.round_number, len(ordered))
    return _pages(doc, entries, footer, nav, dividers=False)


def pairing_lines(t: Tournament, pairing: Pairing, label_width: int = 2) -> str:
    label = cell(f"T{pairing.table}", label_width)
    blank = cell("", label_width)
    if pairing.is_bye:
        (player_id,) = pairing.player_ids or (None,)
        return f"{label} {_name(t, player_id)} · {messages.BYE}"
    s1, s2 = pairing.seat1, pairing.seat2
    if pairing.double_sided:
        (total1, won1), (total2, won2) = _results(pairing, _total(s1), _total(s2))
        p1, p2 = _player(t, s1), _player(t, s2)
        return "\n".join(
            [
                f"{label} {_seat(t, s1, won1)} · {_points(total1, won1)}",
                subtext(
                    _games(
                        (messages.CORP_MARK, _corp(p1), s1.corp_score),
                        (messages.RUNNER_MARK, _runner(p1), s1.runner_score),
                    )
                ),
                f"{blank} {_seat(t, s2, won2)} · {_points(total2, won2)}",
                subtext(
                    _games(
                        (messages.RUNNER_MARK, _runner(p2), s2.runner_score),
                        (messages.CORP_MARK, _corp(p2), s2.corp_score),
                    )
                ),
            ]
        )
    # Single-sided games always have roles (findings Q3); the Corp comes first.
    corp, runner = (s1, s2) if s1.role == "corp" else (s2, s1)
    (corp_pts, corp_won), (runner_pts, runner_won) = _results(
        pairing, corp.combined_score, runner.combined_score
    )
    corp_id = _side(messages.CORP_MARK, _corp(_player(t, corp)))
    runner_id = _side(messages.RUNNER_MARK, _runner(_player(t, runner)))
    return "\n".join(
        [
            f"{label} {_seat(t, corp, corp_won)} · {corp_id} · "
            f"{_points(corp_pts, corp_won)}",
            f"{blank} {_seat(t, runner, runner_won)} · {runner_id} · "
            f"{_points(runner_pts, runner_won)}",
        ]
    )


type Game = tuple[str, str, int | None]  # side marker, ID, points


def _games(game1: Game, game2: Game) -> str:
    return " · ".join(
        f"{messages.game_label(n)} {_side(mark, label)} {_shown(points)}"
        for n, (mark, label, points) in enumerate((game1, game2), start=1)
    )


def _results(
    pairing: Pairing, first: int | None, second: int | None
) -> tuple[tuple[str, bool], tuple[str, bool]]:
    """Points as shown and whether that player won (shown in bold)."""
    if pairing.intentional_draw:
        draw = (messages.INTENTIONAL_DRAW, False)
        return draw, draw
    shown = (_shown(first), _shown(second))
    if first is None or second is None or first == second:
        return (shown[0], False), (shown[1], False)
    return (shown[0], first > second), (shown[1], second > first)


def _seat(t: Tournament, seat: Seat, won: bool) -> str:
    name = _name(t, seat.player_id)
    return f"**{name}**" if won else name


def _points(shown: str, won: bool) -> str:
    return f"**{shown}**" if won else shown


def _shown(points: int | None) -> str:
    return messages.NO_RESULT if points is None else str(points)


def _total(seat: Seat) -> int | None:
    if seat.corp_score is None and seat.runner_score is None:
        return None
    return (seat.corp_score or 0) + (seat.runner_score or 0)


def _player(t: Tournament, seat: Seat) -> Player | None:
    return t.player(seat.player_id) if seat.player_id is not None else None


def _name(t: Tournament, player_id: int | None) -> str:
    player = t.player(player_id) if player_id is not None else None
    return escape_markdown(player.name) if player else messages.UNKNOWN_PLAYER


def _side(mark: str, label: str) -> str:
    return f"{mark} {label}"


def _id(label: str) -> str:
    return escape_markdown(label) or messages.UNKNOWN_IDENTITY


def _corp(player: Player | None) -> str:
    return _id(corp_label(player.corp_identity if player else None))


def _runner(player: Player | None) -> str:
    return _id(runner_label(player.runner_identity if player else None))


def cell(text: str, width: int, *, right: bool = False) -> str:
    """`text` in inline code, padded to `width` columns."""
    padding = CELL_PAD * max(0, width - len(text))
    return f"`{padding}{text}`" if right else f"`{text}{padding}`"


# --- pages ------------------------------------------------------------------------


def _pages(
    doc: Document,
    entries: Sequence[Entry],
    footer: str,
    nav: Nav,
    *,
    dividers: bool,
) -> list[Payload]:
    """Entries joined into text blocks: a new block starts at every entry with a
    gap, after a divider when `dividers` is set."""
    head = "\n".join([f"### [{escape_markdown(doc.title)}]({doc.url})", *doc.header])
    tail = "\n".join([*doc.notes, subtext(f"{messages.SIDE_LEGEND} · {footer}")])
    fixed = 1 + 2 + 1 + _nav_size(nav)  # container, head and tail, separator, nav
    groups = paginate(
        entries,
        TEXT_LIMIT - len(head) - len(tail),
        COMPONENT_LIMIT - fixed,
        block_cost=2 if dividers else 1,
    )
    pages = []
    for number, group in enumerate(groups, start=1):
        blocks: list[Component] = [text(head)]
        for index, block in enumerate(split_blocks(group)):
            if dividers and index > 0:
                blocks.append(divider())
            blocks.append(text(block))
        blocks.append(text(tail))
        blocks.append(divider())
        blocks.extend(nav_rows(number, len(groups), nav))
        pages.append(container(blocks))
    return pages


def paginate(
    entries: Sequence[Entry], chars: int, components: int, *, block_cost: int = 1
) -> list[tuple[Entry, ...]]:
    """Split entries into pages of at most `chars` characters and `components`
    components, keeping every entry whole. An entry with a gap (or the first on
    a page) starts a new block costing `block_cost` components. Always at least
    one (possibly empty) page."""
    pages: list[list[Entry]] = [[]]
    used_chars = used_components = 0
    for entry in entries:
        cost = block_cost if entry.gap or not pages[-1] else 0
        size = len(entry.text) + 1  # its line break
        if pages[-1] and (
            used_chars + size > chars or used_components + cost > components
        ):
            pages.append([])
            used_chars = used_components = 0
            cost = block_cost
        pages[-1].append(entry)
        used_chars += size
        used_components += cost
    return [tuple(page) for page in pages]


def split_blocks(entries: Sequence[Entry]) -> list[str]:
    """Entries joined one per line; an entry with a gap starts a new block."""
    blocks: list[list[str]] = []
    for entry in entries:
        if entry.gap or not blocks:
            blocks.append([])
        blocks[-1].append(entry.text)
    return ["\n".join(block) for block in blocks]


def _nav_size(nav: Nav) -> int:
    """Components in the navigation: a row of four buttons, and the select row."""
    return 5 + (2 if nav.rounds else 0)


def nav_rows(page: int, pages: int, nav: Nav) -> list[Component]:
    rows: list[Component] = [
        action_row(
            [
                button(messages.PREVIOUS_PAGE, PREV_ID, disabled=page == 1),
                button(messages.page_indicator(page, pages), PAGE_ID, disabled=True),
                button(messages.NEXT_PAGE, NEXT_ID, disabled=page == pages),
                button(messages.REFRESH, REFRESH_ID),
            ]
        )
    ]
    if nav.rounds:
        options = [
            {
                "label": messages.round_option(n),
                "value": str(n),
                "default": n == nav.current_round,
            }
            for n in nav.rounds[-MAX_SELECT_OPTIONS:]
        ]
        rows.append(
            action_row(
                [
                    {
                        "type": STRING_SELECT,
                        "custom_id": ROUND_ID,
                        "placeholder": messages.ROUND_PLACEHOLDER,
                        "options": options,
                    }
                ]
            )
        )
    return rows


def text(content: str) -> Component:
    return {"type": TEXT_DISPLAY, "content": content}


def divider() -> Component:
    return {"type": SEPARATOR, "divider": True, "spacing": 1}


def button(label: str, custom_id: str, *, disabled: bool = False) -> Component:
    return {
        "type": BUTTON,
        "style": SECONDARY_BUTTON,
        "label": label,
        "custom_id": custom_id,
        "disabled": disabled,
    }


def action_row(components: list[Component]) -> Component:
    return {"type": ACTION_ROW, "components": components}


def container(blocks: list[Component]) -> Payload:
    return {
        "flags": IS_COMPONENTS_V2,
        "allowed_mentions": {"parse": []},
        "components": [
            {"type": CONTAINER, "accent_color": EMBED_COLOR, "components": blocks}
        ],
    }


def text_length(payload: Payload) -> int:
    """Characters Discord counts towards the 4000 limit: text displays, labels,
    placeholders and option labels, anywhere in the message."""
    total = 0
    stack: list[object] = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key in ("content", "label", "placeholder"):
                value = item.get(key)
                if isinstance(value, str):
                    total += len(value)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return total


def component_count(payload: Payload) -> int:
    """Components in the message, nested ones included (limit 40)."""
    count = 0
    stack: list[object] = _list(payload.get("components"))
    while stack:
        item = stack.pop()
        if isinstance(item, dict) and "type" in item:
            count += 1
            stack.extend(_list(item.get("components")))
    return count


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []
