"""Text helpers: Discord markdown escaping, safe player text, widths, ID labels,
timestamps, Cobra links."""

import logging
import re
import unicodedata
from datetime import datetime
from functools import cache
from typing import Literal

from cobra_bot import messages
from cobra_bot.formatting.identities import (
    CORP_PREFIX_SHORT_NAMES,
    CORP_SHORT_NAMES,
    RUNNER_PREFIX_SHORT_NAMES,
    RUNNER_SHORT_NAMES,
)

log = logging.getLogger(__name__)

COBRA_BASE_URL = "https://tournaments.nullsignal.games"

# Characters with a markdown or markup meaning in Discord message text, including
# masked links ([text](url)), headings/lists (#, -, >), timestamps and mentions (<).
_MARKDOWN = re.compile(r"([\\*_~`|>#\-\[\]()<:])")
_WHITESPACE = re.compile(r"\s+")
# A nickname in straight or curly quotes: René "Loup" Arcemont -> Loup.
_NICKNAME = re.compile(r"[\"“]([^\"“”]+)[\"”]")
# Stands in for a backtick, so a name cannot close a code block or inline code.
_BACKTICK_STANDIN = "'"
ELLIPSIS = "…"
ID_WIDTH = 9  # columns for a short ID (FR-08)

type TimestampStyle = Literal["t", "T", "d", "D", "f", "F", "R"]


def escape_markdown(text: str) -> str:
    """Make user-provided text (e.g. the search query) render literally.

    Whitespace runs, including newlines, collapse to one space so the text cannot
    break the line structure around it.
    """
    flat = _WHITESPACE.sub(" ", text).strip()
    return _MARKDOWN.sub(r"\\\1", flat)


def code_text(text: str) -> str:
    """Make user-provided text (player names, IDs) safe to draw in an image.

    Nothing is escaped, since images do not render markdown; backticks become
    `'`, control and format characters (e.g. ESC) are dropped, whitespace runs
    collapse to one space, and the text is NFC-normalised.
    """
    flat = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()
    kept = "".join(c for c in flat if not unicodedata.category(c).startswith("C"))
    return kept.replace("`", _BACKTICK_STANDIN)


def display_width(text: str) -> int:
    """Columns `text` takes in a monospaced font.

    Combining marks take none; wide and full-width characters (CJK, most emoji)
    take two; everything else, including letters with diacritics, one.
    """
    return sum(_char_width(c) for c in text)


def _char_width(c: str) -> int:
    if unicodedata.combining(c) or unicodedata.category(c) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1


def fit(text: str, width: int) -> str:
    """Cut `text` to at most `width` columns, ending in `…` when cut."""
    if display_width(text) <= width:
        return text
    kept, used = [], 0
    for c in text:
        w = _char_width(c)
        if used + w > width - 1:
            break
        kept.append(c)
        used += w
    return "".join(kept) + ELLIPSIS


def short_identity(identity: str | None) -> str:
    """The text before the first `:` ("Nuvem SA: Law of the Land" -> "Nuvem SA").

    Missing identities render as a placeholder.
    """
    if not identity or not identity.strip():
        return messages.UNKNOWN_IDENTITY
    return identity.split(":", 1)[0].strip() or messages.UNKNOWN_IDENTITY


def _full_identity(identity: str) -> str:
    """The whole ID as the map's full-title keys are written (NFC)."""
    return unicodedata.normalize("NFC", identity).strip()


@cache
def corp_label(identity: str | None) -> str:
    """FR-08: the short Corp ID from the map (keyed by the whole ID),
    else its prefix's short name (`Haas-Bioroid` -> `HB`), else the name
    before `:`, cut to 9 columns. A missing entry is logged once per ID and
    process."""
    short = short_identity(identity)
    if short == messages.UNKNOWN_IDENTITY or identity is None:
        return short
    full = _full_identity(identity)
    if full in CORP_SHORT_NAMES:
        return CORP_SHORT_NAMES[full]
    log.warning("corp ID missing from the short-name map: %s", full)
    if short in CORP_PREFIX_SHORT_NAMES:
        return CORP_PREFIX_SHORT_NAMES[short]
    return fit(code_text(short), ID_WIDTH) or messages.UNKNOWN_IDENTITY


@cache
def runner_label(identity: str | None) -> str:
    """FR-08: the short Runner ID from the map (keyed by the whole ID),
    else its prefix's short name, else the quoted
    nickname or the first word of the name before `:`, cut to 9 columns. A
    missing entry is logged once per ID and process."""
    short = short_identity(identity)
    if short == messages.UNKNOWN_IDENTITY or identity is None:
        return short
    full = _full_identity(identity)
    if full in RUNNER_SHORT_NAMES:
        return RUNNER_SHORT_NAMES[full]
    log.warning("runner ID missing from the short-name map: %s", full)
    if short in RUNNER_PREFIX_SHORT_NAMES:
        return RUNNER_PREFIX_SHORT_NAMES[short]
    safe = code_text(short)
    nickname = _NICKNAME.search(safe)
    if nickname and nickname.group(1).strip():
        name = nickname.group(1).strip()
    else:
        name = safe.split(" ")[0].rstrip(",")
    return fit(name, ID_WIDTH) or messages.UNKNOWN_IDENTITY


def discord_timestamp(moment: datetime, style: TimestampStyle = "R") -> str:
    """`<t:UNIX:R>`: rendered by Discord in each reader's locale and time zone."""
    if moment.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return f"<t:{int(moment.timestamp())}:{style}>"


def tournament_url(tournament_id: int) -> str:
    return f"{COBRA_BASE_URL}/tournaments/{tournament_id}"


def standings_url(tournament_id: int) -> str:
    return f"{tournament_url(tournament_id)}/players/standings"


def bracket_url(tournament_id: int) -> str:
    return f"{tournament_url(tournament_id)}/bracket"
