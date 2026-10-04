"""Player name search (docs/spec/domain.md)."""

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


# --- several names (FR-09) -------------------------------------------------------

MAX_NAMES = 10
NAME_SEPARATORS = ",;"


@dataclass(frozen=True)
class NameResult:
    name: str  # as typed, trimmed
    found: int  # players matching this name, shown or not
    more: int  # of them, beyond `DEFAULT_LIMIT`


@dataclass(frozen=True)
class NamesResult:
    matches: tuple[Player, ...]  # every name's matches, once each, in rank order
    names: tuple[NameResult, ...]
    skipped: int  # names past `MAX_NAMES`, not searched


def split_names(query: str) -> list[str]:
    """`Alice, Bob; Carol` -> the names, trimmed, empty and repeated ones (by
    `normalize`) dropped."""
    for separator in NAME_SEPARATORS[1:]:
        query = query.replace(separator, NAME_SEPARATORS[0])
    names: list[str] = []
    seen: set[str] = set()
    for part in query.split(NAME_SEPARATORS[0]):
        name = " ".join(part.split())
        if name and normalize(name) not in seen:
            seen.add(normalize(name))
            names.append(name)
    return names


def search_names(
    players: Iterable[Player], query: str, limit: int = DEFAULT_LIMIT
) -> NamesResult:
    """Search each comma-separated name like `search_players`, at most
    `MAX_NAMES` of them, so a group of friends can be followed in one reply."""
    roster = tuple(players)
    names = split_names(query)
    searched, skipped = names[:MAX_NAMES], max(0, len(names) - MAX_NAMES)
    results = [(name, search_players(roster, name, limit)) for name in searched]
    found: dict[int, Player] = {}
    for _, result in results:
        for player in result.matches:
            found.setdefault(player.id, player)
    return NamesResult(
        matches=tuple(sorted(found.values(), key=lambda p: p.rank)),
        names=tuple(
            NameResult(name, len(r.matches) + r.more, r.more) for name, r in results
        ),
        skipped=skipped,
    )
