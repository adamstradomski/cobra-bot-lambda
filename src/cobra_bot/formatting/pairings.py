"""Pairings output (FR-03, FR-04, FR-05; SPEC §9; embed format §3).

A table in an ```ansi code block, one entry per table, a blank line between them,
no column headings. Each player line shows the points that player scored, so the
winner is recognisable without colours (C-6).

Single-sided, the Corp always first:

```
T1   3 Alice · Nuvem
     0 Bob · Zahya
```

Double-sided, a name line with the round total and a game line per player; the
left column is game 1, the right column game 2:

```
T1   3 Alice
      C Nuvem     0  R Arissana  3
     3 Bob
      R Zahya     3  C HB        0
```

Unreported points show `–`, intentional draws `ID`; a bye is one line,
`T5  BYE Carol`. A top-cut game is labelled with its game number (`G13`) and
shows `W` / `L` instead of points.
"""

from cobra_bot import messages
from cobra_bot.domain.models import Pairing, Player, Seat, Tournament
from cobra_bot.domain.rounds import PairingsView
from cobra_bot.formatting import ansi
from cobra_bot.formatting.ansi import RESET
from cobra_bot.formatting.document import (
    Document,
    Entry,
    data_line,
    heading,
    identity,
    player_name,
)
from cobra_bot.formatting.text import (
    corp_label,
    display_width,
    runner_label,
    tournament_url,
)

MIN_TABLE_WIDTH = 4  # "T12 " (P-3)
POINTS_WIDTH = 2  # right-aligned, then a space (P-2)
GAME_ID_WIDTH = 10  # the short ID in a double-sided game cell (DS-3)
GAME_GAP = "  "  # between the two game cells (DS-3)
SEPARATOR = " · "  # between a name and its ID (C-14)

type Points = tuple[str, str]  # points as shown, ANSI style of the player's name


def format_pairings(
    t: Tournament, view: PairingsView, *, private: bool = False
) -> Document:
    title_line = (
        messages.cut_pairings_header(view.cut_round, view.complete)
        if view.cut_round
        else messages.pairings_header(view.round_number, view.complete)
    )
    header = [heading(title_line), data_line(t, private=private)]
    ordered = sorted(view.pairings, key=lambda p: p.table)
    width = table_width(ordered)
    double_sided = any(p.double_sided for p in ordered)
    return Document(
        title=t.name,
        url=tournament_url(t.id),
        header=tuple(header),
        entries=tuple(Entry(pairing_rows(t, p, width), gap=True) for p in ordered),
        footer=messages.pairings_footer(view.round_number, len(ordered), double_sided),
    )


def table_width(pairings: list[Pairing]) -> int:
    """Width of the table-label column: the longest `T<n>` plus a space."""
    return max([MIN_TABLE_WIDTH, *(len(table_label(p)) + 1 for p in pairings)])


def table_label(pairing: Pairing) -> str:
    """`T12` for a table, `G12` for a top-cut game."""
    return f"{'G' if pairing.elimination else 'T'}{pairing.table}"


def pairing_rows(t: Tournament, pairing: Pairing, width: int = MIN_TABLE_WIDTH) -> str:
    label = table_label(pairing)
    if pairing.is_bye:
        # P-4: a bye shows no ID.
        (player_id,) = pairing.player_ids or (None,)
        return (
            f"{ansi.PRIMARY}{label:<{width}}{messages.BYE} "
            f"{player_name(t, player_id)}{RESET}"
        )
    s1, s2 = pairing.seat1, pairing.seat2
    if pairing.double_sided:
        return _double_sided(t, pairing, label, width)
    # Single-sided games always have roles (findings Q3); the Corp comes first.
    corp, runner = (s1, s2) if s1.role == "corp" else (s2, s1)
    if pairing.elimination:
        corp_points, runner_points = _results(corp.winner, runner.winner)
    else:
        corp_points, runner_points = _points(
            pairing, corp.combined_score, runner.combined_score
        )
    corp_id, runner_id = _corp_id(_player(t, corp)), _runner_id(_player(t, runner))
    return "\n".join(
        [
            _name_line(t, corp, label, width, corp_points)
            + f"{ansi.SECONDARY}{SEPARATOR}{identity(corp_id, ansi.CORP)}{RESET}",
            _name_line(t, runner, "", width, runner_points)
            + f"{ansi.SECONDARY}{SEPARATOR}{identity(runner_id, ansi.RUNNER)}{RESET}",
        ]
    )


def _double_sided(t: Tournament, pairing: Pairing, label: str, width: int) -> str:
    """DS-1–DS-5: seat 1 is the Corp in game 1 (findings Q3), so its game line
    reads `C … R …` and seat 2's reads `R … C …`; each column is one game."""
    s1, s2 = pairing.seat1, pairing.seat2
    points1, points2 = _points(pairing, _total(s1), _total(s2))
    p1, p2 = _player(t, s1), _player(t, s2)
    return "\n".join(
        [
            _name_line(t, s1, label, width, points1) + RESET,
            _game_line(
                width,
                _cell(messages.CORP_TAG, ansi.CORP, _corp_id(p1), s1.corp_score),
                _cell(
                    messages.RUNNER_TAG, ansi.RUNNER, _runner_id(p1), s1.runner_score
                ),
            ),
            _name_line(t, s2, "", width, points2) + RESET,
            _game_line(
                width,
                _cell(
                    messages.RUNNER_TAG, ansi.RUNNER, _runner_id(p2), s2.runner_score
                ),
                _cell(messages.CORP_TAG, ansi.CORP, _corp_id(p2), s2.corp_score),
            ),
        ]
    )


def _total(seat: Seat) -> int | None:
    """DS-4: the points of both games; None while neither game is reported."""
    if seat.corp_score is None and seat.runner_score is None:
        return None
    return (seat.corp_score or 0) + (seat.runner_score or 0)


def _points(
    pairing: Pairing, first: int | None, second: int | None
) -> tuple[Points, Points]:
    """P-2: each player's points; the player with more is bold, the one with fewer
    secondary; equal points, an intentional draw or no result leave both plain."""
    if pairing.intentional_draw:
        draw = (messages.INTENTIONAL_DRAW, ansi.PRIMARY)
        return draw, draw
    shown = (_shown(first), _shown(second))
    if first is None or second is None or first == second:
        return (shown[0], ansi.PRIMARY), (shown[1], ansi.PRIMARY)
    won = first > second
    return (
        (shown[0], ansi.STRONG if won else ansi.SECONDARY),
        (shown[1], ansi.SECONDARY if won else ansi.STRONG),
    )


def _results(first: bool | None, second: bool | None) -> tuple[Points, Points]:
    """A top-cut game: `W` bold for the winner, `L` secondary for the loser,
    `–` for both while unreported."""
    if not first and not second:
        unreported = (messages.NO_RESULT, ansi.PRIMARY)
        return unreported, unreported
    won, lost = (messages.WIN, ansi.STRONG), (messages.LOSS, ansi.SECONDARY)
    return (won, lost) if first else (lost, won)


def _shown(points: int | None) -> str:
    return messages.NO_RESULT if points is None else str(points)


def _name_line(
    t: Tournament, seat: Seat, label: str, width: int, points: Points
) -> str:
    """P-3, SS-2, DS-1: label or indent, points right-aligned in 2, the name."""
    shown, style = points
    return (
        f"{ansi.PRIMARY}{label:<{width}}"
        f"{ansi.SCORE}{shown:>{POINTS_WIDTH}} "
        f"{style}{player_name(t, seat.player_id)}"
    )


def _cell(tag: str, side_style: str, label: str, points: int | None) -> str:
    """DS-3: the side tag, the short ID padded to 10, the points of that game."""
    padding = " " * max(0, GAME_ID_WIDTH - display_width(label))
    return (
        f"{side_style}{tag} {identity(label, side_style)}{padding}"
        f"{ansi.SCORE}{_shown(points)}"
    )


def _game_line(width: int, game1: str, game2: str) -> str:
    return f"{' ' * (width + 2)}{game1}{ansi.PRIMARY}{GAME_GAP}{game2}{RESET}"


def _player(t: Tournament, seat: Seat) -> Player | None:
    return t.player(seat.player_id) if seat.player_id is not None else None


def _corp_id(player: Player | None) -> str:
    return corp_label(player.corp_identity if player else None)


def _runner_id(player: Player | None) -> str:
    return runner_label(player.runner_identity if player else None)
