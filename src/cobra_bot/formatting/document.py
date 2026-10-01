"""A formatted reply before it is split into Discord embeds and messages."""

from dataclasses import dataclass

from cobra_bot import messages
from cobra_bot.domain.models import Tournament
from cobra_bot.formatting.text import discord_timestamp, escape_markdown


@dataclass(frozen=True)
class Document:
    title: str  # embed title: plain text, Discord does not render markdown there
    url: str  # title link, and the "full list on Cobra" link when entries are cut
    header: tuple[str, ...]  # first lines of the first embed
    entries: tuple[str, ...]  # atomic blocks (may span lines); never split


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


def player_name(t: Tournament, player_id: int | None) -> str:
    """Escaped display name for a player ID."""
    player = t.player(player_id) if player_id is not None else None
    return escape_markdown(player.name) if player else messages.UNKNOWN_PLAYER
