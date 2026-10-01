"""Pairings output (FR-03, FR-04, FR-05; SPEC §9).

Single-sided: `T3 · Alice (Corp, Nuvem SA) 3–0 Bob (Runner, Arissana)`
Double-sided: `T3 · Alice 3–3 Bob`, then one `↳` line per game in single-sided form.
Unreported results show `vs`, intentional draws `ID`, byes `T21 · Carol — BYE`.
"""

from cobra_bot import messages
from cobra_bot.domain.models import Pairing, Role, Seat, Tournament
from cobra_bot.domain.rounds import PairingsView
from cobra_bot.formatting.document import Document, data_line, player_name
from cobra_bot.formatting.text import short_identity, tournament_url

GAME_PREFIX = "↳ "


def format_pairings(
    t: Tournament, view: PairingsView, *, private: bool = False
) -> Document:
    header = [messages.pairings_header(view.round_number, view.complete)]
    if view.top_cut_in_progress:
        header.append(messages.TOP_CUT_IN_PROGRESS)
    header.append(data_line(t, private=private))
    return Document(
        title=t.name,
        url=tournament_url(t.id),
        header=tuple(header),
        entries=tuple(
            pairing_entry(t, p) for p in sorted(view.pairings, key=lambda p: p.table)
        ),
    )


def pairing_entry(t: Tournament, pairing: Pairing) -> str:
    table = f"T{pairing.table}"
    if pairing.is_bye:
        (player_id,) = pairing.player_ids or (None,)
        return f"{table} · {player_name(t, player_id)} — {messages.BYE}"
    if pairing.double_sided:
        return _double_sided(t, pairing, table)
    s1, s2 = pairing.seat1, pairing.seat2
    score = _score(pairing, s1.combined_score, s2.combined_score)
    return f"{table} · {_side(t, s1, s1.role)} {score} {_side(t, s2, s2.role)}"


def _double_sided(t: Tournament, pairing: Pairing, table: str) -> str:
    s1, s2 = pairing.seat1, pairing.seat2
    total = _score(pairing, s1.combined_score, s2.combined_score)
    # Each seat holds the player's own result as Corp and as Runner (findings Q3),
    # so game 1 is seat 1 as Corp against seat 2 as Runner, and game 2 the reverse.
    game1 = _score(pairing, s1.corp_score, s2.runner_score)
    game2 = _score(pairing, s2.corp_score, s1.runner_score)
    return "\n".join(
        [
            f"{table} · {player_name(t, s1.player_id)} {total} "
            f"{player_name(t, s2.player_id)}",
            f"{GAME_PREFIX}{_side(t, s1, 'corp')} {game1} {_side(t, s2, 'runner')}",
            f"{GAME_PREFIX}{_side(t, s2, 'corp')} {game2} {_side(t, s1, 'runner')}",
        ]
    )


def _side(t: Tournament, seat: Seat, role: Role | None) -> str:
    name = player_name(t, seat.player_id)
    if role is None:
        return name
    player = t.player(seat.player_id) if seat.player_id is not None else None
    if role == "corp":
        label, identity = messages.CORP, player.corp_identity if player else None
    else:
        label, identity = messages.RUNNER, player.runner_identity if player else None
    return f"{name} ({label}, {short_identity(identity)})"


def _score(pairing: Pairing, a: int | None, b: int | None) -> str:
    if pairing.intentional_draw:
        return messages.INTENTIONAL_DRAW
    if a is None or b is None:
        return messages.VERSUS
    return f"{a}–{b}"
