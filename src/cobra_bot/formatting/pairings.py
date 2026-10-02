"""Pairings output (FR-03, FR-04, FR-05; SPEC §9; embed format P-1–P-10).

A table in an ```ansi code block, Corp on the left, Runner on the right, the score
from the Corp side; the winner in bold white, the loser grey:

```
T   Corp            Score Runner
────────────────────────────────────────────
T1  Alice            3–0  Bob
    Nuvem                 Arissana
```

Unreported results show `vs`, intentional draws `ID`, byes `BYE` in the score
column. A double-sided pairing shows the combined score, then each game in the
form above, marked `↳`.
"""

from cobra_bot import messages
from cobra_bot.domain.models import Pairing, Player, Seat, Tournament
from cobra_bot.domain.rounds import PairingsView
from cobra_bot.formatting import ansi
from cobra_bot.formatting.ansi import RESET, sgr
from cobra_bot.formatting.document import (
    Document,
    Entry,
    data_line,
    heading,
    player_name,
    subtext,
)
from cobra_bot.formatting.text import (
    corp_label,
    fit,
    pad,
    runner_label,
    tournament_url,
)

NAME_WIDTH = 16  # no separator: the score is right-aligned in 4 after it
SCORE_WIDTH = 4  # right-aligned, then two spaces (P-1)
ID_LINE_WIDTH = NAME_WIDTH + SCORE_WIDTH + 2  # Corp ID column, under the names
MIN_TABLE_WIDTH = 4  # "T12 "
RULE_WIDTH_AFTER_TABLE = 40  # the rule under the headings, beyond the label
GAME_MARK = "↳"

type Side = tuple[Seat, int | None]  # a seat and its score in the game shown
type Named = tuple[str, str]  # display name, ANSI style


def format_pairings(
    t: Tournament, view: PairingsView, *, private: bool = False
) -> Document:
    header = [heading(messages.pairings_header(view.round_number, view.complete))]
    if view.top_cut_in_progress:
        header.append(subtext(messages.TOP_CUT_IN_PROGRESS))
    header.append(data_line(t, private=private))
    ordered = sorted(view.pairings, key=lambda p: p.table)
    width = table_width(ordered)
    return Document(
        title=t.name,
        url=tournament_url(t.id),
        header=tuple(header),
        columns=pairings_columns(width),
        entries=tuple(Entry(pairing_rows(t, p, width)) for p in ordered),
        footer=messages.pairings_footer(view.round_number, len(ordered)),
    )


def table_width(pairings: list[Pairing]) -> int:
    """Width of the table-label column: the longest `T<n>` plus a space."""
    return max([MIN_TABLE_WIDTH, *(len(f"T{p.table}") + 1 for p in pairings)])


def pairings_columns(width: int = MIN_TABLE_WIDTH) -> tuple[str, str]:
    heading_row = (
        f"{messages.TABLE:<{width}}{pad(messages.CORP, NAME_WIDTH)}"
        f"{messages.SCORE:<{SCORE_WIDTH + 2}}{messages.RUNNER}"
    )
    return (
        f"{sgr(ansi.HEADING)}{heading_row}{RESET}",
        ansi.rule(width + RULE_WIDTH_AFTER_TABLE),
    )


def pairing_rows(t: Tournament, pairing: Pairing, width: int = MIN_TABLE_WIDTH) -> str:
    label = f"T{pairing.table}"
    if pairing.is_bye:
        (player_id,) = pairing.player_ids or (None,)
        name = (player_name(t, player_id), ansi.PLAIN)
        return _row(label, width, name, messages.BYE, None)
    s1, s2 = pairing.seat1, pairing.seat2
    if pairing.double_sided:
        # Each seat holds the player's own result as Corp and as Runner (findings
        # Q3), so game 1 is seat 1 as Corp against seat 2 as Runner, and game 2 the
        # reverse.
        total = _result(t, pairing, (s1, s1.combined_score), (s2, s2.combined_score))
        game1 = _game(
            t, pairing, GAME_MARK, width, (s1, s1.corp_score), (s2, s2.runner_score)
        )
        game2 = _game(
            t, pairing, GAME_MARK, width, (s2, s2.corp_score), (s1, s1.runner_score)
        )
        return "\n".join([_row(label, width, *total), game1, game2])
    # Single-sided games always have roles (findings Q3).
    corp, runner = (s1, s2) if s1.role == "corp" else (s2, s1)
    return _game(
        t,
        pairing,
        label,
        width,
        (corp, corp.combined_score),
        (runner, runner.combined_score),
    )


def _game(
    t: Tournament, pairing: Pairing, label: str, width: int, corp: Side, runner: Side
) -> str:
    """Two lines: names and score, then the Corp and Runner IDs under the names."""
    names = _row(label, width, *_result(t, pairing, corp, runner))
    corp_player, runner_player = _player(t, corp[0]), _player(t, runner[0])
    corp_id = corp_label(corp_player.corp_identity if corp_player else None)
    runner_id = runner_label(runner_player.runner_identity if runner_player else None)
    ids = (
        f"{' ' * width}{sgr(ansi.CORP)}{pad(corp_id, ID_LINE_WIDTH)}"
        f"{sgr(ansi.RUNNER)}{runner_id}{RESET}"
    )
    return f"{names}\n{ids}"


def _player(t: Tournament, seat: Seat) -> Player | None:
    return t.player(seat.player_id) if seat.player_id is not None else None


def _result(
    t: Tournament, pairing: Pairing, left: Side, right: Side
) -> tuple[Named, str, Named]:
    """Both names styled by the result, and the score between them."""
    (left_seat, left_score), (right_seat, right_score) = left, right
    left_name = player_name(t, left_seat.player_id)
    right_name = player_name(t, right_seat.player_id)
    if pairing.intentional_draw:
        score = messages.INTENTIONAL_DRAW
    elif left_score is None or right_score is None:
        score = messages.VERSUS
    else:
        score = f"{left_score}–{right_score}"
        if left_score != right_score:
            won = left_score > right_score
            return (
                (left_name, ansi.STRONG if won else ansi.MUTED),
                score,
                (right_name, ansi.MUTED if won else ansi.STRONG),
            )
    return (left_name, ansi.PLAIN), score, (right_name, ansi.PLAIN)


def _row(label: str, width: int, left: Named, score: str, right: Named | None) -> str:
    name, style = left
    row = (
        f"{sgr(ansi.MUTED)}{label:<{width}}"
        f"{sgr(style)}{pad(fit(name, NAME_WIDTH), NAME_WIDTH)}"
        f"{sgr(ansi.SCORE)}{score:>{SCORE_WIDTH}}  "
    )
    if right is not None:
        right_name, right_style = right
        row += f"{sgr(right_style)}{fit(right_name, NAME_WIDTH)}"
    return row.rstrip() + RESET
