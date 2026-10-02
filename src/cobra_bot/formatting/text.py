"""Text helpers: Discord markdown escaping, code-block text and column widths, ID
labels, timestamps, Cobra links."""

import logging
import re
import unicodedata
from datetime import datetime
from functools import cache
from typing import Literal

from cobra_bot import messages
from cobra_bot.formatting.identities import CORP_SHORT_NAMES, RUNNER_SHORT_NAMES

log = logging.getLogger(__name__)

COBRA_BASE_URL = "https://tournaments.nullsignal.games"

# Characters with a markdown or markup meaning in Discord message text, including
# masked links ([text](url)), headings/lists (#, -, >), timestamps and mentions (<).
_MARKDOWN = re.compile(r"([\\*_~`|>#\-\[\]()<:])")
_WHITESPACE = re.compile(r"\s+")
# A nickname in straight or curly quotes: René "Loup" Arcemont -> Loup.
_NICKNAME = re.compile(r"[\"“]([^\"“”]+)[\"”]")
# Stands in for a backtick, which would close the code block around a name (C-7).
_BACKTICK_STANDIN = "'"
ELLIPSIS = "…"
ID_WIDTH = 9  # columns for a short ID (A-1)
NAME_WIDTH = 15  # columns for a player name (C-7)

type TimestampStyle = Literal["t", "T", "d", "D", "f", "F", "R"]


def escape_markdown(text: str) -> str:
    """Make user-provided text (e.g. the search query) render literally.

    Whitespace runs, including newlines, collapse to one space so the text cannot
    break the line structure around it.
    """
    flat = _WHITESPACE.sub(" ", text).strip()
    return _MARKDOWN.sub(r"\\\1", flat)


def code_text(text: str) -> str:
    """Make user-provided text (player names, IDs) safe inside an ```ansi block.

    Markdown does not render there, so nothing is escaped; but a backtick could
    close the block and a control character (e.g. ESC) could inject colours, so
    backticks become `'` and control and format characters are dropped.
    Whitespace runs collapse to one space, and the text is NFC-normalised.
    """
    flat = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()
    kept = "".join(c for c in flat if not unicodedata.category(c).startswith("C"))
    return kept.replace("`", _BACKTICK_STANDIN)


def display_width(text: str) -> int:
    """Columns `text` takes in a monospaced font (C-5).

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


def pad(text: str, width: int) -> str:
    """Left-align `text` in `width` columns (by display width, not `len`)."""
    return text + " " * max(0, width - display_width(text))


def short_identity(identity: str | None) -> str:
    """A-5: the text before the first `:` ("Nuvem SA: Law of the Land" -> "Nuvem SA").

    Missing identities render as a placeholder (A-4).
    """
    if not identity or not identity.strip():
        return messages.UNKNOWN_IDENTITY
    return identity.split(":", 1)[0].strip() or messages.UNKNOWN_IDENTITY


@cache
def corp_label(identity: str | None) -> str:
    """FR-08, A-1–A-2: the short Corp ID from the map, else the name before `:`,
    cut to 9 columns. A missing entry is logged once per ID and process."""
    short = short_identity(identity)
    if short == messages.UNKNOWN_IDENTITY:
        return short
    if short in CORP_SHORT_NAMES:
        return CORP_SHORT_NAMES[short]
    log.warning("corp ID missing from the short-name map: %s", short)
    return fit(code_text(short), ID_WIDTH) or messages.UNKNOWN_IDENTITY


@cache
def runner_label(identity: str | None) -> str:
    """FR-08, A-1–A-2: the short Runner ID from the map, else the quoted nickname
    or the first word, cut to 9 columns. A missing entry is logged once per ID and
    process."""
    short = short_identity(identity)
    if short == messages.UNKNOWN_IDENTITY:
        return short
    if short in RUNNER_SHORT_NAMES:
        return RUNNER_SHORT_NAMES[short]
    log.warning("runner ID missing from the short-name map: %s", short)
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
