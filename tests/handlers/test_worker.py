"""Worker end to end: Job in, Discord webhook requests out, with mocked Cobra and
Discord HTTP and the in-memory store. Error mapping is covered in test_commands."""

import json
import logging
import re

import httpx
import pytest

from builders import FETCHED_AT, fixture_bytes
from cobra_bot.cobra.cache import Fetcher, InMemoryCacheStore, TournamentCache
from cobra_bot.cobra.client import CobraClient
from cobra_bot.commands import Command, Job
from cobra_bot.discord.api import WebhookClient
from cobra_bot.handlers.worker import WorkerApp

COBRA = "https://tournaments.nullsignal.games"
WEBHOOK = "https://discord.com/api/v10/webhooks/app-1/tok-1"
FIXTURES = {4909: "single_sided_top8", 4990: "large_top_cut", 5018: "dss"}


def _cobra(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/QNSF":
        return httpx.Response(302, headers={"Location": f"{COBRA}/tournaments/5018"})
    match = re.fullmatch(r"/tournaments/(\d+)\.json", path)
    if match and int(match.group(1)) in FIXTURES:
        return httpx.Response(200, content=fixture_bytes(FIXTURES[int(match.group(1))]))
    return httpx.Response(302, headers={"Location": f"{COBRA}/error"})


class Discord:
    def __init__(self, status: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status)

    def calls(self) -> list[tuple[str, str, dict[str, object]]]:
        return [(r.method, str(r.url), json.loads(r.content)) for r in self.requests]


def _worker(discord: Discord, fetcher: Fetcher | None = None) -> WorkerApp:
    cobra = CobraClient(httpx.Client(transport=httpx.MockTransport(_cobra)))
    cache = TournamentCache(
        InMemoryCacheStore(),
        fetcher or cobra,
        clock=lambda: FETCHED_AT,
    )
    discord_http = httpx.Client(transport=httpx.MockTransport(discord))
    return WorkerApp(cache, lambda app_id: WebhookClient(discord_http, app_id))


def _job(command: Command) -> dict[str, object]:
    return Job("app-1", "tok-1", command).to_payload()


def test_pairings_end_to_end() -> None:
    discord = Discord()

    _worker(discord).handle(_job(Command("pairings", "QNSF")))

    ((method, url, payload),) = discord.calls()
    assert (method, url) == ("PATCH", f"{WEBHOOK}/messages/@original")
    assert payload["allowed_mentions"] == {"parse": []}
    embed = payload["embeds"][0]  # type: ignore[index]
    assert embed["title"] == "DSS Fixture"
    assert embed["description"].startswith("**Round 3 pairings — in progress**")


def test_standings_end_to_end_with_follow_ups() -> None:
    discord = Discord()

    _worker(discord).handle(_job(Command("standings", "4990")))

    calls = discord.calls()
    assert [c[0] for c in calls] == ["PATCH"] + ["POST"] * (len(calls) - 1)
    assert len(calls) > 1
    assert all("flags" not in payload for _, _, payload in calls)


def test_player_end_to_end() -> None:
    discord = Discord()

    _worker(discord).handle(_job(Command("player", "4909", query="Player00")))

    ((method, _, payload),) = discord.calls()
    assert method == "PATCH"
    description = payload["embeds"][0]["description"]  # type: ignore[index]
    assert "…and" in description and "more matched" in description


def test_error_reply_end_to_end() -> None:
    discord = Discord()

    _worker(discord).handle(_job(Command("standings", "99999999")))

    assert discord.calls() == [
        (
            "PATCH",
            f"{WEBHOOK}/messages/@original",
            {
                "embeds": [{"description": "Tournament not found.", "color": 14725690}],
                "allowed_mentions": {"parse": []},
            },
        )
    ]


def test_unexpected_failure_sends_generic_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Exploding:
        def fetch_tournament(self, tournament_id: int) -> bytes:
            raise RuntimeError("bug")

        def resolve_shortcode(self, code: str) -> int:
            raise RuntimeError("bug")

    discord = Discord()

    with caplog.at_level(logging.ERROR):
        _worker(discord, Exploding()).handle(_job(Command("standings", "4909")))

    description = discord.calls()[0][2]["embeds"][0]["description"]  # type: ignore[index]
    assert description == "Something went wrong. Please try again later."
    assert "command standings failed" in caplog.text


def test_discord_failure_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        _worker(Discord(status=404)).handle(_job(Command("standings", "4909")))

    assert "not delivered" in caplog.text
    assert "tok-1" not in caplog.text


def test_malformed_job_sends_nothing(caplog: pytest.LogCaptureFixture) -> None:
    discord = Discord()

    with caplog.at_level(logging.ERROR):
        _worker(discord).handle({"command": {"name": "standings"}})

    assert discord.requests == []
    assert "malformed job" in caplog.text
