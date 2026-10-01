import re
from collections.abc import Callable

import pytest

from builders import FETCHED_AT, pairing, player, seat, tournament
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.domain.rounds import StandingsView, standings_view
from cobra_bot.formatting.chunking import DISCORD_LIMITS, Limits, Message, chunk
from cobra_bot.formatting.document import Document
from cobra_bot.formatting.standings import format_standings

type LoadRaw = Callable[[str], object]

URL = "https://tournaments.nullsignal.games/tournaments/1/players/standings"
OMITTED = re.compile(r"…and (\d+) more — \[full list on Cobra\]\((\S+)\)")


def _doc(entries: list[str], header: tuple[str, ...] = ("Header",)) -> Document:
    return Document(title="Title", url=URL, header=header, entries=tuple(entries))


def _lines(messages: tuple[Message, ...]) -> list[str]:
    return [
        line
        for message in messages
        for embed in message
        for line in embed.description.split("\n")
    ]


def _assert_within_limits(messages: tuple[Message, ...], limits: Limits) -> None:
    assert len(messages) <= limits.messages
    for message in messages:
        assert 1 <= len(message) <= limits.embeds_per_message
        assert sum(e.chars for e in message) <= limits.chars_per_message
        for embed in message:
            assert 0 < len(embed.description) <= limits.description


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
    assert _lines(messages) == [*doc.header, *doc.entries]  # all, once, in order
    ranks = [int(line.split("\\.")[0]) for line in _lines(messages)[2:]]
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
    last = messages[-1][-1].description.split("\n")[-1]
    match = OMITTED.fullmatch(last)
    assert match is not None
    shown = len(_lines(messages)) - len(doc.header) - 1
    assert int(match.group(1)) == 1000 - shown
    assert match.group(2) == (
        "https://tournaments.nullsignal.games/tournaments/1/players/standings"
    )
    assert _lines(messages)[2 : 2 + shown] == list(doc.entries[:shown])


# --- packing rules ------------------------------------------------------------------


def test_small_document_is_one_embed_with_title_and_link() -> None:
    messages = chunk(_doc(["a", "b"]))

    assert len(messages) == 1
    (embed,) = messages[0]
    assert (embed.title, embed.url, embed.description) == ("Title", URL, "Header\na\nb")


def test_only_the_first_embed_has_a_title() -> None:
    limits = Limits(description=20, chars_per_message=1000)
    messages = chunk(_doc(["x" * 15] * 3), limits)

    embeds = [e for m in messages for e in m]
    assert [e.title for e in embeds] == ["Title", None, None, None]


def test_entries_are_never_split() -> None:
    entries = ["line one\nline two", "line three\nline four"]
    limits = Limits(description=20, chars_per_message=1000)

    messages = chunk(_doc(entries), limits)

    descriptions = [e.description for m in messages for e in m]
    assert descriptions == ["Header", entries[0], entries[1]]


def test_description_limit_starts_a_new_embed() -> None:
    limits = Limits(description=10, chars_per_message=1000)

    messages = chunk(_doc(["aaaa", "bbbb", "cccc"], header=("hh",)), limits)

    assert [e.description for e in messages[0]] == ["hh\naaaa", "bbbb\ncccc"]


def test_embed_count_limit_starts_a_new_message() -> None:
    limits = Limits(description=5, embeds_per_message=2, chars_per_message=1000)

    messages = chunk(_doc(["aaaa", "bbbb", "cccc"], header=("hh",)), limits)

    assert [[e.description for e in m] for m in messages] == [
        ["hh", "aaaa"],
        ["bbbb", "cccc"],
    ]


def test_message_char_limit_counts_title_and_starts_a_new_message() -> None:
    limits = Limits(description=100, chars_per_message=20)

    messages = chunk(_doc(["a" * 8, "b" * 8], header=("h",)), limits)

    # "Title" (5) + "h\naaaaaaaa" (10) = 15; adding "\nbbbbbbbb" would exceed 20.
    assert [[e.description for e in m] for m in messages] == [
        ["h\naaaaaaaa"],
        ["bbbbbbbb"],
    ]
    _assert_within_limits(messages, limits)


@pytest.mark.parametrize("count", [5, 11, 37, 200])
def test_overflow_keeps_the_longest_prefix(count: int) -> None:
    limits = Limits(
        description=120, embeds_per_message=1, chars_per_message=130, messages=3
    )
    entries = [f"entry {i:03d}" for i in range(count)]

    messages = chunk(_doc(entries), limits)

    _assert_within_limits(messages, limits)
    lines = _lines(messages)
    match = OMITTED.fullmatch(lines[-1])
    if match is None:  # everything fitted
        assert lines == ["Header", *entries]
        return
    shown = len(lines) - 2
    assert lines[1:-1] == entries[:shown]
    assert int(match.group(1)) == count - shown


def test_overflow_cut_point_depends_only_on_capacity() -> None:
    """The kept prefix is maximal: more capacity keeps more, the same keeps the same."""
    limits = Limits(description=120, embeds_per_message=1, chars_per_message=130)
    entries = [f"entry {i:03d}" for i in range(500)]

    def shown(messages: int) -> int:
        lines = _lines(
            chunk(_doc(entries), Limits(**{**limits.__dict__, "messages": messages}))
        )
        return len(lines) - 2

    assert shown(2) < shown(3) < shown(4)
    assert shown(3) == shown(3)


def test_long_title_is_clipped() -> None:
    doc = Document(title="T" * 300, url=URL, header=("h",), entries=())

    (embed,) = chunk(doc)[0]

    assert embed.title is not None
    assert len(embed.title) == 256
    assert embed.title.endswith("…")


def test_pathological_entry_is_clipped_not_dropped() -> None:
    messages = chunk(_doc(["x" * 5000]))

    _assert_within_limits(messages, DISCORD_LIMITS)
    assert _lines(messages)[1].endswith("…")
