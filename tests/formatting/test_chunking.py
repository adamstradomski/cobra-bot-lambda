import re
from collections.abc import Callable

import pytest

from builders import FETCHED_AT, pairing, plain, player, seat, tournament
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.rounds import StandingsView, standings_view
from cobra_bot.formatting.chunking import (
    DISCORD_LIMITS,
    FIELD_NAME,
    Limits,
    Message,
    chunk,
)
from cobra_bot.formatting.document import EMBED_COLOR, Document, Entry
from cobra_bot.formatting.standings import format_standings

type LoadRaw = Callable[[str], object]

URL = "https://tournaments.nullsignal.games/tournaments/1/players/standings"
OMITTED = re.compile(r"…and (\d+) more — \[full list on Cobra\]\((\S+)\)")
CODE_BLOCK = re.compile(r"```ansi\n(.*?)\n```", re.DOTALL)


def _doc(
    entries: list[str],
    *,
    header: tuple[str, ...] = ("Header",),
    columns: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
    footer: str = "",
    gaps: bool = False,
) -> Document:
    return Document(
        title="Title",
        url=URL,
        header=header,
        columns=columns,
        entries=tuple(Entry(e, gap=gaps) for e in entries),
        notes=notes,
        footer=footer,
    )


def _parts(messages: tuple[Message, ...]) -> list[list[str]]:
    """Per message: the description, then the field values."""
    return [[e.description, *e.fields] for m in messages for e in m]


def _blocks(messages: tuple[Message, ...]) -> list[list[str]]:
    """Lines of every code block, in order."""
    return [
        block.split("\n")
        for parts in _parts(messages)
        for part in parts
        for block in CODE_BLOCK.findall(part)
    ]


def _assert_within_limits(messages: tuple[Message, ...], limits: Limits) -> None:
    assert len(messages) <= limits.messages
    for message in messages:
        (embed,) = message
        assert embed.chars <= limits.chars_per_message
        assert 0 < len(embed.description) <= limits.description
        assert len(embed.fields) <= limits.fields
        assert all(0 < len(value) <= limits.field_value for value in embed.fields)
        for part in (embed.description, *embed.fields):
            assert part.count("```") in (0, 2), part  # each part closes its block


def _standings_doc(t: object) -> Document:
    view = standings_view(t)  # type: ignore[arg-type]
    assert isinstance(view, StandingsView)
    return format_standings(t, view)  # type: ignore[arg-type]


# --- acceptance criteria -----------------------------------------------------------


def test_ac14_large_standings_fit_and_keep_rank_order(raw_fixture: LoadRaw) -> None:
    t = parse_tournament(
        raw_fixture("large_top_cut"), tournament_id=4990, fetched_at=FETCHED_AT
    )
    doc = _standings_doc(t)

    messages = chunk(doc)

    _assert_within_limits(messages, DISCORD_LIMITS)
    assert len(messages) > 1
    blocks = _blocks(messages)
    assert all(block[0] != "" for block in blocks)  # no gap atop a block
    rows = [line for block in blocks for line in block if line][2:]  # no columns
    assert rows == [e.text for e in doc.entries]  # all, once, in order
    ranks = [int(plain(row).split()[0]) for row in rows]
    assert ranks == list(range(1, 236))


def test_ac15_thousand_players_are_cut_with_a_link() -> None:
    players = tuple(player(i, rank=i) for i in range(1, 1001))
    t = tournament(
        (pairing(1, seat(1, "corp", 3), seat(2, "runner", 0)),), players=players
    )
    doc = _standings_doc(t)

    messages = chunk(doc)

    assert len(messages) == 5
    _assert_within_limits(messages, DISCORD_LIMITS)
    last = _parts(messages)[-1][-1].split("\n")[-1]
    match = OMITTED.fullmatch(last)
    assert match is not None
    rows = [line for block in _blocks(messages) for line in block][2:]
    assert int(match.group(1)) == 1000 - len(rows)
    assert match.group(2) == URL
    assert rows == [e.text for e in doc.entries[: len(rows)]]


# --- layout -------------------------------------------------------------------------


def test_small_document_is_one_embed_with_title_link_colour_and_footer() -> None:
    messages = chunk(_doc(["a", "b"], columns=("col",), footer="legend"))

    assert len(messages) == 1
    (embed,) = messages[0]
    assert (embed.title, embed.url, embed.color) == ("Title", URL, EMBED_COLOR)
    assert embed.description == "Header\n```ansi\ncol\na\nb\n```"
    assert embed.fields == ()
    assert embed.footer == "legend"


def test_field_name_is_a_zero_width_space() -> None:
    assert chr(0x200B) == FIELD_NAME


def test_no_footer_means_none() -> None:
    (embed,) = chunk(_doc(["a"]))[0]

    assert embed.footer is None


def test_gaps_are_blank_lines_inside_a_block_only() -> None:
    limits = Limits(description=25, chars_per_message=1000)

    messages = chunk(_doc(["aaaa", "bbbb", "cccc"], header=("h",), gaps=True), limits)

    # "h" + block "aaaa", gap, "bbbb" = 24; "cccc" opens a field without a gap.
    assert _blocks(messages) == [["aaaa", "", "bbbb"], ["cccc"]]


def test_columns_head_only_the_first_block() -> None:
    limits = Limits(description=30, chars_per_message=1000)

    messages = chunk(_doc(["aaaa", "bbbb", "cccc"], columns=("col",)), limits)

    blocks = _blocks(messages)
    assert blocks[0][0] == "col"
    assert all("col" not in block for block in blocks[1:])


def test_entries_are_never_split() -> None:
    entries = ["line one\nline two", "line three\nline four"]
    limits = Limits(description=40, chars_per_message=1000)

    messages = chunk(_doc(entries, header=("h",)), limits)

    assert _blocks(messages) == [e.split("\n") for e in entries]


def test_description_limit_moves_the_rest_to_a_field() -> None:
    limits = Limits(description=25, chars_per_message=1000)

    messages = chunk(_doc(["aaaa", "bbbb", "cccc"], header=("h",)), limits)

    # "h\n```ansi\naaaa\nbbbb\n```" is 23 chars; with "\ncccc" it would be 28.
    assert _parts(messages) == [["h\n```ansi\naaaa\nbbbb\n```", "```ansi\ncccc\n```"]]


@pytest.mark.parametrize(
    ("field_value", "fields"),
    [
        (21, ["```ansi\nbbbb\ncccc\n```"]),
        (20, ["```ansi\nbbbb\n```", "```ansi\ncccc\n```"]),
    ],
    ids=["at-limit", "one-below"],
)
def test_field_value_limit_starts_a_new_field(
    field_value: int, fields: list[str]
) -> None:
    limits = Limits(description=20, field_value=field_value, chars_per_message=1000)

    messages = chunk(_doc(["aaaa", "bbbb", "cccc"], header=("h",)), limits)

    assert _parts(messages) == [["h\n```ansi\naaaa\n```", *fields]]


def test_field_count_limit_starts_a_new_message() -> None:
    limits = Limits(description=18, field_value=16, fields=1, chars_per_message=1000)

    messages = chunk(_doc(["aaaa", "bbbb", "cccc"], header=("h",)), limits)

    assert _parts(messages) == [
        ["h\n```ansi\naaaa\n```", "```ansi\nbbbb\n```"],
        ["```ansi\ncccc\n```"],
    ]
    assert [m[0].title for m in messages] == ["Title", None]


@pytest.mark.parametrize(
    ("chars", "parts"),
    [
        # "Title" (5) + footer "F" (1) + "h\n```ansi\naaaa\nbbbb\n```" (23) = 29.
        (29, [["h\n```ansi\naaaa\nbbbb\n```"], ["```ansi\ncccc\n```"]]),
        (28, [["h\n```ansi\naaaa\n```"], ["```ansi\nbbbb\ncccc\n```"]]),
    ],
    ids=["at-limit", "one-below"],
)
def test_message_char_limit_counts_title_and_footer(
    chars: int, parts: list[list[str]]
) -> None:
    limits = Limits(description=100, field_value=10, chars_per_message=chars)

    messages = chunk(_doc(["aaaa", "bbbb", "cccc"], header=("h",), footer="F"), limits)

    assert _parts(messages) == parts
    _assert_within_limits(messages, limits)


@pytest.mark.parametrize(
    ("chars", "fields"),
    [
        # "Title" (5) + description (18) + field name (1) + field (16) = 40.
        (40, 1),
        (39, 0),
    ],
    ids=["at-limit", "one-below"],
)
def test_message_char_limit_counts_field_names(chars: int, fields: int) -> None:
    limits = Limits(description=18, chars_per_message=chars)

    messages = chunk(_doc(["aaaa", "bbbb"], header=("h",)), limits)

    assert len(messages[0][0].fields) == fields


def test_notes_follow_the_table_in_the_last_part() -> None:
    (embed,) = chunk(_doc(["a"], notes=("note 1", "note 2")))[0]

    assert embed.description == "Header\n```ansi\na\n```\nnote 1\nnote 2"


def test_notes_that_do_not_fit_get_their_own_field() -> None:
    limits = Limits(description=18, chars_per_message=1000)

    messages = chunk(_doc(["aaaa"], header=("h",), notes=("nn",)), limits)

    assert _parts(messages) == [["h\n```ansi\naaaa\n```", "nn"]]


def test_no_entries_means_no_code_block() -> None:
    doc = _doc([], columns=("col",), notes=("No players match.",))

    (embed,) = chunk(doc)[0]

    assert embed.description == "Header\nNo players match."


# --- overflow -----------------------------------------------------------------------

OVERFLOW = Limits(
    description=150, field_value=60, fields=2, chars_per_message=300, messages=3
)


@pytest.mark.parametrize("count", [5, 11, 37, 200])
def test_overflow_keeps_the_longest_prefix(count: int) -> None:
    entries = [f"entry {i:03d}" for i in range(count)]

    messages = chunk(_doc(entries), OVERFLOW)

    _assert_within_limits(messages, OVERFLOW)
    rows = [line for block in _blocks(messages) for line in block]
    assert rows == entries[: len(rows)]
    match = OMITTED.fullmatch(_parts(messages)[-1][-1].split("\n")[-1])
    if match is None:  # everything fitted
        assert rows == entries
    else:
        assert int(match.group(1)) == count - len(rows)


def test_overflow_cut_point_depends_only_on_capacity() -> None:
    """The kept prefix is maximal: more capacity keeps more, the same keeps the same."""
    entries = [f"entry {i:03d}" for i in range(500)]

    def shown(messages: int) -> int:
        limits = Limits(**{**OVERFLOW.__dict__, "messages": messages})
        return sum(len(block) for block in _blocks(chunk(_doc(entries), limits)))

    assert shown(2) < shown(3) < shown(4)
    assert shown(3) == shown(3)


# --- last-resort clipping -------------------------------------------------------------


def test_long_title_and_footer_are_clipped() -> None:
    doc = Document(
        title="T" * 300, url=URL, header=("h",), entries=(), footer="F" * 3000
    )

    (embed,) = chunk(doc)[0]

    assert embed.title is not None
    assert len(embed.title) == 256
    assert embed.title.endswith("…")
    assert embed.footer is not None
    assert len(embed.footer) == 2048


def test_long_header_is_clipped_to_the_description() -> None:
    limits = Limits(description=50, chars_per_message=1000)

    messages = chunk(_doc(["a"], header=("h" * 80,)), limits)

    _assert_within_limits(messages, limits)
    assert _parts(messages) == [["h" * 49 + "…", "```ansi\na\n```"]]


def test_columns_wider_than_a_description_are_an_error() -> None:
    limits = Limits(description=20, chars_per_message=1000)

    with pytest.raises(ValueError, match="columns do not fit"):
        chunk(_doc(["a"], header=(), columns=("c" * 50,)), limits)


def test_header_leaving_no_room_for_the_omission_line_is_an_error() -> None:
    limits = Limits(description=20, fields=0, chars_per_message=1000, messages=1)

    with pytest.raises(ValueError, match="header does not fit"):
        chunk(_doc(["entry"] * 10, header=("h" * 20,)), limits)


def test_pathological_entry_is_clipped_not_dropped() -> None:
    messages = chunk(_doc(["a", "x" * 5000]))

    _assert_within_limits(messages, DISCORD_LIMITS)
    blocks = _blocks(messages)
    assert blocks[-1][0].endswith("…")
    assert blocks[0] == ["a"]
