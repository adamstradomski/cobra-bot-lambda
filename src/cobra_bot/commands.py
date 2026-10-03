"""The `/cobra` command: read it from an interaction, hand it to the Worker, and
run it there (SPEC §2, §3).

The Worker receives only what it needs (`Job`), never the whole interaction,
so no user data travels or gets logged (NFR-09).
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal, cast

from cobra_bot import messages
from cobra_bot.cobra.cache import TournamentCache
from cobra_bot.cobra.client import NotFound, Private, Unavailable
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.cobra.refs import InvalidTournamentRef, TournamentId, parse_ref
from cobra_bot.domain.models import Tournament
from cobra_bot.domain.rounds import (
    NotStarted,
    PairingsView,
    RoundOutOfRange,
    StandingsView,
    TopCutNotSupported,
    pairings_view,
    standings_view,
)
from cobra_bot.domain.search import search_players
from cobra_bot.formatting.chunking import ImagePage, Message, chunk
from cobra_bot.formatting.players import format_player_cards

if TYPE_CHECKING:
    from cobra_bot.formatting.image import Fonts

log = logging.getLogger(__name__)

type CommandName = Literal["pairings", "standings", "player"]

COMMAND = "cobra"
SUBCOMMANDS: frozenset[str] = frozenset({"pairings", "standings", "player"})


@dataclass(frozen=True)
class Command:
    name: CommandName
    tournament: str
    round: int | None = None
    query: str | None = None

    @property
    def ephemeral(self) -> bool:
        """`/cobra player` replies privately (FR-09); the others are public."""
        return self.name == "player"


@dataclass(frozen=True)
class Job:
    """What the Interactions function passes to the Worker (async invoke)."""

    application_id: str
    token: str
    command: Command

    def to_payload(self) -> dict[str, object]:
        return {
            "application_id": self.application_id,
            "token": self.token,
            "command": asdict(self.command),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Job:
        raw = payload.get("command")
        if not isinstance(raw, Mapping):
            raise ValueError("job without a command")
        command = _command(
            raw.get("name"), raw.get("tournament"), raw.get("round"), raw.get("query")
        )
        application_id, token = payload.get("application_id"), payload.get("token")
        if command is None or not isinstance(application_id, str):
            raise ValueError("malformed job")
        if not isinstance(token, str) or not token:
            raise ValueError("job without a token")
        return cls(application_id, token, command)


def parse_command(interaction: Mapping[str, object]) -> Command | None:
    """The `/cobra <subcommand>` in an APPLICATION_COMMAND interaction, or None."""
    data = interaction.get("data")
    if not isinstance(data, Mapping) or data.get("name") != COMMAND:
        return None
    subcommands = data.get("options")
    if not isinstance(subcommands, list) or len(subcommands) != 1:
        return None
    sub = subcommands[0]
    if not isinstance(sub, Mapping):
        return None
    values: dict[str, object] = {}
    options = sub.get("options", [])
    for option in options if isinstance(options, list) else []:
        if isinstance(option, Mapping) and isinstance(option.get("name"), str):
            values[cast(str, option["name"])] = option.get("value")
    return _command(
        sub.get("name"),
        values.get("tournament"),
        values.get("round"),
        values.get("query"),
    )


def _command(
    name: object, tournament: object, rnd: object, query: object
) -> Command | None:
    if name not in SUBCOMMANDS or not isinstance(tournament, str):
        return None
    if rnd is not None and (isinstance(rnd, bool) or not isinstance(rnd, int)):
        return None
    if query is not None and not isinstance(query, str):
        return None
    if name == "player" and not query:
        return None
    return Command(
        name=cast(CommandName, name),
        tournament=tournament,
        round=rnd if name == "pairings" else None,
        query=query if name == "player" else None,
    )


# --- execution (Worker) ---------------------------------------------------------


@dataclass(frozen=True)
class Images:
    """A reply as image pages: pairings and standings (SPEC §9)."""

    pages: tuple[ImagePage, ...]


# Chunked embed messages (player cards), image pages, or one plain text reply.
type Reply = tuple[Message, ...] | Images | str


def execute(command: Command, cache: TournamentCache, fonts: Fonts) -> Reply:
    """Run a command end to end and map every expected failure to a message
    (FR-16). Unexpected exceptions propagate to the handler. `fonts` draw the
    images (`cobra_bot.fonts.load`)."""
    try:
        ref = parse_ref(command.tournament)
    except InvalidTournamentRef:
        return messages.INVALID_REFERENCE
    try:
        tournament_id = (
            ref.id if isinstance(ref, TournamentId) else cache.shortcode(ref.code)
        )
        result = cache.tournament(tournament_id)
    except NotFound:
        return messages.TOURNAMENT_NOT_FOUND
    except Private:
        return messages.TOURNAMENT_PRIVATE
    except Unavailable:
        return messages.COBRA_UNAVAILABLE
    log.info(
        "command=%s tournament=%s stale=%s private=%s",
        command.name,
        tournament_id,
        result.stale,
        result.private,
    )
    try:
        t = parse_tournament(
            json.loads(result.body),
            tournament_id=tournament_id,
            fetched_at=result.fetched_at,
            stale=result.stale,
        )
    except ValueError:  # invalid JSON or ParseError
        log.warning("unreadable export for tournament %s", tournament_id)
        return messages.COBRA_DATA_UNREADABLE
    return _run(command, t, fonts, private=result.private)


def _run(command: Command, t: Tournament, fonts: Fonts, *, private: bool) -> Reply:
    # Imported here: it loads Pillow, which InteractionsFunction (it imports this
    # module for parse_command) must not pay for within Discord's 3 s.
    from cobra_bot.formatting import image

    match command.name:
        case "pairings":
            match pairings_view(t, command.round):
                case NotStarted():
                    return messages.NOT_STARTED
                case RoundOutOfRange(requested=requested, last_round=last):
                    return messages.round_out_of_range(requested, last)
                case TopCutNotSupported():
                    return messages.TOP_CUT_NOT_SUPPORTED
                case PairingsView() as pairings:
                    return Images(
                        image.pairings_images(t, pairings, fonts, private=private)
                    )
        case "standings":
            match standings_view(t):
                case NotStarted():
                    return messages.NOT_STARTED
                case StandingsView() as standings:
                    return Images(
                        image.standings_images(t, standings, fonts, private=private)
                    )
        case "player":
            query = command.query or ""
            found = search_players(t.players, query)
            return chunk(format_player_cards(t, found, query, private=private))
