"""Layouts B1 and B2 (Components V2), built from domain objects and fixtures."""

import json
from collections.abc import Callable

import pytest

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
from cobra_bot.formatting.chunking import FENCE_CLOSE, FENCE_OPEN
from cobra_bot.formatting.document import EMBED_COLOR, Document, Entry
from cobra_bot.formatting.standings import format_standings
from cobra_bot.preview import components as c
from cobra_bot.preview.components import Nav

type LoadRaw = Callable[[str], object]
type Payload = dict[str, object]

DISCORD_TEXT_LIMIT = 4000


def _fixture(raw_fixture: LoadRaw, name: str) -> Tournament:
    return parse_tournament(raw_fixture(name), tournament_id=7, fetched_at=FETCHED_AT)


def _standings(t: Tournament) -> StandingsView:
    view = standings_view(t)
    assert isinstance(view, StandingsView)
    return view


def _pairings(t: Tournament, number: int | None = None) -> PairingsView:
    view = pairings_view(t, number)
    assert isinstance(view, PairingsView)
    return view


def _container(payload: Payload) -> list[dict[str, object]]:
    (box,) = payload["components"]  # type: ignore[misc]  # JSON-shaped dict
    assert box["type"] == c.CONTAINER
    blocks: list[dict[str, object]] = box["components"]
    return blocks


def _texts(payload: Payload) -> list[str]:
    return [
        str(b["content"]) for b in _container(payload) if b["type"] == c.TEXT_DISPLAY
    ]


def _rows(payload: Payload) -> list[list[dict[str, object]]]:
    return [
        b["components"]  # type: ignore[misc]
        for b in _container(payload)
        if b["type"] == c.ACTION_ROW
    ]


def _doc(*entries: Entry, footer: str = "legend") -> Document:
    return Document(
        title="Cup",
        url="https://example.test/t/1",
        header=("**State**", "Data from <t:1:R>"),
        entries=entries,
        footer=footer,
    )


# --- message shape ------------------------------------------------------------


def test_page_is_a_components_v2_container_in_the_bot_colour() -> None:
    (page,) = c.b1_pages(_doc(Entry("row")))

    assert page["flags"] == 1 << 15
    assert page["allowed_mentions"] == {"parse": []}
    (box,) = page["components"]  # type: ignore[misc]
    assert box["accent_color"] == EMBED_COLOR
    assert "embeds" not in page


def test_page_text_title_link_header_table_legend() -> None:
    (page,) = c.b1_pages(_doc(Entry("row 1"), Entry("row 2", gap=True)))

    head, table, tail = _texts(page)
    assert head == "### [Cup](https://example.test/t/1)\n**State**\nData from <t:1:R>"
    assert table == f"{FENCE_OPEN}row 1\n\nrow 2{FENCE_CLOSE}"
    assert tail == "-# legend"


def test_title_markdown_is_escaped() -> None:
    doc = Document("*Cup* [2]", "https://x.test", (), (Entry("r"),))

    (page,) = c.b1_pages(doc)

    assert _texts(page)[0] == r"### [\*Cup\* \[2\]](https://x.test)"


def test_no_entries_gives_one_page_without_a_table() -> None:
    (page,) = c.b1_pages(_doc())

    assert len(_texts(page)) == 2  # header and legend


def test_notes_come_before_the_legend() -> None:
    doc = Document("Cup", "https://x.test", (), (), notes=("No players match.",))

    (page,) = c.b1_pages(doc, c.NO_ROUNDS)

    assert _texts(page)[-1] == "No players match."


# --- navigation -------------------------------------------------------------------


def _buttons(page: Payload) -> list[dict[str, object]]:
    return _rows(page)[0]


def test_single_page_disables_prev_and_next() -> None:
    (page,) = c.b1_pages(_doc(Entry("r")))

    prev, indicator, nxt, refresh = _buttons(page)
    assert (prev["label"], prev["disabled"]) == (messages.PREVIOUS_PAGE, True)
    assert (indicator["label"], indicator["disabled"]) == ("1 / 1", True)
    assert (nxt["label"], nxt["disabled"]) == (messages.NEXT_PAGE, True)
    assert (refresh["label"], refresh["disabled"]) == (messages.REFRESH, False)


@pytest.mark.parametrize(
    ("page", "prev_disabled", "next_disabled"),
    [(1, True, False), (2, False, False), (3, False, True)],
)
def test_prev_and_next_disabled_only_at_the_ends(
    page: int, prev_disabled: bool, next_disabled: bool
) -> None:
    (row,) = c.nav_rows(page, 3, c.NO_ROUNDS)
    prev, indicator, nxt, _ = row["components"]  # type: ignore[misc]

    assert prev["disabled"] is prev_disabled
    assert nxt["disabled"] is next_disabled
    assert indicator["label"] == f"{page} / 3"


def test_buttons_are_secondary_with_unique_custom_ids() -> None:
    rows = c.nav_rows(1, 2, Nav((1, 2), 2))
    ids = [
        item["custom_id"]
        for row in rows
        for item in row["components"]  # type: ignore[attr-defined]
    ]

    assert len(ids) == len(set(ids)) == 5
    assert all(
        b["style"] == c.SECONDARY_BUTTON
        for b in rows[0]["components"]  # type: ignore[attr-defined]
    )


def test_no_rounds_means_no_select() -> None:
    assert len(c.nav_rows(1, 1, c.NO_ROUNDS)) == 1


def test_round_select_marks_the_current_round() -> None:
    _, row = c.nav_rows(1, 1, Nav((1, 2, 3), 2))
    (select,) = row["components"]  # type: ignore[misc]

    assert select["type"] == c.STRING_SELECT
    assert select["placeholder"] == messages.ROUND_PLACEHOLDER
    assert [(o["label"], o["value"], o["default"]) for o in select["options"]] == [
        ("Round 1", "1", False),
        ("Round 2", "2", True),
        ("Round 3", "3", False),
    ]


@pytest.mark.parametrize(("rounds", "first"), [(25, 1), (26, 2)])
def test_round_select_keeps_the_last_25_rounds(rounds: int, first: int) -> None:
    _, row = c.nav_rows(1, 1, Nav(tuple(range(1, rounds + 1)), rounds))
    (select,) = row["components"]  # type: ignore[misc]

    values = [o["value"] for o in select["options"]]
    assert len(values) == 25
    assert values[0] == str(first)


# --- pages ------------------------------------------------------------------------


def test_paginate_fills_a_page_up_to_the_budget() -> None:
    entries = [Entry("a" * 9), Entry("b" * 9)]  # 10 each with the separator

    assert c.paginate(entries, 20) == [tuple(entries)]
    assert c.paginate(entries, 19) == [(entries[0],), (entries[1],)]


def test_paginate_counts_the_blank_line_of_a_gap() -> None:
    entries = [Entry("a" * 9), Entry("b" * 9, gap=True)]  # 10 + 11

    assert len(c.paginate(entries, 21)) == 1
    assert len(c.paginate(entries, 20)) == 2


def test_paginate_puts_an_oversized_entry_on_its_own_page() -> None:
    entries = [Entry("a"), Entry("b" * 50), Entry("c")]

    assert c.paginate(entries, 10) == [(entries[0],), (entries[1],), (entries[2],)]


def test_paginate_empty_is_one_empty_page() -> None:
    assert c.paginate([], 10) == [()]


def test_join_entries_gap_is_ignored_at_the_top_of_a_page() -> None:
    assert c.join_entries([Entry("a", gap=True), Entry("b"), Entry("c", gap=True)]) == (
        "a\nb\n\nc"
    )


def test_b1_pages_keep_every_entry_in_order(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "large_top_cut")
    doc = format_standings(t, _standings(t))

    pages = c.b1_pages(doc)

    assert len(pages) > 1
    tables = [_texts(p)[1] for p in pages]
    assert all(x.startswith(FENCE_OPEN) and x.endswith(FENCE_CLOSE) for x in tables)
    shown = "\n\n".join(x[len(FENCE_OPEN) : -len(FENCE_CLOSE)] for x in tables)
    assert [line for line in shown.split("\n") if line] == [
        line for e in doc.entries for line in e.text.split("\n")
    ]
    assert [_buttons(p)[1]["label"] for p in pages] == [
        f"{n} / {len(pages)}" for n in range(1, len(pages) + 1)
    ]


@pytest.mark.parametrize("layout", ["b1", "b2"])
def test_every_page_stays_within_discords_text_limit(
    raw_fixture: LoadRaw, layout: str
) -> None:
    t = _fixture(raw_fixture, "large_top_cut")
    view = _standings(t)
    pages = (
        c.b1_pages(format_standings(t, view))
        if layout == "b1"
        else c.b2_standings(t, view)
    )

    assert all(c.text_length(p) <= DISCORD_TEXT_LIMIT for p in pages)


def test_text_length_counts_contents_labels_and_placeholders() -> None:
    payload = c.container(
        [
            c.text("abc"),
            *c.nav_rows(1, 1, Nav((1,), 1)),
        ]
    )
    labels = len("Prev1 / 1NextRefresh") + len("Choose a round") + len("Round 1")

    assert c.text_length(payload) == 3 + labels


# --- B2 standings -------------------------------------------------------------------


def test_standings_line_bold_name_and_points_grey_ids_and_sos() -> None:
    p = player(
        1,
        "Alice",
        rank=1,
        points=22,
        sos="1.8214",
        corp="Nuvem SA: Law of the Land",
        runner="Arissana Rocha Nahu: Street Artist",
    )

    assert c.standings_line(p) == (
        "1\\. **Alice** — **22**\n-# Nuvem · Arissana · SoS 1.821"
    )


def test_standings_line_escapes_markdown_in_names() -> None:
    p = player(1, "*bold_name~", rank=30)

    first_line = c.standings_line(p).split("\n")[0]
    assert first_line == r"30\. **\*bold\_name\~** — **0**"


def test_standings_line_unknown_ids_show_the_placeholder() -> None:
    p = player(1, "Alice")

    assert c.standings_line(p).endswith("-# — · — · SoS 0.000")


def test_b2_standings_blank_line_between_points_groups() -> None:
    players = (
        player(1, "A", rank=1, points=6),
        player(2, "B", rank=2, points=6),
        player(3, "C", rank=3, points=3),
    )
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=players
    )

    (page,) = c.b2_standings(t, _standings(t))

    table = _texts(page)[1]
    assert "**0**" not in table
    assert table.count("\n\n") == 1
    assert table.index("\n\n") > table.index("**B**")
    assert table.index("\n\n") < table.index("**C**")


def test_b2_standings_legend_and_no_round_select() -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),),
        players=(player(1, rank=1), player(2, rank=2)),
    )

    (page,) = c.b2_standings(t, _standings(t))

    assert _texts(page)[-1] == "-# Round 1 · 2 players"
    assert len(_rows(page)) == 1


# --- B2 pairings --------------------------------------------------------------------

PLAYERS = (
    player(
        1,
        "Alice",
        corp="Nuvem SA: Law of the Land",
        runner="Zahya Sadeghi: Versatile Smuggler",
    ),
    player(
        2,
        "Bob",
        corp="Haas-Bioroid: Precision Design",
        runner="Arissana Rocha Nahu: Street Artist",
    ),
)


def test_single_sided_corp_first() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(4, seat(2, "runner", 0), seat(1, "corp", 3))

    assert c.pairing_line(t, p) == (
        "T4 · **Alice 3** – **0 Bob**\n-# C Nuvem · R Arissana"
    )


def test_single_sided_unreported_shows_dashes() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(1, seat(1, "corp"), seat(2, "runner"))

    assert c.pairing_line(t, p).startswith("T1 · **Alice –** – **– Bob**")


def test_intentional_draw_shows_id() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(1, seat(1, "corp", 1), seat(2, "runner", 1), intentional_draw=True)

    assert c.pairing_line(t, p).startswith("T1 · **Alice ID** – **ID Bob**")


def test_double_sided_totals_then_one_game_per_side() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(2, seat(1, corp=3, runner=0), seat(2, corp=3, runner=0))

    assert c.pairing_line(t, p) == (
        "T2 · **Alice 3** – **3 Bob**\n"
        "-# G1: C Nuvem 3 – 0 R Arissana · G2: R Zahya 0 – 3 C HB"
    )


def test_double_sided_half_reported() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(2, seat(1, corp=3), seat(2, runner=0))

    line, details = c.pairing_line(t, p).split("\n")
    assert line == "T2 · **Alice 3** – **0 Bob**"
    assert "G2: R Zahya – – – C HB" in details


@pytest.mark.parametrize("bye_seat", [1, 2])
def test_bye_in_either_seat(bye_seat: int) -> None:
    t = tournament(players=PLAYERS)
    seats = (seat(1, None, 3), seat(None))
    p = pairing(9, *(seats if bye_seat == 2 else seats[::-1]))

    assert c.pairing_line(t, p) == f"T9 · {messages.BYE} **Alice**"


def test_unknown_player_and_escaped_names() -> None:
    t = tournament(players=(player(1, "_under_"),))
    p = pairing(1, seat(1, "corp", 3), seat(99, "runner", 0))

    assert c.pairing_line(t, p).startswith(
        f"T1 · **\\_under\\_ 3** – **0 {messages.UNKNOWN_PLAYER}**"
    )


def test_b2_pairings_sorted_by_table_with_select_and_legend(
    raw_fixture: LoadRaw,
) -> None:
    t = _fixture(raw_fixture, "dss")
    view = _pairings(t)

    (page,) = c.b2_pairings(t, view, Nav((1, 2, 3), 3))

    table = _texts(page)[1]
    labels = [
        line.split(" · ")[0] for line in table.split("\n") if line.startswith("T")
    ]
    assert labels == [f"T{n}" for n in sorted(p.table for p in view.pairings)]
    assert _texts(page)[-1] == "-# Round 3 · 16 tables · G1 = game 1, G2 = game 2"
    assert len(_rows(page)) == 2


def test_b2_pairings_has_no_code_block(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "dss")

    pages = c.b2_pairings(t, _pairings(t))

    assert "```" not in json.dumps(pages)
    assert "\\u001b" not in json.dumps(pages)
