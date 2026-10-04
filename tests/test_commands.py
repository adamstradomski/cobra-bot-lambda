"""`execute`: every command and every expected failure, at the commands layer
(fake fetcher, in-memory store). The Worker end-to-end tests cover the wiring."""

import json
import logging
from collections.abc import Callable
from datetime import timedelta

import pytest

from builders import FETCHED_AT, FETCHED_AT_TAG, fixture_bytes
from cobra_bot import fonts as bundled_fonts
from cobra_bot import messages
from cobra_bot.cobra.cache import InMemoryCacheStore, TournamentCache, tournament_key
from cobra_bot.cobra.client import CobraError, NotFound, Private, Unavailable
from cobra_bot.commands import Command, Images, Job, Reply, execute, parse_command
from cobra_bot.domain.models import Player
from cobra_bot.domain.rounds import name_order
from cobra_bot.formatting.embed import Embed

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


# --- commands ------------------------------------------------------------------------


@pytest.mark.req("FR-01")
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

    reply = _images(run(Command("player", "4909", query="layer0017"), cache))

    (page,) = reply.pages
    assert page.embed.description.startswith("**Players matching “layer0017”**")
    assert page.embed.footer == "Round 14 · 1 player"
    assert page.filename == "players-1.png"


@pytest.mark.req("FR-12")
def test_shortcode_reference() -> None:
    cache, _ = _setup()

    reply = _images(run(Command("pairings", "qnsf"), cache))

    assert reply.pages[0].embed.description.startswith(
        "**Round 3 pairings — in progress**"
    )


def test_no_players_match() -> None:
    cache, _ = _setup()

    reply = run(Command("player", "4909", query="nobody"), cache)

    assert isinstance(reply, Embed), reply
    assert reply.description == (
        f"**Players matching “nobody”**\nData from {FETCHED_AT_TAG}\nNo players match."
    )
    assert reply.title == "Single-Sided Top 8 Fixture"
    assert reply.image is None


# --- round and state errors ---------------------------------------------------------


@pytest.mark.req("FR-16")
@pytest.mark.parametrize(
    ("command", "reply"),
    [
        (Command("pairings", "4909", round=15), messages.round_out_of_range(15, 14)),
        (Command("pairings", "5125"), messages.NOT_STARTED),
        (Command("standings", "5125"), messages.NOT_STARTED),
    ],
    ids=["out-of-range", "pairings-not-started", "standings-not-started"],
)
def test_round_state_errors(command: Command, reply: str) -> None:
    cache, _ = _setup()

    assert run(command, cache) == reply


# --- FR-16 errors ---------------------------------------------------------------------


@pytest.mark.req("FR-16")
@pytest.mark.parametrize("tournament", ["abc!", "https://example.com/tournaments/1"])
def test_invalid_reference(tournament: str) -> None:
    cache, _ = _setup()

    assert run(Command("standings", tournament), cache) == messages.INVALID_REFERENCE


@pytest.mark.req("FR-16")
@pytest.mark.parametrize(
    ("tournament", "reply"),
    [("1", messages.TOURNAMENT_NOT_FOUND), ("ZQXJ", messages.TOURNAMENT_NOT_FOUND)],
    ids=["id", "shortcode"],
)
def test_not_found(tournament: str, reply: str) -> None:
    cache, _ = _setup()

    assert run(Command("standings", tournament), cache) == reply


@pytest.mark.req("FR-16")
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


@pytest.mark.req("FR-15")
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

    assert reply.pages[0].embed.description.split("\n")[2] == notice


@pytest.mark.parametrize("body", [b"not json", b'{"players": [{"rank": 1}]}'])
def test_unreadable_export(body: bytes) -> None:
    cache = _cache(Fetcher({4909: body}))

    assert run(Command("standings", "4909"), cache) == messages.COBRA_DATA_UNREADABLE


@pytest.mark.req("FR-13", "AC-26")
def test_ac26_standings_before_the_first_round_list_the_registered_players() -> None:
    """Players registered, no round paired: standings list them; pairings say
    the tournament has not started."""
    export = json.loads(fixture_bytes("dss"))
    export["rounds"] = []
    cache = _cache(Fetcher({5132: json.dumps(export).encode()}))

    standings = _images(run(Command("standings", "5132"), cache))
    pairings = run(Command("pairings", "5132"), cache)

    first = standings.pages[0].embed
    assert first.description.startswith("**Registered players — not started yet**\n")
    assert first.footer == "31 players"
    assert pairings == messages.NOT_STARTED


def test_player_list_shows_every_named_player() -> None:
    """Several comma-separated names: one card per matching player."""
    cache, _ = _setup()

    reply = _images(run(Command("player", "4909", query="0017, 0042, nobody"), cache))

    (page,) = reply.pages
    assert page.embed.footer == "Round 14 · 2 players"
    assert page.embed.description.endswith("No players match “nobody”.")


def test_player_search_before_round_1_ranks_like_standings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-26: before the first round, search shows the rank standings show
    (by name), not the export's registration order."""
    from cobra_bot.formatting import image

    drawn: list[tuple[str, int]] = []
    real = image.players_table

    def spy(t: object, players: list[Player]) -> object:
        drawn.extend((p.name, p.rank) for p in players)
        return real(t, players)  # type: ignore[arg-type]

    monkeypatch.setattr(image, "players_table", spy)
    export = json.loads(fixture_bytes("dss"))
    export["rounds"] = []
    count = len(export["players"])
    for n, entry in enumerate(export["players"]):
        entry["rank"] = count - n  # registration order, not by name
    cache = _cache(Fetcher({5132: json.dumps(export).encode()}))

    run(Command("player", "5132", query="Player0001, Player0002"), cache)

    by_name = sorted(
        (e["name"] for e in export["players"]),
        key=lambda name: name_order(name),
    )
    assert drawn == [
        ("Player0001", by_name.index("Player0001") + 1),
        ("Player0002", by_name.index("Player0002") + 1),
    ]


def test_images_are_reused_until_the_data_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Separate from the 60 s data cache: same data, no drawing; new data,
    drawn again. The header (data age) is always new."""
    from cobra_bot.cobra.cache import InMemoryCacheStore
    from cobra_bot.formatting import image
    from cobra_bot.image_cache import ImageCache

    drawn: list[int] = []
    real = image.render_png
    monkeypatch.setattr(
        image, "render_png", lambda table, fonts: drawn.append(1) or real(table, fonts)
    )
    images = ImageCache(InMemoryCacheStore(), clock=lambda: FETCHED_AT)
    export = json.loads(fixture_bytes("dss"))
    fetcher = Fetcher({5018: json.dumps(export).encode()})
    cache = _cache(fetcher)
    command = Command("standings", "5018")

    first = _images(execute(command, cache, FONTS, images))
    second = _images(execute(command, cache, FONTS, images))
    assert len(drawn) == 1
    assert second.pages[0].png == first.pages[0].png

    export["players"][0]["matchPoints"] += 3  # a result came in
    fetcher.bodies[5018] = json.dumps(export).encode()
    later = _cache(fetcher)  # data cache refreshed (another 60 s window)
    execute(command, later, FONTS, images)
    assert len(drawn) == 2


def _dss_with_points_off(extra: int) -> TournamentCache:
    export = json.loads(fixture_bytes("dss"))
    export["players"][0]["matchPoints"] += extra
    return _cache(Fetcher({5018: json.dumps(export).encode()}))


def test_standings_log_points_that_fit_no_round(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Points adjusted by hand: standings fall back to the last complete round
    and say so in the log."""
    with caplog.at_level(logging.WARNING, logger="cobra_bot.commands"):
        run(Command("standings", "5018"), _dss_with_points_off(1))

    assert "tournament 5018: match points fit no Swiss round" in caplog.text


def test_standings_whose_points_fit_a_round_log_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="cobra_bot.commands"):
        run(Command("standings", "5018"), _dss_with_points_off(0))

    assert caplog.text == ""


# --- top cut and bracket -----------------------------------------------------------


@pytest.mark.req("FR-02", "FR-19")
def test_pairings_of_a_top_cut_round() -> None:
    cache, _ = _setup()

    reply = _images(run(Command("pairings", "4909", round=9), cache))

    assert reply.pages[0].embed.description.startswith(
        "**Top cut round 1 pairings — complete**"
    )


def test_default_pairings_show_the_latest_round_in_the_top_cut() -> None:
    cache, _ = _setup()

    reply = _images(run(Command("pairings", "4909"), cache))

    assert reply.pages[0].embed.description.startswith(
        "**Top cut round 6 pairings — complete**"
    )


@pytest.mark.req("FR-19", "FR-23", "AC-29")
def test_top_cut() -> None:
    cache, _ = _setup()

    reply = _images(run(Command("top-cut", "4909"), cache))

    (page,) = reply.pages
    assert page.embed.description.startswith("**Top 8 cut — finished**")
    assert page.filename == "top-cut-1.png"


@pytest.mark.req("FR-19", "FR-24", "AC-30")
def test_bracket() -> None:
    cache, _ = _setup()

    reply = _images(run(Command("bracket", "4909"), cache))

    (page,) = reply.pages
    assert page.embed.description.startswith(
        "**Top 8 bracket (double elimination) — finished**"
    )
    assert page.filename == "bracket-1.png"
    assert page.png.startswith(b"\x89PNG")


@pytest.mark.req("FR-23", "AC-29")
@pytest.mark.parametrize("name", ["top-cut", "bracket"])
def test_no_top_cut(name: str) -> None:
    cache, _ = _setup()

    assert run(Command(name, "5018"), cache) == messages.NO_TOP_CUT  # type: ignore[arg-type]


@pytest.mark.req("FR-24")
def test_bracket_for_a_cut_size_without_one() -> None:
    export = json.loads(fixture_bytes("single_sided_top8"))
    export["cutToTop"] = 6
    export["rounds"] = export["rounds"][:8]
    export["eliminationPlayers"] = []
    cache = _cache(Fetcher({4909: json.dumps(export).encode()}))

    assert run(Command("bracket", "4909"), cache) == messages.bracket_unavailable(6)


def test_bracket_reuses_the_cached_image() -> None:
    from cobra_bot.image_cache import ImageCache

    cache, _ = _setup()
    images = ImageCache(InMemoryCacheStore(), clock=lambda: FETCHED_AT)

    first = _images(execute(Command("bracket", "4909"), cache, FONTS, images))
    second = _images(execute(Command("bracket", "4909"), cache, FONTS, images))

    assert (images.misses, images.hits) == (1, 1)
    assert first.pages[0].png == second.pages[0].png


def _interaction(name: str, **options: object) -> dict[str, object]:
    return {
        "data": {
            "name": "cobra",
            "options": [
                {
                    "name": name,
                    "options": [{"name": k, "value": v} for k, v in options.items()],
                }
            ],
        }
    }


@pytest.mark.parametrize("name", ["top-cut", "bracket"])
def test_parse_new_subcommands(name: str) -> None:
    command = parse_command(_interaction(name, tournament="4909", round=3))

    assert command == Command(name, "4909")  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["top-cut", "bracket"])
def test_new_subcommands_survive_the_job_payload(name: str) -> None:
    job = Job("app", "token", Command(name, "4909"))  # type: ignore[arg-type]

    assert Job.from_payload(job.to_payload()) == job
