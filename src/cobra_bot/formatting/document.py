"""A formatted reply before it is split into Discord embeds and messages.

The reply is a table in an ```ansi code block (SPEC §9): markdown header lines
above it, optional markdown notes below it, and a legend in the embed footer.
"""

from dataclasses import dataclass

from cobra_bot import messages
from cobra_bot.domain.models import Tournament
from cobra_bot.formatting import ansi
from cobra_bot.formatting.text import NAME_WIDTH, code_text, discord_timestamp, fit

EMBED_COLOR = 0xE0B23A


@dataclass(frozen=True)
class Entry:
    text: str  # table lines with ANSI colours; one atomic block, never split
    gap: bool = False  # a blank line before it, unless it starts a code block


@dataclass(frozen=True)
class Document:
    title: str  # embed title: plain text, Discord does not render markdown there
    url: str  # title link, and the "full list on Cobra" link when entries are cut
    header: tuple[str, ...]  # markdown lines above the table
    entries: tuple[Entry, ...]  # table rows
    notes: tuple[str, ...] = ()  # markdown lines below the table
    footer: str = ""  # plain-text legend


def data_line(t: Tournament, *, private: bool = False) -> str:
    """When the data was fetched, and why it is stale if it is (SPEC §7, FR-21).

    Lives in the description, not the embed footer: footers do not render
    Discord timestamps.
    """
    timestamp = discord_timestamp(t.fetched_at)
    if not t.stale:
        return messages.data_from(timestamp)
    if private:
        return messages.stale_tournament_private(timestamp)
    return messages.stale_cobra_unavailable(timestamp)


def heading(text: str) -> str:
    """The state line, in bold."""
    return f"**{text}**"


def subtext(text: str) -> str:
    """A small grey note line."""
    return f"-# {text}"


def player_name(t: Tournament, player_id: int | None) -> str:
    """Display name for a player ID, safe inside a code block, cut to 15 columns
    (C-7)."""
    player = t.player(player_id) if player_id is not None else None
    return (
        fit(code_text(player.name), NAME_WIDTH) if player else messages.UNKNOWN_PLAYER
    )


def identity(label: str, side_style: str) -> str:
    """A short ID in its side's colour; an unknown ID in the secondary colour (A-4)."""
    style = ansi.SECONDARY if label == messages.UNKNOWN_IDENTITY else side_style
    return f"{style}{label}"
