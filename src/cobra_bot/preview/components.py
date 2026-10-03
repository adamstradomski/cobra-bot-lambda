"""Layouts B1 and B2: replies as Discord Components V2 messages.

Each page is one message: a container in the bot colour holding the title link
and header, the table, the notes and legend, then the navigation, i.e. Prev,
the page number, Next and Refresh, and for pairings a round select. The bot
does not handle these buttons yet, and the preview swaps them for link buttons
(`scripts/preview.py`).

- B1: the table is format A's ```ansi code block, split into pages instead of
  embeds.
- B2: no code block and no columns. One line per player or table with the
  names and points in bold, then a small grey line with the IDs (and the SoS
  in standings). Meant for phones, where code blocks lose their colours and
  wrap.

A V2 message holds at most 4000 characters of text across its components;
`TEXT_LIMIT` keeps a margin for the button and select labels.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from cobra_bot import messages
from cobra_bot.domain.models import Pairing, Player, Seat, Tournament
from cobra_bot.domain.rounds import PairingsView, StandingsView
from cobra_bot.formatting.chunking import FENCE_CLOSE, FENCE_OPEN
from cobra_bot.formatting.document import EMBED_COLOR, Document, Entry, subtext
from cobra_bot.formatting.pairings import format_pairings
from cobra_bot.formatting.standings import format_standings
from cobra_bot.formatting.text import corp_label, escape_markdown, runner_label

IS_COMPONENTS_V2 = 1 << 15  # message flag 32768
TEXT_LIMIT = 3600  # of Discord's 4000, leaving room for labels and options
MAX_SELECT_OPTIONS = 25

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


# --- B1 ---------------------------------------------------------------------


def b1_pages(doc: Document, nav: Nav = NO_ROUNDS) -> list[Payload]:
    """Format A's table, page by page; every entry stays whole."""
    return _pages(doc, doc.entries, doc.footer, nav, code_block=True)


# --- B2 ---------------------------------------------------------------------


def b2_standings(
    t: Tournament, view: StandingsView, *, private: bool = False
) -> list[Payload]:
    doc = format_standings(t, view, private=private)
    entries = []
    previous: Player | None = None
    for p in view.players:
        gap = previous is not None and p.match_points != previous.match_points
        entries.append(Entry(standings_line(p), gap=gap))
        previous = p
    footer = messages.compact_standings_footer(view.after_round, len(view.players))
    return _pages(doc, tuple(entries), footer, NO_ROUNDS, code_block=False)


def standings_line(p: Player) -> str:
    """`1\\. **Alice** — **22**`, then `-# Nuvem · Arissana · SoS 1.821`.

    The dot is escaped: `1. ` at the start of a line would become a markdown
    list, which Discord renumbers.
    """
    ids = f"{_id(corp_label(p.corp_identity))} · {_id(runner_label(p.runner_identity))}"
    return (
        f"{p.rank}\\. **{escape_markdown(p.name)}** — **{p.match_points}**\n"
        + subtext(f"{ids} · {messages.SOS} {p.sos:.3f}")
    )


def b2_pairings(
    t: Tournament, view: PairingsView, nav: Nav = NO_ROUNDS, *, private: bool = False
) -> list[Payload]:
    doc = format_pairings(t, view, private=private)
    ordered = sorted(view.pairings, key=lambda p: p.table)
    entries = tuple(Entry(pairing_line(t, p)) for p in ordered)
    footer = messages.compact_pairings_footer(
        view.round_number, len(ordered), any(p.double_sided for p in ordered)
    )
    return _pages(doc, entries, footer, nav, code_block=False)


def pairing_line(t: Tournament, pairing: Pairing) -> str:
    """Single-sided, the Corp first: `T1 · **Alice 3** – **0 Bob**`, then
    `-# C Nuvem · R Zahya`. Double-sided: seat 1 first with the round totals,
    then one game per side, `-# G1: C Nuvem 3 – 0 R Zahya · G2: …`.
    A bye: `T5 · BYE **Carol**`."""
    label = f"T{pairing.table}"
    if pairing.is_bye:
        (player_id,) = pairing.player_ids or (None,)
        return f"{label} · {messages.BYE} **{_name(t, player_id)}**"
    s1, s2 = pairing.seat1, pairing.seat2
    if pairing.double_sided:
        first, second = (s1, _total(s1)), (s2, _total(s2))
        p1, p2 = _player(t, s1), _player(t, s2)
        g1 = _game(
            1, _corp(p1), s1.corp_score, _runner(p2), s2.runner_score, corp_first=True
        )
        g2 = _game(
            2, _runner(p1), s1.runner_score, _corp(p2), s2.corp_score, corp_first=False
        )
        details = f"{g1} · {g2}"
    else:
        corp, runner = (s1, s2) if s1.role == "corp" else (s2, s1)
        first, second = (corp, corp.combined_score), (runner, runner.combined_score)
        details = (
            f"{messages.CORP_TAG} {_corp(_player(t, corp))} · "
            f"{messages.RUNNER_TAG} {_runner(_player(t, runner))}"
        )
    a, b = _scores(pairing, first[1], second[1])
    return (
        f"{label} · **{_name(t, first[0].player_id)} {a}** – "
        f"**{b} {_name(t, second[0].player_id)}**\n" + subtext(details)
    )


def _game(
    game: int,
    first_id: str,
    first_score: int | None,
    second_id: str,
    second_score: int | None,
    *,
    corp_first: bool,
) -> str:
    tags = (
        (messages.CORP_TAG, messages.RUNNER_TAG)
        if corp_first
        else (messages.RUNNER_TAG, messages.CORP_TAG)
    )
    return (
        f"{messages.game_label(game)}: {tags[0]} {first_id} {_shown(first_score)} – "
        f"{_shown(second_score)} {tags[1]} {second_id}"
    )


def _scores(pairing: Pairing, a: int | None, b: int | None) -> tuple[str, str]:
    if pairing.intentional_draw:
        return messages.INTENTIONAL_DRAW, messages.INTENTIONAL_DRAW
    return _shown(a), _shown(b)


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


def _id(label: str) -> str:
    return escape_markdown(label) or messages.UNKNOWN_IDENTITY


def _corp(player: Player | None) -> str:
    return _id(corp_label(player.corp_identity if player else None))


def _runner(player: Player | None) -> str:
    return _id(runner_label(player.runner_identity if player else None))


# --- pages ------------------------------------------------------------------


def _pages(
    doc: Document,
    entries: Sequence[Entry],
    footer: str,
    nav: Nav,
    *,
    code_block: bool,
) -> list[Payload]:
    head = "\n".join([f"### [{escape_markdown(doc.title)}]({doc.url})", *doc.header])
    tail = "\n".join([*doc.notes, *([subtext(footer)] if footer else [])])
    fences = len(FENCE_OPEN) + len(FENCE_CLOSE) if code_block else 0
    budget = TEXT_LIMIT - len(head) - len(tail) - fences
    groups = paginate(entries, budget)
    pages = []
    for number, group in enumerate(groups, start=1):
        blocks: list[Component] = [text(head)]
        if group:
            body = join_entries(group)
            blocks.append(
                text(f"{FENCE_OPEN}{body}{FENCE_CLOSE}" if code_block else body)
            )
        if tail:
            blocks.append(text(tail))
        blocks.append({"type": SEPARATOR, "divider": True, "spacing": 1})
        blocks.extend(nav_rows(number, len(groups), nav))
        pages.append(container(blocks))
    return pages


def paginate(entries: Sequence[Entry], budget: int) -> list[tuple[Entry, ...]]:
    """Split entries into pages of at most `budget` characters, keeping every
    entry whole; always at least one (possibly empty) page."""
    pages: list[list[Entry]] = [[]]
    used = 0
    for entry in entries:
        cost = len(entry.text) + (2 if entry.gap else 1)  # its separator, at most
        if pages[-1] and used + cost > budget:
            pages.append([])
            used = 0
        pages[-1].append(entry)
        used += cost
    return [tuple(page) for page in pages]


def join_entries(entries: Sequence[Entry]) -> str:
    """Entries one per line, a blank line before those with a gap (not before
    the first on the page)."""
    parts = [entries[0].text]
    for entry in entries[1:]:
        parts.append(("\n\n" if entry.gap else "\n") + entry.text)
    return "".join(parts)


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
