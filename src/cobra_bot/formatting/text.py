"""Text helpers: Discord markdown escaping, ID shortening, timestamps, Cobra links."""

import re
from datetime import datetime
from typing import Literal

from cobra_bot import messages

COBRA_BASE_URL = "https://tournaments.nullsignal.games"

# Characters with a markdown or markup meaning in Discord message text, including
# masked links ([text](url)), headings/lists (#, -, >), timestamps and mentions (<).
_MARKDOWN = re.compile(r"([\\*_~`|>#\-\[\]()<:])")
_WHITESPACE = re.compile(r"\s+")
_ORDERED_LIST = re.compile(r"^(\d+)\.(?=\s)", re.MULTILINE)

type TimestampStyle = Literal["t", "T", "d", "D", "f", "F", "R"]


def escape_markdown(text: str) -> str:
    """Make user-provided text (player names, identities) render literally.

    Whitespace runs, including newlines, collapse to one space so a name cannot
    break the line structure of an entry.
    """
    flat = _WHITESPACE.sub(" ", text).strip()
    return _MARKDOWN.sub(r"\\\1", flat)


def escape_ordered_list(text: str) -> str:
    """Stop `1. Alice` at a line start from rendering as a renumbered Discord list."""
    return _ORDERED_LIST.sub(r"\1\\.", text)


def short_identity(identity: str | None) -> str:
    """FR-08: the text before the first `:` ("Nuvem SA: Law of the Land" -> "Nuvem SA").

    Missing identities render as a placeholder.
    """
    if not identity or not identity.strip():
        return messages.UNKNOWN_IDENTITY
    return identity.split(":", 1)[0].strip() or messages.UNKNOWN_IDENTITY


def discord_timestamp(moment: datetime, style: TimestampStyle = "R") -> str:
    """`<t:UNIX:R>`: rendered by Discord in each reader's locale and time zone."""
    if moment.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return f"<t:{int(moment.timestamp())}:{style}>"


def tournament_url(tournament_id: int) -> str:
    return f"{COBRA_BASE_URL}/tournaments/{tournament_id}"


def standings_url(tournament_id: int) -> str:
    return f"{tournament_url(tournament_id)}/players/standings"
