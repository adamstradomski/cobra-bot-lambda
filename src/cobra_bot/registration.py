"""The global `/cobra` command as registered with Discord (docs/spec/architecture.md).

A public contract: names, options, integration types and contexts must not
change without the author's approval (CLAUDE.md).
"""

from cobra_bot import messages
from cobra_bot.commands import COMMAND

CHAT_INPUT = 1
SUB_COMMAND = 1
STRING = 3
INTEGER = 4

GUILD_INSTALL, USER_INSTALL = 0, 1
GUILD, BOT_DM, PRIVATE_CHANNEL = 0, 1, 2

QUERY_MIN_LENGTH, QUERY_MAX_LENGTH = 1, 200

type Definition = dict[str, object]


def _tournament_option() -> Definition:
    return {
        "type": STRING,
        "name": "tournament",
        "description": messages.TOURNAMENT_OPTION_DESCRIPTION,
        "required": True,
    }


def command_definition() -> Definition:
    return {
        "name": COMMAND,
        "type": CHAT_INPUT,
        "description": messages.COMMAND_DESCRIPTION,
        "integration_types": [GUILD_INSTALL, USER_INSTALL],
        "contexts": [GUILD, BOT_DM, PRIVATE_CHANNEL],
        "options": [
            {
                "type": SUB_COMMAND,
                "name": "pairings",
                "description": messages.PAIRINGS_DESCRIPTION,
                "options": [
                    _tournament_option(),
                    {
                        "type": INTEGER,
                        "name": "round",
                        "description": messages.ROUND_OPTION_DESCRIPTION,
                        "required": False,
                        "min_value": 1,
                    },
                ],
            },
            {
                "type": SUB_COMMAND,
                "name": "standings",
                "description": messages.STANDINGS_DESCRIPTION,
                "options": [_tournament_option()],
            },
            {
                "type": SUB_COMMAND,
                "name": "top-cut",
                "description": messages.TOP_CUT_DESCRIPTION,
                "options": [_tournament_option()],
            },
            {
                "type": SUB_COMMAND,
                "name": "bracket",
                "description": messages.BRACKET_DESCRIPTION,
                "options": [_tournament_option()],
            },
            {
                "type": SUB_COMMAND,
                "name": "player",
                "description": messages.PLAYER_DESCRIPTION,
                "options": [
                    _tournament_option(),
                    {
                        "type": STRING,
                        "name": "query",
                        "description": messages.QUERY_OPTION_DESCRIPTION,
                        "required": True,
                        "min_length": QUERY_MIN_LENGTH,
                        "max_length": QUERY_MAX_LENGTH,
                    },
                ],
            },
        ],
    }
