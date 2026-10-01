"""Standings output (FR-06, FR-07; SPEC §9).

`1. Alice — 22 pts — SoS 1.821 — Nuvem SA / Arissana`
"""

from cobra_bot import messages
from cobra_bot.domain.models import Player, Tournament
from cobra_bot.domain.rounds import StandingsView
from cobra_bot.formatting.document import Document, data_line
from cobra_bot.formatting.text import (
    escape_markdown,
    escape_ordered_list,
    short_identity,
    standings_url,
)


def format_standings(
    t: Tournament, view: StandingsView, *, private: bool = False
) -> Document:
    title_line = (
        messages.standings_header(view.after_round)
        if view.after_round
        else messages.NO_COMPLETED_ROUNDS
    )
    return Document(
        title=t.name,
        url=standings_url(t.id),
        header=(title_line, data_line(t, private=private)),
        entries=tuple(standings_entry(p) for p in view.players),
    )


def standings_entry(p: Player) -> str:
    line = (
        f"{p.rank}. {escape_markdown(p.name)} — {p.match_points} {messages.POINTS}"
        f" — {messages.SOS} {p.sos:.3f}"
        f" — {short_identity(p.corp_identity)} / {short_identity(p.runner_identity)}"
    )
    return escape_ordered_list(line)
