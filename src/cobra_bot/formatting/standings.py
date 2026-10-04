"""Standings output (FR-06, FR-07; SPEC §9; embed format §2).

A table in an ```ansi code block, three lines per player and no column headings;
a blank line separates groups of players on the same match points:

```
 1. Alice           22
    Nuvem        1.821
    Arissana
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
    subtext,
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

MIN_RANK_WIDTH = 2
RANK_SUFFIX = ". "  # after the rank (S-1)
POINTS_WIDTH = 3  # right-aligned after the name, the space before them included
# S-1: the columns right of the indent; the SoS ends where the points do.
BODY_WIDTH = NAME_WIDTH + POINTS_WIDTH


def format_standings(
    t: Tournament, view: StandingsView, *, private: bool = False
) -> Document:
    if not view.started:
        title_line = messages.REGISTERED_PLAYERS
    elif view.after_round:
        title_line = messages.standings_header(view.after_round)
    else:
        title_line = messages.NO_COMPLETED_ROUNDS
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
        header=(
            heading(title_line),
            *(
                [subtext(messages.cut_note(view.cut, view.cut_size))]
                if view.cut
                else []
            ),
            data_line(t, private=private),
        ),
        entries=tuple(entries),
        footer=messages.standings_footer(view.after_round, len(view.players)),
    )


def rank_width(players: tuple[Player, ...]) -> int:
    """S-3: 2 columns, 3 once a rank reaches 100."""
    return max([MIN_RANK_WIDTH, *(len(str(p.rank)) for p in players)])


def standings_row(p: Player, width: int = MIN_RANK_WIDTH) -> str:
    """S-1: rank, name and points; the Corp ID and SoS; the Runner ID.

    A wider rank column takes its columns from the name, so a line never grows
    past 22 columns (S-3, C-5).
    """
    name_width = NAME_WIDTH - (width - MIN_RANK_WIDTH)
    body_width = BODY_WIDTH - (width - MIN_RANK_WIDTH)
    indent = " " * (width + len(RANK_SUFFIX))
    name = fit(code_text(p.name), name_width)
    corp = corp_label(p.corp_identity)
    sos = f"{p.sos:.3f}"
    sos_padding = " " * max(1, body_width - display_width(corp) - len(sos))
    return "\n".join(
        [
            f"{ansi.PRIMARY}{p.rank:>{width}}{RANK_SUFFIX}"
            f"{ansi.STRONG}{pad(name, name_width)}"
            f"{ansi.SCORE}{p.match_points:>{POINTS_WIDTH}}{RESET}",
            f"{indent}{identity(corp, ansi.CORP)}"
            f"{sos_padding}{ansi.SECONDARY}{sos}{RESET}",
            f"{indent}{identity(runner_label(p.runner_identity), ansi.RUNNER)}{RESET}",
        ]
    )
