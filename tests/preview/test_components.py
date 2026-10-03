"""Layout B2 (Components V2, plain markdown), built from domain objects and
fixtures."""

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
from cobra_bot.formatting.document import EMBED_COLOR, Entry
from cobra_bot.preview import components as c
from cobra_bot.preview.components import Nav

type LoadRaw = Callable[[str], object]
type Payload = dict[str, object]

DISCORD_TEXT_LIMIT = 4000
DISCORD_COMPONENT_LIMIT = 40
PAD = "\u00a0"
CORP = messages.CORP_MARK
RUNNER = messages.RUNNER_MARK


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


def _one_round(*players: object) -> Tournament:
    return tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),),
        players=players,  # type: ignore[arg-type]
    )


# --- message shape ------------------------------------------------------------------


def test_page_is_a_components_v2_container_in_the_bot_colour() -> None:
    t = _one_round(player(1, rank=1, points=3), player(2, rank=2))

    (page,) = c.b2_standings(t, _standings(t))

    assert page["flags"] == 1 << 15
    assert page["allowed_mentions"] == {"parse": []}
    (box,) = page["components"]  # type: ignore[misc]
    assert box["accent_color"] == EMBED_COLOR
    assert "embeds" not in page


def test_page_head_title_link_and_header() -> None:
    t = _one_round(player(1, rank=1, points=3), player(2, rank=2))

    (page,) = c.b2_standings(t, _standings(t))

    assert _texts(page)[0] == (
        "### [Test Cup](https://tournaments.nullsignal.games/tournaments/1/players/"
        "standings)\n**Standings after round 1**\nData from <t:1790856000:R>"
    )


def test_title_markdown_is_escaped() -> None:
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(None)),),
        players=(player(1),),
        name="*Cup* [2]",
    )

    (page,) = c.b2_standings(t, _standings(t))

    assert _texts(page)[0].startswith(r"### [\*Cup\* \[2\]](https://")


def test_legend_names_the_side_markers() -> None:
    t = _one_round(player(1, rank=1, points=3), player(2, rank=2))

    (page,) = c.b2_standings(t, _standings(t))

    assert _texts(page)[-1] == f"-# {CORP} Corp · {RUNNER} Runner · Round 1 · 2 players"


def test_no_code_blocks_or_ansi(raw_fixture: LoadRaw) -> None:
    """Desktop and mobile render the same: mobile drops ANSI colours."""
    t = _fixture(raw_fixture, "dss")

    pages = [*c.b2_pairings(t, _pairings(t)), *c.b2_standings(t, _standings(t))]

    assert "`" * 3 not in json.dumps(pages)
    assert "\\u001b" not in json.dumps(pages)


# --- cells --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "width", "right", "expected"),
    [
        ("1", 3, True, f"`{PAD}{PAD}1`"),
        ("100", 3, True, "`100`"),
        ("T1", 3, False, f"`T1{PAD}`"),
        ("", 2, False, f"`{PAD}{PAD}`"),
        ("T100", 3, False, "`T100`"),  # never cut
    ],
)
def test_cell_pads_with_no_break_spaces(
    value: str, width: int, right: bool, expected: str
) -> None:
    assert c.cell(value, width, right=right) == expected


# --- standings ----------------------------------------------------------------------


def test_standings_lines_ids_before_points_and_sos() -> None:
    p = player(
        1,
        "Alice",
        rank=1,
        points=22,
        sos="1.8214",
        corp="Nuvem SA: Law of the Land",
        runner="Arissana Rocha Nahu: Street Artist",
    )

    assert c.standings_lines(p) == (
        f"`1` **Alice**\n-# {CORP} Nuvem · {RUNNER} Arissana · **22 pts** · SoS 1.821"
    )


def test_standings_rank_padded_to_the_widest_rank() -> None:
    assert c.standings_lines(player(1, rank=7), 3).startswith(f"`{PAD}{PAD}7` ")


def test_standings_lines_escape_markdown_in_names() -> None:
    first_line = c.standings_lines(player(1, "*bold_name~", rank=30), 2).split("\n")[0]

    assert first_line == r"`30` **\*bold\_name\~**"


def test_standings_unknown_ids_show_the_placeholder() -> None:
    details = c.standings_lines(player(1, "Alice")).split("\n")[1]

    assert details == f"-# {CORP} — · {RUNNER} — · **0 pts** · SoS 0.000"


def test_standings_divider_between_points_groups() -> None:
    players = (
        player(1, "A", rank=1, points=6),
        player(2, "B", rank=2, points=6),
        player(3, "C", rank=3, points=3),
    )
    t = _one_round(*players)

    (page,) = c.b2_standings(t, _standings(t))

    blocks = _container(page)
    kinds = [b["type"] for b in blocks]
    # head, group 6, divider, group 3, legend, divider, nav row
    assert kinds[:6] == [
        c.TEXT_DISPLAY,
        c.TEXT_DISPLAY,
        c.SEPARATOR,
        c.TEXT_DISPLAY,
        c.TEXT_DISPLAY,
        c.SEPARATOR,
    ]
    assert "**A**" in str(blocks[1]["content"])
    assert "**B**" in str(blocks[1]["content"])
    assert "**C**" in str(blocks[3]["content"])


def test_standings_have_no_round_select() -> None:
    t = _one_round(player(1, rank=1, points=3), player(2, rank=2))

    (page,) = c.b2_standings(t, _standings(t))

    assert len(_rows(page)) == 1


# --- pairings -----------------------------------------------------------------------

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
BLANK = f"`{PAD}{PAD}`"


def test_single_sided_corp_first_winner_bold() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(4, seat(2, "runner", 0), seat(1, "corp", 3))

    assert c.pairing_lines(t, p) == (
        f"`T4` **Alice** · {CORP} Nuvem · **3**\n{BLANK} Bob · {RUNNER} Arissana · 0"
    )


def test_single_sided_unreported_leaves_both_plain() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(1, seat(1, "corp"), seat(2, "runner"))

    assert c.pairing_lines(t, p) == (
        f"`T1` Alice · {CORP} Nuvem · –\n{BLANK} Bob · {RUNNER} Arissana · –"
    )


def test_intentional_draw_shows_id_and_no_winner() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(1, seat(1, "corp", 1), seat(2, "runner", 1), intentional_draw=True)

    lines = c.pairing_lines(t, p).split("\n")
    assert [line.rsplit(" · ", 1)[1] for line in lines] == ["ID", "ID"]
    assert "**" not in "".join(lines)


def test_double_sided_total_then_both_games() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(2, seat(1, corp=3, runner=3), seat(2, corp=0, runner=0))

    assert c.pairing_lines(t, p) == (
        f"`T2` **Alice** · **6**\n"
        f"-# G1 {CORP} Nuvem 3 · G2 {RUNNER} Zahya 3\n"
        f"{BLANK} Bob · 0\n"
        f"-# G1 {RUNNER} Arissana 0 · G2 {CORP} HB 0"
    )


def test_double_sided_half_reported() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(2, seat(1, corp=3), seat(2, runner=0))

    lines = c.pairing_lines(t, p).split("\n")
    assert lines[0] == "`T2` **Alice** · **3**"
    assert lines[1] == f"-# G1 {CORP} Nuvem 3 · G2 {RUNNER} Zahya –"


@pytest.mark.parametrize("bye_seat", [1, 2])
def test_bye_in_either_seat(bye_seat: int) -> None:
    t = tournament(players=PLAYERS)
    seats = (seat(1, None, 3), seat(None))
    p = pairing(9, *(seats if bye_seat == 2 else seats[::-1]))

    assert c.pairing_lines(t, p) == f"`T9` Alice · {messages.BYE}"


def test_table_label_padded_to_the_widest_table() -> None:
    t = tournament(players=PLAYERS)
    p = pairing(9, seat(1, None, 3), seat(None))

    assert c.pairing_lines(t, p, 3).startswith(f"`T9{PAD}` ")


def test_unknown_player_and_escaped_names() -> None:
    t = tournament(players=(player(1, "_under_"),))
    p = pairing(1, seat(1, "corp", 3), seat(99, "runner", 0))

    first, second = c.pairing_lines(t, p).split("\n")
    assert first.startswith(r"`T1` **\_under\_** · ")
    assert second.startswith(f"{BLANK} {messages.UNKNOWN_PLAYER} · ")


def test_pairings_one_block_per_table_in_table_order(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "dss")
    view = _pairings(t, 2)

    (page,) = c.b2_pairings(t, view, Nav((1, 2, 3), 2))

    tables = _texts(page)[1:-1]
    assert [x.split("`")[1].rstrip(PAD) for x in tables] == [
        f"T{n}" for n in sorted(p.table for p in view.pairings)
    ]
    assert c.SEPARATOR not in [b["type"] for b in _container(page)][:-3]
    assert _texts(page)[-1].endswith("Round 2 · 16 tables")
    assert len(_rows(page)) == 2


# --- navigation ---------------------------------------------------------------------


def test_single_page_disables_prev_and_next() -> None:
    (row,) = c.nav_rows(1, 1, c.NO_ROUNDS)
    prev, indicator, nxt, refresh = row["components"]  # type: ignore[misc]

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


def test_controls_have_unique_custom_ids() -> None:
    rows = c.nav_rows(1, 2, Nav((1, 2), 2))
    ids = [
        item["custom_id"]
        for row in rows
        for item in row["components"]  # type: ignore[attr-defined]
    ]

    assert len(ids) == len(set(ids)) == 5


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


# --- pages --------------------------------------------------------------------------


def test_paginate_fills_a_page_up_to_the_character_budget() -> None:
    entries = [Entry("a" * 9), Entry("b" * 9)]  # 10 each with the line break

    assert c.paginate(entries, 20, 99) == [tuple(entries)]
    assert c.paginate(entries, 19, 99) == [(entries[0],), (entries[1],)]


@pytest.mark.parametrize(("budget", "pages"), [(4, 1), (3, 2)])
def test_paginate_counts_a_component_per_block(budget: int, pages: int) -> None:
    """Four blocks of one component each; the first entry always starts one."""
    entries = [Entry("a"), Entry("b", gap=True), Entry("c", gap=True), Entry("d", True)]

    assert len(c.paginate(entries, 99, budget)) == pages


def test_paginate_block_cost_counts_the_divider() -> None:
    entries = [Entry("a"), Entry("b", gap=True)]

    assert len(c.paginate(entries, 99, 4, block_cost=2)) == 1
    assert len(c.paginate(entries, 99, 3, block_cost=2)) == 2


def test_paginate_entries_without_gap_share_a_block() -> None:
    entries = [Entry("a"), Entry("b"), Entry("c")]

    assert len(c.paginate(entries, 99, 1)) == 1


def test_paginate_puts_an_oversized_entry_on_its_own_page() -> None:
    entries = [Entry("a"), Entry("b" * 50), Entry("c")]

    assert c.paginate(entries, 10, 99) == [(entries[0],), (entries[1],), (entries[2],)]


def test_paginate_empty_is_one_empty_page() -> None:
    assert c.paginate([], 10, 10) == [()]


def test_split_blocks_starts_a_block_at_each_gap() -> None:
    entries = [Entry("a", gap=True), Entry("b"), Entry("c", gap=True)]

    assert c.split_blocks(entries) == ["a\nb", "c"]


def test_pages_keep_every_player_in_order(raw_fixture: LoadRaw) -> None:
    t = _fixture(raw_fixture, "large_top_cut")
    view = _standings(t)

    pages = c.b2_standings(t, view)

    assert len(pages) > 1
    shown = "\n".join(x for p in pages for x in _texts(p)[1:-1])
    names = [line.split("**")[1] for line in shown.split("\n") if line.startswith("`")]
    assert len(names) == len(view.players)
    assert [_rows(p)[0][1]["label"] for p in pages] == [
        f"{n} / {len(pages)}" for n in range(1, len(pages) + 1)
    ]


@pytest.mark.parametrize("command", ["standings", "pairings"])
@pytest.mark.parametrize("fixture", ["large_top_cut", "single_sided_top8", "dss"])
def test_every_page_stays_within_discords_limits(
    raw_fixture: LoadRaw, command: str, fixture: str
) -> None:
    t = _fixture(raw_fixture, fixture)
    if command == "standings":
        pages = c.b2_standings(t, _standings(t))
    else:
        view = _pairings(t, 1)
        pages = c.b2_pairings(t, view, Nav(tuple(range(1, 26)), 1))

    assert all(c.text_length(p) <= DISCORD_TEXT_LIMIT for p in pages)
    assert all(c.component_count(p) <= DISCORD_COMPONENT_LIMIT for p in pages)


def test_many_tables_are_split_by_the_component_limit() -> None:
    """Each table is one component: 40 short tables cannot share a page."""
    players = tuple(player(n) for n in range(1, 81))
    rnd = tuple(
        pairing(n, seat(2 * n - 1, "corp"), seat(2 * n, "runner")) for n in range(1, 41)
    )
    t = tournament(rnd, players=players)

    pages = c.b2_pairings(t, _pairings(t, 1), Nav((1,), 1))

    assert len(pages) == 2
    assert all(c.component_count(p) <= DISCORD_COMPONENT_LIMIT for p in pages)


def test_component_count_includes_nested_components() -> None:
    payload = c.container([c.text("x"), *c.nav_rows(1, 1, Nav((1,), 1))])

    # container, text, button row + 4 buttons, select row + select
    assert c.component_count(payload) == 1 + 1 + 5 + 2


def test_text_length_counts_contents_labels_and_placeholders() -> None:
    payload = c.container([c.text("abc"), *c.nav_rows(1, 1, Nav((1,), 1))])
    labels = len("Prev1 / 1NextRefresh") + len("Choose a round") + len("Round 1")

    assert c.text_length(payload) == 3 + labels
