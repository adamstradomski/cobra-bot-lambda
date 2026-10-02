"""Standings output (FR-06, FR-07; SPEC §9; embed format S-1–S-5).

A table in an ```ansi code block; a blank line separates groups of players on the
same match points:

```
 #  Player          Pts  SoS    Corp      Runner
───────────────────────────────────────────────────
 1  Alice            22  1.821  Nuvem     Arissana
```
"""

from cobra_bot import messages
from cobra_bot.domain.models import Player, Tournament
from cobra_bot.domain.rounds import StandingsView
from cobra_bot.formatting import ansi
from cobra_bot.formatting.ansi import RESET, sgr
from cobra_bot.formatting.document import Document, Entry, data_line, heading
from cobra_bot.formatting.text import (
    code_text,
    corp_label,
    display_width,
    fit,
    pad,
    runner_label,
    standings_url,
)

NAME_WIDTH = 16  # no separator: points are right-aligned in 3 after it
CORP_WIDTH = 10
MIN_RANK_WIDTH = 2
RULE_EXTRA = 3  # the rule is 3 columns wider than the headings (S-1)


def format_standings(
    t: Tournament, view: StandingsView, *, private: bool = False
) -> Document:
    title_line = (
        messages.standings_header(view.after_round)
        if view.after_round
        else messages.NO_COMPLETED_ROUNDS
    )
    width = rank_width(view.players)
    entries = []
    previous: Player | None = None
    for p in view.players:
        gap = previous is not None and p.match_points != previous.match_points
        entries.append(Entry(standings_row(p, width), gap=gap))
        previous = p
    return Document(
        title=t.name,
        url=standings_url(t.id),
        header=(heading(title_line), data_line(t, private=private)),
        columns=standings_columns(width),
        entries=tuple(entries),
        footer=messages.standings_footer(view.after_round, len(view.players)),
    )


def rank_width(players: tuple[Player, ...]) -> int:
    return max([MIN_RANK_WIDTH, *(len(str(p.rank)) for p in players)])


def standings_columns(width: int = MIN_RANK_WIDTH) -> tuple[str, str]:
    heading_row = (
        f"{messages.RANK:>{width}}  {pad(messages.PLAYER, NAME_WIDTH)}"
        f"{messages.POINTS:>3}  {messages.SOS:<5}  "
        f"{pad(messages.CORP, CORP_WIDTH)}{messages.RUNNER}"
    )
    return (
        f"{sgr(ansi.HEADING)}{heading_row}{RESET}",
        ansi.rule(display_width(heading_row) + RULE_EXTRA),
    )


def standings_row(p: Player, width: int = MIN_RANK_WIDTH) -> str:
    name = fit(code_text(p.name), NAME_WIDTH)
    return (
        f"{sgr(ansi.MUTED)}{p.rank:>{width}}  "
        f"{sgr(ansi.STRONG)}{pad(name, NAME_WIDTH)}"
        f"{sgr(ansi.SCORE)}{p.match_points:>3}  "
        f"{sgr(ansi.MUTED)}{p.sos:.3f}  "
        f"{sgr(ansi.CORP)}{pad(corp_label(p.corp_identity), CORP_WIDTH)}"
        f"{sgr(ansi.RUNNER)}{runner_label(p.runner_identity)}{RESET}"
    )
