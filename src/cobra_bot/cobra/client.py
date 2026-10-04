"""HTTP access to Cobra (docs/spec/cobra.md; NFR-16).

Redirects are never followed: Cobra signals "not found" and "private" through
them (docs/spec/cobra.md), and outbound requests must stay on Cobra.

| Response                                   | Tournament JSON | Shortcode      |
|--------------------------------------------|-----------------|----------------|
| 200 with a JSON object                     | body            | Unavailable    |
| 302 -> /tournaments/{id}                   | Unavailable     | id             |
| 302 -> /error, /tournaments/not_found, 404 | NotFound        | NotFound       |
| 401, or a shortcode 302 -> /               | Private         | Private        |
| 5xx, timeout, connection error, other      | Unavailable     | Unavailable    |
"""

import json
import re
import urllib.parse

import httpx

USER_AGENT = (
    "cobra-bot-lambda/0.1 (+https://github.com/adamstradomski/cobra-bot-lambda)"
)
TIMEOUT_S = 8.0
COBRA_BASE_URL = "https://tournaments.nullsignal.games"

_TOURNAMENT_PATH = re.compile(r"/tournaments/([0-9]+)/?")
_NOT_FOUND_PATHS = ("/error", "/tournaments/not_found")


class CobraError(Exception):
    """Base class for Cobra outcomes other than data."""


class NotFound(CobraError):
    pass


class Private(CobraError):
    pass


class Unavailable(CobraError):
    pass


def make_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT_S,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


class CobraClient:
    def __init__(self, http: httpx.Client, base_url: str = COBRA_BASE_URL) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    def fetch_tournament(self, tournament_id: int) -> bytes:
        """Raw JSON export of a tournament; raises a CobraError subclass otherwise."""
        response = self._get(f"/tournaments/{tournament_id}.json")
        if response.status_code == 200:
            try:
                data = json.loads(response.content)
            except ValueError:
                raise Unavailable("response is not JSON") from None
            if not isinstance(data, dict):
                raise Unavailable("response is not a JSON object")
            return response.content
        if response.status_code == 401:
            raise Private(f"tournament {tournament_id} is private")
        if self._is_not_found(response):
            raise NotFound(f"tournament {tournament_id} not found")
        raise Unavailable(f"unexpected HTTP {response.status_code}")

    def resolve_shortcode(self, code: str) -> int:
        """Tournament ID for a shortcode, read from Cobra's redirect."""
        response = self._get(f"/{urllib.parse.quote(code, safe='')}")
        if response.is_redirect:
            path = self._location_path(response)
            match = _TOURNAMENT_PATH.fullmatch(path)
            if match:
                return int(match.group(1))
            if path in ("", "/"):
                raise Private(f"shortcode {code} belongs to a private tournament")
        if response.status_code == 401:
            raise Private(f"shortcode {code} belongs to a private tournament")
        if self._is_not_found(response):
            raise NotFound(f"shortcode {code} not found")
        raise Unavailable(f"unexpected HTTP {response.status_code}")

    def _get(self, path: str) -> httpx.Response:
        try:
            return self._http.get(self._base_url + path)
        except httpx.TimeoutException as err:
            raise Unavailable("timeout") from err
        except httpx.HTTPError as err:
            raise Unavailable(type(err).__name__) from err

    def _is_not_found(self, response: httpx.Response) -> bool:
        if response.status_code == 404:
            return True
        return response.is_redirect and self._location_path(response).startswith(
            _NOT_FOUND_PATHS
        )

    @staticmethod
    def _location_path(response: httpx.Response) -> str:
        location = str(response.headers.get("Location", ""))
        return urllib.parse.urlsplit(location).path
