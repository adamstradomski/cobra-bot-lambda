import json
from collections.abc import Callable

import httpx
import pytest

from builders import pairing, player, seat, tournament
from cobra_bot.discord.api import (
    EPHEMERAL,
    USER_AGENT,
    DiscordError,
    WebhookClient,
    make_http_client,
)
from cobra_bot.domain.rounds import (
    PairingsView,
    StandingsView,
    pairings_view,
    standings_view,
)
from cobra_bot.formatting.chunking import Embed, chunk
from cobra_bot.formatting.pairings import format_pairings
from cobra_bot.formatting.standings import format_standings

APP = "123456"
TOKEN = "secret-interaction-token"
WEBHOOK = f"https://discord.com/api/v10/webhooks/{APP}/{TOKEN}"

type Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0) if self.responses else httpx.Response(200)

    def client(self) -> WebhookClient:
        http = httpx.Client(transport=httpx.MockTransport(self.handler))
        return WebhookClient(http, APP, sleep=self.sleeps.append)

    def payloads(self) -> list[dict[str, object]]:
        return [json.loads(r.content) for r in self.requests]


def _message(text: str = "x") -> tuple[Embed, ...]:
    return (Embed(description=text),)


# --- AC-21 ---------------------------------------------------------------------------


def test_ac21_every_payload_blocks_mentions_and_names_are_escaped() -> None:
    names = ("@Mention", "*bold_name~")
    players = tuple(player(i, names[i % 2], rank=i) for i in range(1, 301))
    rnd = tuple(
        pairing(t, seat(2 * t - 1, "corp", 3), seat(2 * t, "runner", 0))
        for t in range(1, 151)
    )
    t = tournament(rnd, players=players)
    standings = standings_view(t)
    pairings = pairings_view(t)
    assert isinstance(standings, StandingsView)
    assert isinstance(pairings, PairingsView)
    documents = [format_standings(t, standings), format_pairings(t, pairings)]
    recorder = Recorder()
    client = recorder.client()

    for doc in documents:
        messages = chunk(doc)
        assert len(messages) > 1  # follow-ups are covered too
        client.send(TOKEN, messages, ephemeral=False)

    payloads = recorder.payloads()
    assert payloads
    descriptions: list[str] = []
    for payload in payloads:
        assert payload["allowed_mentions"] == {"parse": []}
        embeds = payload["embeds"]
        assert isinstance(embeds, list)
        descriptions += [e["description"] for e in embeds]
    text = "\n".join(descriptions)
    assert "*bold_name~" not in text  # never sent unescaped
    assert r"\*bold\_name\~" in text
    assert "@Mention" in text  # not markup; pings are blocked by allowed_mentions


# --- routing --------------------------------------------------------------------------


def test_first_message_edits_original_rest_are_follow_ups() -> None:
    recorder = Recorder()

    recorder.client().send(
        TOKEN, [_message("a"), _message("b"), _message("c")], ephemeral=False
    )

    assert [(r.method, str(r.url)) for r in recorder.requests] == [
        ("PATCH", f"{WEBHOOK}/messages/@original"),
        ("POST", WEBHOOK),
        ("POST", WEBHOOK),
    ]
    assert [p["embeds"] for p in recorder.payloads()] == [
        [{"description": "a"}],
        [{"description": "b"}],
        [{"description": "c"}],
    ]


def test_ephemeral_follow_ups_carry_the_flag() -> None:
    recorder = Recorder()

    recorder.client().send(TOKEN, [_message("a"), _message("b")], ephemeral=True)

    first, second = recorder.payloads()
    assert "flags" not in first  # the deferred response already is ephemeral
    assert second["flags"] == EPHEMERAL == 64


def test_embed_title_and_url() -> None:
    recorder = Recorder()
    embed = Embed(
        description="d",
        title="Cup",
        url="https://tournaments.nullsignal.games/tournaments/1",
    )

    recorder.client().send(TOKEN, [(embed,)], ephemeral=False)

    assert recorder.payloads()[0]["embeds"] == [
        {
            "description": "d",
            "title": "Cup",
            "url": "https://tournaments.nullsignal.games/tournaments/1",
        }
    ]


def test_send_text() -> None:
    recorder = Recorder()

    recorder.client().send_text(TOKEN, "Tournament not found.")

    assert recorder.payloads() == [
        {
            "embeds": [{"description": "Tournament not found."}],
            "allowed_mentions": {"parse": []},
        }
    ]


# --- rate limits (T19 DoD) ------------------------------------------------------------


def test_429_is_retried_after_retry_after_header() -> None:
    recorder = Recorder(
        httpx.Response(429, headers={"Retry-After": "1.5"}, json={"retry_after": 1.5}),
        httpx.Response(200),
    )

    recorder.client().follow_up(TOKEN, {"content": "x"})

    assert len(recorder.requests) == 2
    assert recorder.sleeps == [1.5]


def test_429_uses_body_retry_after_without_header() -> None:
    recorder = Recorder(
        httpx.Response(429, json={"retry_after": 0.25}), httpx.Response(204)
    )

    recorder.client().follow_up(TOKEN, {})

    assert recorder.sleeps == [0.25]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, headers={"Retry-After": "60"}),
        httpx.Response(429, content=b"no hint"),
    ],
    ids=["too-long", "no-hint"],
)
def test_unusable_rate_limit_fails_without_sleeping(response: httpx.Response) -> None:
    recorder = Recorder(response)

    with pytest.raises(DiscordError, match="rate limited"):
        recorder.client().follow_up(TOKEN, {})
    assert recorder.sleeps == []


def test_persistent_rate_limit_gives_up() -> None:
    limited = [httpx.Response(429, headers={"Retry-After": "0.1"}) for _ in range(10)]
    recorder = Recorder(*limited)

    with pytest.raises(DiscordError, match="still rate limited"):
        recorder.client().follow_up(TOKEN, {})
    assert len(recorder.requests) == 4


# --- errors ---------------------------------------------------------------------


def test_http_error_does_not_leak_the_token() -> None:
    recorder = Recorder(httpx.Response(404))

    with pytest.raises(DiscordError) as excinfo:
        recorder.client().edit_original(TOKEN, {})
    assert TOKEN not in str(excinfo.value)


def test_network_error_is_not_retried_and_does_not_leak_the_token() -> None:
    calls: list[httpx.Request] = []

    def timeout(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout(f"timed out: {request.url}", request=request)

    http = httpx.Client(transport=httpx.MockTransport(timeout))
    with pytest.raises(DiscordError) as excinfo:
        WebhookClient(http, APP).follow_up(TOKEN, {})
    assert len(calls) == 1
    assert TOKEN not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__


def test_http_client_user_agent() -> None:
    with make_http_client() as http:
        assert http.headers["User-Agent"] == USER_AGENT
