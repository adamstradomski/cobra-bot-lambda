"""Player name search (SPEC §8)."""

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from cobra_bot.domain.models import Player

DEFAULT_LIMIT = 3

# Letters that do not decompose under NFKD, applied after casefold().
_EXTRA = str.maketrans({"ł": "l", "ø": "o", "đ": "d", "ß": "ss", "æ": "ae", "œ": "oe"})


@dataclass(frozen=True)
class SearchResult:
    matches: tuple[Player, ...]  # in rank order, at most `limit`
    more: int  # matching players beyond `matches`


def normalize(text: str) -> str:
    """Case- and diacritic-insensitive form: `Żółw` -> `zolw`, `Maëlig` -> `maelig`."""
    folded = text.casefold().translate(_EXTRA)
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def search_players(
    players: Iterable[Player], query: str, limit: int = DEFAULT_LIMIT
) -> SearchResult:
    needle = normalize(query).strip()
    if not needle:
        return SearchResult(matches=(), more=0)
    found = sorted(
        (p for p in players if needle in normalize(p.name)), key=lambda p: p.rank
    )
    return SearchResult(matches=tuple(found[:limit]), more=max(0, len(found) - limit))
