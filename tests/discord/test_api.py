import json
from collections.abc import Callable

import httpx
import pytest

from builders import pairing, player, seat, tournament
from cobra_bot.discord.api import (
    DETAIL_CHARS,
    EPHEMERAL,
    USER_AGENT,
    Attachment,
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
from cobra_bot.formatting.chunking import FIELD_NAME, Embed, chunk
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


def test_ac21_every_payload_blocks_mentions_and_names_stay_in_code_blocks() -> None:
    """Names sit in ```ansi code blocks, where markdown and mentions do not render;
    a name cannot close the block early."""
    names = ("@Mention", "*bold_name~", "```@everyone")
    players = tuple(player(i, names[i % 3], rank=i) for i in range(1, 301))
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
    parts: list[str] = []
    for payload in payloads:
        assert payload["allowed_mentions"] == {"parse": []}
        embeds = payload["embeds"]
        assert isinstance(embeds, list)
        for e in embeds:
            parts += [e["description"], *(f["value"] for f in e.get("fields", []))]
    for part in parts:
        # Every part opens and closes its own block; names never add a fence.
        assert part.count("```") == 2, part
    text = "\n".join(parts)
    assert "*bold_name~" in text  # literal inside the code block, not escaped
    assert "@Mention" in text  # pings are blocked by allowed_mentions
    assert "'''@everyone" in text  # backticks replaced (C-7)


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


def test_embed_colour_fields_and_footer() -> None:
    recorder = Recorder()
    embed = Embed(description="d", fields=("f1", "f2"), footer="legend", color=0xE0B23A)

    recorder.client().send(TOKEN, [(embed,)], ephemeral=False)

    assert recorder.payloads()[0]["embeds"] == [
        {
            "description": "d",
            "color": 14725690,
            "fields": [
                {"name": FIELD_NAME, "value": "f1", "inline": False},
                {"name": FIELD_NAME, "value": "f2", "inline": False},
            ],
            "footer": {"text": "legend"},
        }
    ]


def test_send_text() -> None:
    recorder = Recorder()

    recorder.client().send_text(TOKEN, "Tournament not found.")

    assert recorder.payloads() == [
        {
            "embeds": [{"description": "Tournament not found.", "color": 14725690}],
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


def test_http_error_keeps_discords_reason_out_of_the_message() -> None:
    """`detail` says which field Discord rejected; the message stays short."""
    recorder = Recorder(httpx.Response(400, text='{"components": ["0"]}'))

    with pytest.raises(DiscordError) as excinfo:
        recorder.client().follow_up(TOKEN, {})
    assert str(excinfo.value) == "POST failed: HTTP 400"
    assert excinfo.value.detail == '{"components": ["0"]}'


def test_http_error_detail_is_cut() -> None:
    recorder = Recorder(httpx.Response(400, text="x" * 1000))

    with pytest.raises(DiscordError) as excinfo:
        recorder.client().follow_up(TOKEN, {})
    assert len(excinfo.value.detail) == DETAIL_CHARS


# --- attachments and components (scripts/preview.py) -----------------------------


def test_follow_up_without_extras_sends_json_and_no_query() -> None:
    recorder = Recorder()

    recorder.client().follow_up(TOKEN, {"content": "x"})

    (request,) = recorder.requests
    assert str(request.url) == WEBHOOK
    assert request.headers["Content-Type"] == "application/json"


def test_follow_up_with_components_asks_the_webhook_to_keep_them() -> None:
    recorder = Recorder()

    recorder.client().follow_up(TOKEN, {"components": []}, with_components=True)

    (request,) = recorder.requests
    assert str(request.url) == f"{WEBHOOK}?with_components=true"
    assert json.loads(request.content) == {"components": []}


def test_follow_up_with_files_sends_multipart() -> None:
    recorder = Recorder()
    payload = {"attachments": [{"id": 0, "filename": "a.png"}]}

    recorder.client().follow_up(
        TOKEN, payload, files=[Attachment("a.png", b"\x89PNG-bytes", "image/png")]
    )

    (request,) = recorder.requests
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    body = request.content
    assert b'name="payload_json"' in body
    assert json.dumps(payload).encode() in body
    assert b'name="files[0]"; filename="a.png"' in body
    assert b"Content-Type: image/png" in body
    assert b"\x89PNG-bytes" in body


def test_multipart_429_is_retried_with_the_files() -> None:
    recorder = Recorder(httpx.Response(429, headers={"Retry-After": "0.5"}))

    recorder.client().follow_up(TOKEN, {}, files=[Attachment("a.png", b"img")])

    assert len(recorder.requests) == 2
    assert all(b"img" in r.content for r in recorder.requests)
