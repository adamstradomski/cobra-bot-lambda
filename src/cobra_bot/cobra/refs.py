"""Parse the `tournament` command option into a Cobra reference (docs/spec/cobra.md).

Accepted:
- a numeric ID: `4909`;
- a Cobra URL with an ID: `https://tournaments.nullsignal.games/tournaments/4977/...`;
- a shortcode, bare or as a Cobra URL: `QNSF`, `https://tournaments.nullsignal.games/QNSF`
  (docs/spec/cobra.md: 4 letters or digits, case-insensitive; an all-digit
  input is always an ID).
Surrounding whitespace and Discord's `<...>` link-suppression brackets are ignored.
"""

import re
import urllib.parse
from dataclasses import dataclass
from typing import NoReturn

COBRA_HOST = "tournaments.nullsignal.games"
MAX_ID_DIGITS = 9

_ID = re.compile(rf"[0-9]{{1,{MAX_ID_DIGITS}}}")
_SHORTCODE = re.compile(r"[A-Za-z0-9]{4}")


@dataclass(frozen=True)
class TournamentId:
    id: int


@dataclass(frozen=True)
class Shortcode:
    code: str  # upper case


type TournamentRef = TournamentId | Shortcode


class InvalidTournamentRef(ValueError):
    """The input is not a tournament ID, Cobra URL or shortcode."""


def parse_ref(text: str) -> TournamentRef:
    value = text.strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    if "/" in value or ":" in value:
        return _parse_url(value)
    return _parse_token(value) or _invalid(text)


def _parse_token(token: str) -> TournamentRef | None:
    if _ID.fullmatch(token):
        number = int(token)
        return TournamentId(number) if number > 0 else None
    if _SHORTCODE.fullmatch(token):
        return Shortcode(token.upper())
    return None


def _parse_url(value: str) -> TournamentRef:
    parts = urllib.parse.urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or host != COBRA_HOST:
        _invalid(value)
    segments = [s for s in parts.path.split("/") if s]
    match segments:
        case ["tournaments", tid, *_] if _ID.fullmatch(tid):
            ref = _parse_token(tid)
        case [code] if _SHORTCODE.fullmatch(code) and not code.isdigit():
            ref = Shortcode(code.upper())
        case _:
            ref = None
    return ref or _invalid(value)


def _invalid(value: str) -> NoReturn:
    raise InvalidTournamentRef(
        f"not a tournament ID, Cobra URL or shortcode: {value!r}"
    )
