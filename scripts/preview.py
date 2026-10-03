#!/usr/bin/env python3
"""Post the bot's reply to a `/cobra` command into a Discord channel, rendered
from a local Cobra export, to check the layout without building or deploying.

    uv run scripts/preview.py 5018 pairings --round 2
    uv run scripts/preview.py 4909 standings --save-images out/
    uv run scripts/preview.py tests/fixtures/dss.json player 1003 --dry-run

The reply goes through the same code as the Worker (`commands.execute`, the
cache, the parser, the image renderer and formatters, the payload builders), so
the messages are the production ones: images for pairings and standings, an
embed for player cards. Cobra is never contacted. Messages are posted through a
channel webhook (`DISCORD_PREVIEW_WEBHOOK_URL`). Runs in the project
environment. See README.md for options and exit codes.
"""

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import httpx

from cobra_bot import fonts as bundled_fonts
from cobra_bot.cobra.cache import InMemoryCacheStore, TournamentCache, tournament_key
from cobra_bot.cobra.client import CobraError, Private, Unavailable
from cobra_bot.commands import Command, CommandName, Images, Reply, execute
from cobra_bot.discord import api as discord
from cobra_bot.discord.api import Attachment, DiscordError, Payload, WebhookClient
from cobra_bot.formatting.image import Fonts

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS_DIR = REPO_ROOT / "snapshots"
WEBHOOK_ENV = "DISCORD_PREVIEW_WEBHOOK_URL"
# Tournament ID for an export outside snapshots/{id}/; only shows in Cobra links.
DEFAULT_TOURNAMENT_ID = 1
# Age of the cached copy for --stale / --private: past the TTL, so the cache
# asks Cobra (the fake below) and serves the copy marked stale.
STALE_AGE = timedelta(minutes=10)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

# ASCII digits only: `\d` would also accept other scripts' digits.
_ID = re.compile(r"[0-9]{1,9}")
_WEBHOOK_URL = re.compile(
    r"https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api(?:/v[0-9]+)?"
    r"/webhooks/([0-9]+)/([A-Za-z0-9_-]+)"
)

type Clock = Callable[[], datetime]


class UsageError(Exception):
    """Bad arguments, a missing export or a bad webhook URL; exit code 2."""


@dataclass(frozen=True)
class Post:
    """One message to post."""

    payload: Payload
    files: tuple[Attachment, ...] = ()


class _OfflineCobra:
    """Fetcher that never contacts Cobra: every call fails with `error`."""

    def __init__(self, error: CobraError) -> None:
        self._error = error

    def fetch_tournament(self, tournament_id: int) -> bytes:
        raise self._error

    def resolve_shortcode(self, code: str) -> int:
        raise self._error


def resolve_source(
    source: str, snapshots: Path, tournament_id: int | None
) -> tuple[Path, int]:
    """The export to render and the tournament ID to render it under.

    A tournament ID means the newest `snapshots/{id}/{ts}.json`, written by
    `capture_snapshots.py`; anything else is a path to an export.
    """
    if _ID.fullmatch(source):
        directory = snapshots / source
        exports = sorted(
            p for p in directory.glob("*.json") if not p.name.endswith(".meta.json")
        )
        if not exports:
            raise UsageError(
                f"No snapshot of tournament {source} in {directory}. Capture one: "
                f"uv run scripts/capture_snapshots.py {source} --once"
            )
        return exports[-1], tournament_id or int(source)
    path = Path(source)
    if not path.is_file():
        raise UsageError(f"{source} is neither a tournament ID nor a file.")
    parent_id = int(path.parent.name) if _ID.fullmatch(path.parent.name) else None
    return path, tournament_id or parent_id or DEFAULT_TOURNAMENT_ID


def offline_cache(
    body: bytes, tournament_id: int, now: datetime, data: str
) -> TournamentCache:
    """A cache holding `body`, with a Cobra that is never reached.

    `data`: `fresh` (fetched just now), `stale` (Cobra unavailable) or `private`
    (the tournament became private).
    """
    store = InMemoryCacheStore()
    fetched_at = now if data == "fresh" else now - STALE_AGE
    store.put(tournament_key(tournament_id), body, fetched_at)
    error: CobraError = Private("preview") if data == "private" else Unavailable("")
    return TournamentCache(
        store, _OfflineCobra(error), clock=lambda: now, sleep=lambda _: None
    )


def posts(reply: Reply) -> list[Post]:
    """The messages the Worker would send. Channel webhooks cannot post
    ephemeral messages, so none carries the ephemeral flag."""
    if isinstance(reply, str):
        return [Post(discord.text_payload(reply))]
    if isinstance(reply, Images):
        return [
            Post(discord.image_payload(page), (discord.image_file(page),))
            for page in reply.pages
        ]
    return [Post(discord.message_payload(message)) for message in reply]


def webhook_target(env: Mapping[str, str]) -> tuple[str, str]:
    """Webhook ID and token from the webhook URL; the URL is never printed."""
    url = (env.get(WEBHOOK_ENV) or "").strip()
    if not url:
        raise UsageError(f"Set {WEBHOOK_ENV}, or use --dry-run.")
    match = _WEBHOOK_URL.fullmatch(url)
    if match is None:
        raise UsageError(
            f"{WEBHOOK_ENV} is not a Discord webhook URL "
            "(https://discord.com/api/webhooks/<id>/<token>)."
        )
    return match[1], match[2]


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--dry-run",
        action="store_true",
        help="print the payloads instead of sending them; needs no webhook",
    )
    data = common.add_mutually_exclusive_group()
    data.add_argument(
        "--stale",
        dest="data",
        action="store_const",
        const="stale",
        help="render as stale data: Cobra unavailable",
    )
    data.add_argument(
        "--private",
        dest="data",
        action="store_const",
        const="private",
        help="render as stale data: the tournament became private",
    )
    common.add_argument(
        "--id",
        type=int,
        dest="tournament_id",
        help="tournament ID used in Cobra links (default: from SOURCE)",
    )
    common.add_argument(
        "--save-images", type=Path, metavar="DIR", help="also write the PNGs here"
    )
    common.add_argument(
        "--note",
        metavar="TEXT",
        help="post TEXT as a plain message first, to label the preview",
    )
    common.set_defaults(data="fresh")

    parser = argparse.ArgumentParser(
        description="Preview /cobra replies in Discord from a local Cobra export."
    )
    parser.add_argument(
        "source",
        metavar="SOURCE",
        help="tournament ID (newest snapshot in snapshots/ID/) or export file",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    pairings = commands.add_parser("pairings", parents=[common])
    pairings.add_argument("--round", type=int, help="round number (default: latest)")
    commands.add_parser("standings", parents=[common])
    player = commands.add_parser("player", parents=[common])
    player.add_argument("query", help="player name or part of it")
    return parser


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    http: httpx.Client | None = None,
    clock: Clock = lambda: datetime.now(UTC),
    snapshots: Path = SNAPSHOTS_DIR,
    fonts: Fonts | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.tournament_id is not None and args.tournament_id < 1:
        print("preview: --id must be a positive number", file=sys.stderr)
        return EXIT_USAGE
    try:
        path, tournament_id = resolve_source(args.source, snapshots, args.tournament_id)
        body = path.read_bytes()
        target = (
            None if args.dry_run else webhook_target(os.environ if env is None else env)
        )
        command = Command(
            name=cast(CommandName, args.command),
            tournament=str(tournament_id),
            round=getattr(args, "round", None),
            query=getattr(args, "query", None),
        )
        cache = offline_cache(body, tournament_id, clock(), args.data)
        reply = execute(command, cache, fonts or bundled_fonts.load())
        messages = posts(reply)
        if args.note:
            note: Payload = {"content": args.note, "allowed_mentions": {"parse": []}}
            messages.insert(0, Post(note))
        if args.save_images is not None:
            _save_images(messages, args.save_images)
    except UsageError as err:
        print(f"preview: {err}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as err:
        print(
            f"preview: {err.filename or args.source}: {err.strerror}", file=sys.stderr
        )
        return EXIT_USAGE

    if target is None:
        # UTF-8 whatever the console code page, so names and IDs print as is.
        bodies = [message.payload for message in messages]
        text = json.dumps(bodies, indent=2, ensure_ascii=False) + "\n"
        sys.stdout.flush()
        sys.stdout.buffer.write(text.encode())
        sys.stdout.buffer.flush()
        return EXIT_OK

    webhook_id, token = target
    if command.ephemeral:
        print("preview: posted publicly; the bot replies privately", file=sys.stderr)
    started = time.monotonic()
    client = http or discord.make_http_client()
    try:
        webhook = WebhookClient(client, webhook_id)
        for message in messages:
            webhook.follow_up(token, message.payload, files=message.files)
    except DiscordError as err:
        detail = f" (Discord: {err.detail})" if err.detail else ""
        print(f"preview: {err}{detail}", file=sys.stderr)
        return EXIT_FAILED
    finally:
        if http is None:
            client.close()
    print(
        f"preview: {command.name} of {path.name} sent as {len(messages)} message(s) "
        f"in {(time.monotonic() - started) * 1000:.0f} ms",
        file=sys.stderr,
    )
    return EXIT_OK


def _save_images(messages: list[Post], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for message in messages:
        for file in message.files:
            (directory / file.filename).write_bytes(file.content)
            print(f"preview: wrote {directory / file.filename}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
