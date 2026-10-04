"""Player cards for `/cobra player` (FR-09, FR-10; SPEC §9).

Each card, in the ```ansi code block: the player's standings entry, then their
pairing in the latest round, Swiss or top cut (or bye). A blank line separates
the cards.
"""

from cobra_bot import messages
from cobra_bot.domain.models import Player, Tournament
from cobra_bot.domain.search import MAX_NAMES, NamesResult
from cobra_bot.formatting import ansi
from cobra_bot.formatting.ansi import RESET
from cobra_bot.formatting.document import (
    Document,
    Entry,
    data_line,
    heading,
)
from cobra_bot.formatting.pairings import pairing_rows, table_width
from cobra_bot.formatting.standings import rank_width, standings_row
from cobra_bot.formatting.text import escape_markdown, tournament_url


def format_player_cards(
    t: Tournament, result: NamesResult, query: str, *, private: bool = False
) -> Document:
    header = [
        heading(messages.players_header(escape_markdown(query))),
        data_line(t, private=private),
    ]
    notes = _notes(result)
    return Document(
        title=t.name,
        url=tournament_url(t.id),
        header=tuple(header),
        entries=tuple(Entry(player_card(t, p), gap=True) for p in result.matches),
        notes=tuple(notes),
        footer=messages.PLAYERS_FOOTER,
    )


def _notes(result: NamesResult) -> list[str]:
    """One name: as before. Several: a note per name that matched nobody or
    more players than shown, naming it."""
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


def player_card(t: Tournament, player: Player) -> str:
    lines = [standings_row(player, rank_width((player,)))]
    if t.rounds:
        number = len(t.rounds)
        pairings = t.rounds[number - 1]
        pairing = next((p for p in pairings if player.id in p.player_ids), None)
        if pairing is None:
            lines.append(_muted(messages.player_not_paired(number)))
        else:
            lines.append(_muted(messages.player_round(number)))
            lines.append(pairing_rows(t, pairing, table_width(list(pairings))))
    return "\n".join(lines)


def _muted(text: str) -> str:
    return f"{ansi.SECONDARY}{text}{RESET}"
