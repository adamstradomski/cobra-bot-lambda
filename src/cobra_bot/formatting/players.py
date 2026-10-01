"""Player cards for `/cobra player` (FR-09, FR-10; SPEC §9).

Each card: the player's standings line, then their pairing in the latest Swiss
round (or bye). A note is added while a top cut is in progress.
"""

from cobra_bot import messages
from cobra_bot.domain.models import Player, Tournament
from cobra_bot.domain.rounds import swiss_round_numbers, top_cut_in_progress
from cobra_bot.domain.search import SearchResult
from cobra_bot.formatting.document import Document, data_line
from cobra_bot.formatting.pairings import pairing_entry
from cobra_bot.formatting.standings import standings_entry
from cobra_bot.formatting.text import escape_markdown, tournament_url


def format_player_cards(
    t: Tournament, result: SearchResult, query: str, *, private: bool = False
) -> Document:
    header = [messages.players_header(escape_markdown(query))]
    if top_cut_in_progress(t):
        header.append(messages.TOP_CUT_IN_PROGRESS)
    header.append(data_line(t, private=private))
    entries = [player_card(t, p) for p in result.matches]
    if not entries:
        entries.append(messages.NO_PLAYERS_MATCH)
    if result.more:
        entries.append(messages.more_players_matched(result.more))
    return Document(
        title=t.name,
        url=tournament_url(t.id),
        header=tuple(header),
        entries=tuple(entries),
    )


def player_card(t: Tournament, player: Player) -> str:
    lines = [standings_entry(player)]
    swiss = swiss_round_numbers(t)
    if swiss:
        number = swiss[-1]
        pairing = next(
            (p for p in t.rounds[number - 1] if player.id in p.player_ids), None
        )
        shown = pairing_entry(t, pairing) if pairing else messages.NOT_PAIRED
        lines.append(messages.player_round(number, shown))
    return "\n".join(lines)
