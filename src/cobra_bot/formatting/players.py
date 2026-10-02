"""Player cards for `/cobra player` (FR-09, FR-10; SPEC §9).

Each card, in the ```ansi code block: the player's standings row, then their
pairing in the latest Swiss round (or bye). A blank line separates the cards. A
note is added while a top cut is in progress.
"""

from cobra_bot import messages
from cobra_bot.domain.models import Player, Tournament
from cobra_bot.domain.rounds import swiss_round_numbers, top_cut_in_progress
from cobra_bot.domain.search import SearchResult
from cobra_bot.formatting import ansi
from cobra_bot.formatting.ansi import RESET, sgr
from cobra_bot.formatting.document import (
    Document,
    Entry,
    data_line,
    heading,
    subtext,
)
from cobra_bot.formatting.pairings import pairing_rows, table_width
from cobra_bot.formatting.standings import rank_width, standings_row
from cobra_bot.formatting.text import escape_markdown, tournament_url


def format_player_cards(
    t: Tournament, result: SearchResult, query: str, *, private: bool = False
) -> Document:
    header = [heading(messages.players_header(escape_markdown(query)))]
    if top_cut_in_progress(t):
        header.append(subtext(messages.TOP_CUT_IN_PROGRESS))
    header.append(data_line(t, private=private))
    notes = []
    if not result.matches:
        notes.append(messages.NO_PLAYERS_MATCH)
    if result.more:
        notes.append(messages.more_players_matched(result.more))
    return Document(
        title=t.name,
        url=tournament_url(t.id),
        header=tuple(header),
        entries=tuple(Entry(player_card(t, p), gap=True) for p in result.matches),
        notes=tuple(notes),
        footer=messages.PLAYERS_FOOTER,
    )


def player_card(t: Tournament, player: Player) -> str:
    lines = [standings_row(player, rank_width((player,)))]
    swiss = swiss_round_numbers(t)
    if swiss:
        number = swiss[-1]
        pairings = t.rounds[number - 1]
        pairing = next((p for p in pairings if player.id in p.player_ids), None)
        if pairing is None:
            lines.append(_muted(messages.player_not_paired(number)))
        else:
            lines.append(_muted(messages.player_round(number)))
            lines.append(pairing_rows(t, pairing, table_width(list(pairings))))
    return "\n".join(lines)


def _muted(text: str) -> str:
    return f"{sgr(ansi.MUTED)}{text}{RESET}"
