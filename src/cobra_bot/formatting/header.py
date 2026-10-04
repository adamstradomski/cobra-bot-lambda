"""The text around a reply's image (docs/spec/output.md): the embed title and its Cobra
link, the header lines above the image and the notes below it."""

from dataclasses import dataclass

from cobra_bot import messages
from cobra_bot.domain.bracket import TopCutView
from cobra_bot.domain.models import Tournament
from cobra_bot.domain.rounds import PairingsView, StandingsView
from cobra_bot.domain.search import MAX_NAMES, NamesResult
from cobra_bot.formatting.text import (
    ELLIPSIS,
    discord_timestamp,
    escape_markdown,
    standings_url,
    tournament_url,
)

TITLE_CHARS = 256  # Discord rejects a longer embed title


@dataclass(frozen=True)
class Header:
    title: str  # embed title: plain text, Discord does not render markdown there
    url: str  # title link, and the "full list on Cobra" link when pages are cut
    lines: tuple[str, ...]  # markdown lines above the image
    notes: tuple[str, ...] = ()  # markdown lines below the header


def title(t: Tournament) -> str:
    """The tournament name as the embed title, cut to Discord's limit."""
    if len(t.name) <= TITLE_CHARS:
        return t.name
    return t.name[: TITLE_CHARS - len(ELLIPSIS)] + ELLIPSIS


def data_line(t: Tournament, *, private: bool = False) -> str:
    """When the data was fetched, and why it is stale if it is (FR-21;
    docs/spec/cache.md).

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


def standings(t: Tournament, view: StandingsView, *, private: bool = False) -> Header:
    """After which round; the top cut's state once Swiss is over (FR-22)."""
    if not view.started:
        title_line = messages.REGISTERED_PLAYERS
    elif view.after_round:
        title_line = messages.standings_header(view.after_round)
    else:
        title_line = messages.NO_COMPLETED_ROUNDS
    cut = [subtext(messages.cut_note(view.cut, view.cut_size))] if view.cut else []
    return Header(
        title=title(t),
        url=standings_url(t.id),
        lines=(heading(title_line), *cut, data_line(t, private=private)),
    )


def pairings(t: Tournament, view: PairingsView, *, private: bool = False) -> Header:
    """Which round, Swiss or top cut, and whether it is complete (FR-03)."""
    title_line = (
        messages.cut_pairings_header(view.cut_round, view.complete)
        if view.cut_round
        else messages.pairings_header(view.round_number, view.complete)
    )
    return Header(
        title=title(t),
        url=tournament_url(t.id),
        lines=(heading(title_line), data_line(t, private=private)),
    )


def top_cut(t: Tournament, view: TopCutView, *, private: bool = False) -> Header:
    return Header(
        title=title(t),
        url=standings_url(t.id),
        lines=(
            heading(messages.top_cut_header(view.size, view.status)),
            data_line(t, private=private),
        ),
    )


def players(
    t: Tournament, result: NamesResult, query: str, *, private: bool = False
) -> Header:
    """The query, escaped; notes for names that matched nobody or more players
    than shown (FR-09, FR-10)."""
    return Header(
        title=title(t),
        url=tournament_url(t.id),
        lines=(
            heading(messages.players_header(escape_markdown(query))),
            data_line(t, private=private),
        ),
        notes=tuple(_player_notes(result)),
    )


def _player_notes(result: NamesResult) -> list[str]:
    """One name: "No players match." or how many more matched. Several: a note
    per name that matched nobody or more players than shown, naming it."""
    if len(result.names) <= 1:
        notes = [] if result.matches else [messages.NO_PLAYERS_MATCH]
        more = result.names[0].more if result.names else 0
        if more:
            notes.append(messages.more_players_matched(more))
    else:
        notes = []
        for name in result.names:
            shown = escape_markdown(name.name)
            if not name.found:
                notes.append(messages.no_player_named(shown))
            elif name.more:
                notes.append(messages.more_players_named(name.more, shown))
    if result.skipped:
        notes.append(messages.names_skipped(result.skipped, MAX_NAMES))
    return notes
