"""`execute`: every command and every expected failure, at the commands layer
(fake fetcher, in-memory store). The Worker end-to-end tests cover the wiring."""

import re
from collections.abc import Callable
from datetime import timedelta

import pytest

from builders import FETCHED_AT, FETCHED_AT_TAG, fixture_bytes, plain
from cobra_bot import fonts as bundled_fonts
from cobra_bot import messages
from cobra_bot.cobra.cache import InMemoryCacheStore, TournamentCache, tournament_key
from cobra_bot.cobra.client import CobraError, NotFound, Private, Unavailable
from cobra_bot.commands import Command, Images, Reply, execute
from cobra_bot.formatting.chunking import Message

type LoadRaw = Callable[[str], object]

FONTS = bundled_fonts.load()  # read-only, shared by every test


class Fetcher:
    def __init__(self, bodies: dict[int, bytes], codes: dict[str, int] | None = None):
        self.bodies = bodies
        self.codes = codes or {}
        self.error: CobraError | None = None

    def fetch_tournament(self, tournament_id: int) -> bytes:
        if self.error:
            raise self.error
        if tournament_id not in self.bodies:
            raise NotFound("no such tournament")
        return self.bodies[tournament_id]

    def resolve_shortcode(self, code: str) -> int:
        if self.error:
            raise self.error
        if code not in self.codes:
            raise NotFound("no such code")
        return self.codes[code]


def _cache(
    fetcher: Fetcher, store: InMemoryCacheStore | None = None
) -> TournamentCache:
    return TournamentCache(
        store or InMemoryCacheStore(), fetcher, clock=lambda: FETCHED_AT
    )


def _setup() -> tuple[TournamentCache, Fetcher]:
    fetcher = Fetcher(
        {
            4909: fixture_bytes("single_sided_top8"),
            5018: fixture_bytes("dss"),
            5125: fixture_bytes("not_started"),
        },
        codes={"QNSF": 5018},
    )
    return _cache(fetcher), fetcher


def run(command: Command, cache: TournamentCache) -> Reply:
    return execute(command, cache, FONTS)


def _images(reply: object) -> Images:
    assert isinstance(reply, Images), reply
    return reply


def _messages(reply: object) -> tuple[Message, ...]:
    assert isinstance(reply, tuple), reply
    return reply


def _text(reply: tuple[Message, ...]) -> str:
    """All embed text, without colours."""
    parts = (part for m in reply for e in m for part in (e.description, *e.fields))
    return plain("\n".join(parts))


# --- commands ------------------------------------------------------------------------


def test_pairings() -> None:
    cache, _ = _setup()

    reply = _images(run(Command("pairings", "4909", round=1), cache))

    page = reply.pages[0]  # 23 tables, 46 players: two pages
    assert page.embed.title == "Single-Sided Top 8 Fixture"
    assert page.embed.description.startswith("**Round 1 pairings — complete**\n")
    assert page.png.startswith(b"\x89PNG")


def test_standings() -> None:
    cache, _ = _setup()

    reply = _images(run(Command("standings", "4909"), cache))

    page = reply.pages[0]  # 23 tables, 46 players: two pages
    assert page.embed.description.startswith("**Standings after round 8**\n")
    assert page.embed.image == page.filename == "standings-1.png"


def test_player() -> None:
    cache, _ = _setup()

    reply = _messages(run(Command("player", "4909", query="layer0017"), cache))

    assert re.search(r"^ 2[.] Player0017 +18$", _text(reply), re.MULTILINE)


def test_shortcode_reference() -> None:
    cache, _ = _setup()

    reply = _images(run(Command("pairings", "qnsf"), cache))

    assert reply.pages[0].embed.description.startswith(
        "**Round 3 pairings — in progress**"
    )


def test_no_players_match() -> None:
    cache, _ = _setup()

    reply = _messages(run(Command("player", "4909", query="nobody"), cache))

    assert "No players match." in _text(reply)


# --- round and state errors ---------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "reply"),
    [
        (Command("pairings", "4909", round=9), messages.TOP_CUT_NOT_SUPPORTED),
        (Command("pairings", "4909", round=15), messages.round_out_of_range(15, 14)),
        (Command("pairings", "5125"), messages.NOT_STARTED),
        (Command("standings", "5125"), messages.NOT_STARTED),
    ],
    ids=["top-cut", "out-of-range", "pairings-not-started", "standings-not-started"],
)
def test_round_state_errors(command: Command, reply: str) -> None:
    cache, _ = _setup()

    assert run(command, cache) == reply


# --- FR-16 errors ---------------------------------------------------------------------


@pytest.mark.parametrize("tournament", ["abc!", "https://example.com/tournaments/1"])
def test_invalid_reference(tournament: str) -> None:
    cache, _ = _setup()

    assert run(Command("standings", tournament), cache) == messages.INVALID_REFERENCE


@pytest.mark.parametrize(
    ("tournament", "reply"),
    [("1", messages.TOURNAMENT_NOT_FOUND), ("ZQXJ", messages.TOURNAMENT_NOT_FOUND)],
    ids=["id", "shortcode"],
)
def test_not_found(tournament: str, reply: str) -> None:
    cache, _ = _setup()

    assert run(Command("standings", tournament), cache) == reply


@pytest.mark.parametrize(
    ("error", "reply"),
    [
        (Private("401"), messages.TOURNAMENT_PRIVATE),
        (Unavailable("down"), messages.COBRA_UNAVAILABLE),
    ],
)
def test_cobra_failures_without_cache(error: CobraError, reply: str) -> None:
    cache, fetcher = _setup()
    fetcher.error = error

    assert run(Command("standings", "4909"), cache) == reply


@pytest.mark.parametrize(
    ("error", "notice"),
    [
        (Unavailable("down"), f"Cobra unavailable — data from {FETCHED_AT_TAG}"),
        (Private("401"), f"Tournament is now private — data from {FETCHED_AT_TAG}"),
    ],
)
def test_stale_data_is_served_with_notice(error: CobraError, notice: str) -> None:
    store = InMemoryCacheStore()
    store.put(tournament_key(4909), fixture_bytes("single_sided_top8"), FETCHED_AT)
    fetcher = Fetcher({})
    fetcher.error = error
    cache = TournamentCache(
        store, fetcher, clock=lambda: FETCHED_AT + timedelta(minutes=10)
    )

    reply = _images(run(Command("standings", "4909"), cache))

    assert reply.pages[0].embed.description.split("\n")[1] == notice


@pytest.mark.parametrize("body", [b"not json", b'{"players": [{"rank": 1}]}'])
def test_unreadable_export(body: bytes) -> None:
    cache = _cache(Fetcher({4909: body}))

    assert run(Command("standings", "4909"), cache) == messages.COBRA_DATA_UNREADABLE
