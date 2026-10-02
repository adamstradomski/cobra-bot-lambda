"""Standings output (FR-06, FR-07; SPEC §9; embed format §2).

A table in an ```ansi code block, two lines per player; a blank line separates
groups of players on the same match points:

```
 # Player          Pts  SoS
─────────────────────────────
 1 Alice            22  1.821
   Nuvem · Arissana
```
"""

from cobra_bot import messages
from cobra_bot.domain.models import Player, Tournament
from cobra_bot.domain.rounds import StandingsView
from cobra_bot.formatting import ansi
from cobra_bot.formatting.ansi import RESET
from cobra_bot.formatting.document import (
    Document,
    Entry,
    data_line,
    heading,
    identity,
)
from cobra_bot.formatting.text import (
    NAME_WIDTH,
    code_text,
    corp_label,
    display_width,
    fit,
    pad,
    runner_label,
    standings_url,
)

NAME_COLUMN = NAME_WIDTH + 1  # points are right-aligned in 3 after it (S-1)
MIN_RANK_WIDTH = 2
RULE_EXTRA = 2  # the rule is 2 columns wider than the header (S-2)
SEPARATOR = " · "


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
    """S-3: 2 columns, 3 once a rank reaches 100."""
    return max([MIN_RANK_WIDTH, *(len(str(p.rank)) for p in players)])


def standings_columns(width: int = MIN_RANK_WIDTH) -> tuple[str, str]:
    header = (
        f"{messages.RANK:>{width}} {pad(messages.PLAYER, NAME_COLUMN)}"
        f"{messages.POINTS:>3}  {messages.SOS}"
    )
    return (
        f"{ansi.SECONDARY}{header}{RESET}",
        ansi.rule(display_width(header) + RULE_EXTRA),
    )


def standings_row(p: Player, width: int = MIN_RANK_WIDTH) -> str:
    """S-1: rank, name, points and SoS; then the Corp and Runner IDs."""
    name = fit(code_text(p.name), NAME_WIDTH)
    result = (
        f"{ansi.PRIMARY}{p.rank:>{width}} "
        f"{ansi.STRONG}{pad(name, NAME_COLUMN)}"
        f"{ansi.SCORE}{p.match_points:>3}  "
        f"{ansi.SECONDARY}{p.sos:.3f}{RESET}"
    )
    ids = (
        f"{' ' * (width + 1)}{identity(corp_label(p.corp_identity), ansi.CORP)}"
        f"{ansi.SECONDARY}{SEPARATOR}"
        f"{identity(runner_label(p.runner_identity), ansi.RUNNER)}{RESET}"
    )
    return f"{result}\n{ids}"
