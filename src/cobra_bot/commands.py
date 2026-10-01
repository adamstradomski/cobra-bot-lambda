"""The `/cobra` command: read it from an interaction and hand it to the Worker
(SPEC §2, §3).

The Worker receives only what it needs (`Job`), never the whole interaction,
so no user data travels or gets logged (NFR-09).
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal, cast

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
