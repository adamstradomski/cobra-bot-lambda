#!/usr/bin/env python3
"""Register the global `/cobra` command with Discord (task T22, SPEC §2).

Overwrites the application's global commands with the definition in
`cobra_bot.registration`. Runs in the project environment: `uv run
scripts/register_commands.py`. See README.md for usage and exit codes.
"""

import argparse
import json
import os
import sys
from collections.abc import Mapping

import httpx

from cobra_bot.registration import command_definition

DISCORD_API = "https://discord.com/api/v10"
USER_AGENT = "DiscordBot (https://github.com/adamstradomski/cobra-bot-lambda, 0.1)"
APP_ID_ENV = "DISCORD_APPLICATION_ID"
TOKEN_ENV = "DISCORD_BOT_TOKEN"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def payload() -> list[dict[str, object]]:
    return [command_definition()]


def register(http: httpx.Client, application_id: str, token: str) -> httpx.Response:
    return http.put(
        f"{DISCORD_API}/applications/{application_id}/commands",
        json=payload(),
        headers={"Authorization": f"Bot {token}", "User-Agent": USER_AGENT},
    )


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    http: httpx.Client | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Register the /cobra command.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the payload instead of sending it; needs no credentials",
    )
    args = parser.parse_args(argv)
    if args.dry_run:
        print(json.dumps(payload(), indent=2, ensure_ascii=False))
        return EXIT_OK

    env = os.environ if env is None else env
    application_id, token = env.get(APP_ID_ENV), env.get(TOKEN_ENV)
    if not application_id or not token:
        print(f"register_commands: set {APP_ID_ENV} and {TOKEN_ENV}", file=sys.stderr)
        return EXIT_USAGE

    client = http or httpx.Client(timeout=10.0)
    try:
        response = register(client, application_id, token)
    except httpx.HTTPError as err:
        print(
            f"register_commands: request failed: {type(err).__name__}", file=sys.stderr
        )
        return EXIT_FAILED
    finally:
        if http is None:
            client.close()
    if not response.is_success:
        # Discord's error body explains the problem and never echoes the token.
        print(
            f"register_commands: HTTP {response.status_code}: {response.text[:500]}",
            file=sys.stderr,
        )
        return EXIT_FAILED
    names = [c.get("name") for c in response.json() if isinstance(c, dict)]
    print(f"register_commands: registered {names}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
