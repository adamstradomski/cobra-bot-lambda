from collections.abc import Callable

import httpx
import pytest

from cobra_bot.cobra.client import (
    TIMEOUT_S,
    USER_AGENT,
    CobraClient,
    NotFound,
    Private,
    Unavailable,
    make_http_client,
)

BASE = "https://tournaments.nullsignal.games"

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, seen: list[httpx.Request] | None = None) -> CobraClient:
    def record(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(record), follow_redirects=False)
    return CobraClient(http)


def _redirect(location: str) -> Handler:
    return lambda _: httpx.Response(302, headers={"Location": location})


# --- tournament JSON (T14 DoD: 200, 404, 500, timeout) -------------------------------


def test_200_returns_raw_json() -> None:
    seen: list[httpx.Request] = []
    body = b'{"name": "T", "players": [], "rounds": []}'
    client = _client(lambda _: httpx.Response(200, content=body), seen)

    assert client.fetch_tournament(4909) == body
    assert str(seen[0].url) == f"{BASE}/tournaments/4909.json"


def test_404_is_not_found() -> None:
    with pytest.raises(NotFound):
        _client(lambda _: httpx.Response(404)).fetch_tournament(1)


def test_500_is_unavailable() -> None:
    with pytest.raises(Unavailable):
        _client(lambda _: httpx.Response(500)).fetch_tournament(1)


@pytest.mark.req("NFR-16")
def test_timeout_is_unavailable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(Unavailable, match="timeout"):
        _client(timeout).fetch_tournament(1)


def test_connection_error_is_unavailable() -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(Unavailable):
        _client(refused).fetch_tournament(1)


# --- Cobra specifics (findings Q5) ----------------------------------------------------


@pytest.mark.parametrize(
    "location", ["https://tournaments.nullsignal.games/error", "/error"]
)
def test_redirect_to_error_is_not_found(location: str) -> None:
    with pytest.raises(NotFound):
        _client(_redirect(location)).fetch_tournament(99999999)


@pytest.mark.req("FR-21")
def test_401_is_private() -> None:
    body = '{"error":"🔒 Sorry, you can\'t do that"}'.encode()
    with pytest.raises(Private):
        _client(lambda _: httpx.Response(401, content=body)).fetch_tournament(5125)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"<html>Cobra</html>"),
        httpx.Response(200, content=b"[1, 2]"),
        httpx.Response(302, headers={"Location": "/somewhere"}),
        httpx.Response(403),
    ],
    ids=["html", "not-an-object", "other-redirect", "403"],
)
def test_unexpected_responses_are_unavailable(response: httpx.Response) -> None:
    with pytest.raises(Unavailable):
        _client(lambda _: response).fetch_tournament(1)


# --- shortcodes (findings Q4) ---------------------------------------------------------


@pytest.mark.req("FR-12")
def test_shortcode_resolves_from_redirect() -> None:
    seen: list[httpx.Request] = []
    client = _client(_redirect(f"{BASE}/tournaments/5018"), seen)

    assert client.resolve_shortcode("QNSF") == 5018
    assert str(seen[0].url) == f"{BASE}/QNSF"


def test_unknown_shortcode_is_not_found() -> None:
    with pytest.raises(NotFound):
        _client(_redirect(f"{BASE}/tournaments/not_found?code=ZQXJ")).resolve_shortcode(
            "ZQXJ"
        )


def test_shortcode_of_private_tournament() -> None:
    with pytest.raises(Private):
        _client(_redirect(f"{BASE}/")).resolve_shortcode("N9WI")


@pytest.mark.parametrize(
    "response",
    [httpx.Response(200, content=b"<html/>"), httpx.Response(503)],
    ids=["no-redirect", "503"],
)
def test_shortcode_unexpected_responses_are_unavailable(
    response: httpx.Response,
) -> None:
    with pytest.raises(Unavailable):
        _client(lambda _: response).resolve_shortcode("QNSF")


# --- client configuration (NFR-16) ----------------------------------------------------


@pytest.mark.req("NFR-16")
def test_http_client_settings() -> None:
    with make_http_client() as http:
        assert http.headers["User-Agent"] == USER_AGENT
        assert http.timeout.read == TIMEOUT_S == 8.0
        assert http.follow_redirects is False
