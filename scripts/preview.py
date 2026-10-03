#!/usr/bin/env python3
"""Post the bot's reply to a `/cobra` command into a Discord channel, rendered
from a local Cobra export, to check the layout without building or deploying.

    uv run scripts/preview.py 5018 pairings --round 2
    uv run scripts/preview.py 4909 standings --format b2
    uv run scripts/preview.py tests/fixtures/dss.json player 1003 --dry-run

Format A, the default, is the bot's reply: it goes through the same code as the
Worker (`commands.execute`, the cache, the parser, the formatters,
`message_payload`), so the embeds are the production ones. Formats B1, B2 and C
are layouts under test (`cobra_bot.preview`) for the same data. Cobra is never
contacted. Messages are posted through a channel webhook
(`DISCORD_PREVIEW_WEBHOOK_URL`). Runs in the project environment. See README.md
for options and exit codes.
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

from cobra_bot.cobra.cache import InMemoryCacheStore, TournamentCache, tournament_key
from cobra_bot.cobra.client import CobraError, Private, Unavailable
from cobra_bot.cobra.parser import parse_tournament
from cobra_bot.commands import Command, CommandName, Reply, execute
from cobra_bot.discord import api as discord
from cobra_bot.discord.api import Attachment, DiscordError, Payload, WebhookClient
from cobra_bot.domain.models import Tournament
from cobra_bot.domain.rounds import (
    PairingsView,
    StandingsView,
    pairings_view,
    standings_view,
    swiss_round_numbers,
)
from cobra_bot.domain.search import search_players
from cobra_bot.formatting.document import Document
from cobra_bot.formatting.pairings import format_pairings
from cobra_bot.formatting.players import format_player_cards
from cobra_bot.formatting.standings import format_standings
from cobra_bot.formatting.text import tournament_url

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS_DIR = REPO_ROOT / "snapshots"
WEBHOOK_ENV = "DISCORD_PREVIEW_WEBHOOK_URL"
# Tournament ID for an export outside snapshots/{id}/; only shows in Cobra links.
DEFAULT_TOURNAMENT_ID = 1
# Age of the cached copy for --stale / --private: past the TTL, so the cache
# asks Cobra (the fake below) and serves the copy marked stale.
STALE_AGE = timedelta(minutes=10)
FORMATS = ("a", "b1", "b2", "c")
LINK_BUTTON = 5  # button style
BUTTONS_PER_ROW = 5

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
type Component = dict[str, object]


class UsageError(Exception):
    """Bad arguments, a missing export or a bad webhook URL; exit code 2."""


@dataclass(frozen=True)
class Post:
    """One message to post."""

    payload: Payload
    files: tuple[Attachment, ...] = ()
    components: bool = False  # Components V2: the webhook must be told


@dataclass(frozen=True)
class Options:
    """How to render the non-A formats."""

    format: str = "a"
    page: int | None = 1  # None = every page
    mockup: bool = True  # swap interactive components for link buttons
    font: Path | None = None
    bold_font: Path | None = None


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


def render(
    command: Command, body: bytes, tournament_id: int, now: datetime, data: str
) -> Reply:
    """Run `command` as the Worker does, with `body` as the cached export."""
    return execute(command, offline_cache(body, tournament_id, now, data))


def payloads(reply: Reply) -> list[Payload]:
    """The bodies the Worker would send. Channel webhooks cannot post ephemeral
    messages, so no payload carries the ephemeral flag."""
    if isinstance(reply, str):
        return [discord.text_payload(reply)]
    return [discord.message_payload(message) for message in reply]


def build_posts(
    command: Command, cache: TournamentCache, tournament_id: int, options: Options
) -> list[Post]:
    """The messages for `options.format`. An error reply (unknown round, not
    started, …) is the bot's text reply in every format."""
    reply = execute(command, cache)
    if options.format == "a" or isinstance(reply, str):
        return [Post(p) for p in payloads(reply)]
    result = cache.tournament(tournament_id)
    t = parse_tournament(
        json.loads(result.body),
        tournament_id=tournament_id,
        fetched_at=result.fetched_at,
        stale=result.stale,
    )
    pages = _variant_pages(command, t, result.private, options)
    if options.page is None:
        return pages
    if not 1 <= options.page <= len(pages):
        raise UsageError(f"--page {options.page}: this reply has {len(pages)} page(s).")
    return [pages[options.page - 1]]


def _variant_pages(
    command: Command, t: Tournament, private: bool, options: Options
) -> list[Post]:
    from cobra_bot.preview import components  # only for B1, B2

    view = (
        pairings_view(t, command.round)
        if command.name == "pairings"
        else standings_view(t)
        if command.name == "standings"
        else None
    )
    nav = components.NO_ROUNDS
    if isinstance(view, PairingsView):
        nav = components.Nav(tuple(swiss_round_numbers(t)), view.round_number)
    url = tournament_url(t.id)

    def v2(payloads: list[Payload]) -> list[Post]:
        if options.mockup:
            payloads = [link_mockup(p, url) for p in payloads]
        return [Post(p, components=True) for p in payloads]

    match options.format:
        case "b1":
            return v2(components.b1_pages(_document(command, t, view, private), nav))
        case "b2" if isinstance(view, StandingsView):
            return v2(components.b2_standings(t, view, private=private))
        case "b2" if isinstance(view, PairingsView):
            return v2(components.b2_pairings(t, view, nav, private=private))
        case "c" if isinstance(view, StandingsView | PairingsView):
            from cobra_bot.preview import image  # imports Pillow: only for C

            try:
                fonts = image.load_fonts(options.font, options.bold_font)
            except image.FontNotFound as err:
                raise UsageError(str(err)) from None
            images = (
                image.c_standings(t, view, fonts, private=private)
                if isinstance(view, StandingsView)
                else image.c_pairings(t, view, fonts, private=private)
            )
            return [Post(payload, (file,)) for payload, file in images]
    raise UsageError(f"--format {options.format} supports pairings and standings.")


def _document(
    command: Command,
    t: Tournament,
    view: object,
    private: bool,
) -> Document:
    if isinstance(view, PairingsView):
        return format_pairings(t, view, private=private)
    if isinstance(view, StandingsView):
        return format_standings(t, view, private=private)
    query = command.query or ""
    return format_player_cards(
        t, search_players(t.players, query), query, private=private
    )


def link_mockup(payload: Payload, url: str) -> Payload:
    """Channel webhooks may post only non-interactive components, so every
    button becomes a link button with the same label, and the round select a
    row of link buttons, one per option, the selected one disabled. All links
    go to `url`."""

    def convert(components: object) -> list[object]:
        out: list[object] = []
        for item in components if isinstance(components, list) else []:
            if not isinstance(item, dict):
                out.append(item)
                continue
            children = item.get("components")
            selects = [
                c for c in children or [] if isinstance(c, dict) and "options" in c
            ]
            if selects:
                out.extend(_option_rows(selects[0], url))
                continue
            if "custom_id" in item:
                item = {k: v for k, v in item.items() if k != "custom_id"}
                item.update(style=LINK_BUTTON, url=url)
            elif children is not None:
                item = {**item, "components": convert(children)}
            out.append(item)
        return out

    return {**payload, "components": convert(payload.get("components"))}


def _option_rows(select: Component, url: str) -> list[object]:
    options = select.get("options")
    buttons: list[Component] = [
        {
            "type": 2,
            "style": LINK_BUTTON,
            "label": option.get("label"),
            "url": url,
            "disabled": bool(option.get("default")),
        }
        for option in (options if isinstance(options, list) else [])
        if isinstance(option, dict)
    ]
    return [
        {"type": 1, "components": buttons[i : i + BUTTONS_PER_ROW]}
        for i in range(0, len(buttons), BUTTONS_PER_ROW)
    ]


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


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1: {value}")
    return value


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
        "--format",
        choices=FORMATS,
        default="a",
        help="a: the bot's embeds (default); b1, b2, c: layouts under test",
    )
    pages = common.add_mutually_exclusive_group()
    pages.add_argument(
        "--page", type=_positive, default=1, help="b1, b2, c: page to post (default 1)"
    )
    pages.add_argument(
        "--all-pages",
        dest="page",
        action="store_const",
        const=None,
        help="b1, b2, c: post every page",
    )
    common.add_argument(
        "--no-mockup",
        dest="mockup",
        action="store_false",
        help="b1, b2: keep the real buttons and select (a channel webhook rejects "
        "them)",
    )
    common.add_argument("--font", type=Path, help="c: TrueType font file")
    common.add_argument(
        "--bold-font", type=Path, help="c: bold TrueType font (default: --font)"
    )
    common.add_argument(
        "--save-images", type=Path, metavar="DIR", help="c: also write the PNGs here"
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
) -> int:
    args = _parser().parse_args(argv)
    if args.tournament_id is not None and args.tournament_id < 1:
        print("preview: --id must be a positive number", file=sys.stderr)
        return EXIT_USAGE
    options = Options(args.format, args.page, args.mockup, args.font, args.bold_font)
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
        posts = build_posts(command, cache, tournament_id, options)
        if args.note:
            note: Payload = {"content": args.note, "allowed_mentions": {"parse": []}}
            posts.insert(0, Post(note))
        if args.save_images is not None:
            _save_images(posts, args.save_images)
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
        bodies = [post.payload for post in posts]
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
        for post in posts:
            webhook.follow_up(
                token, post.payload, files=post.files, with_components=post.components
            )
    except DiscordError as err:
        detail = f" (Discord: {err.detail})" if err.detail else ""
        print(f"preview: {err}{detail}", file=sys.stderr)
        return EXIT_FAILED
    finally:
        if http is None:
            client.close()
    print(
        f"preview: {command.name} of {path.name} in format {options.format.upper()} "
        f"sent as {len(posts)} message(s) "
        f"in {(time.monotonic() - started) * 1000:.0f} ms",
        file=sys.stderr,
    )
    return EXIT_OK


def _save_images(posts: list[Post], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for post in posts:
        for file in post.files:
            (directory / file.filename).write_bytes(file.content)
            print(f"preview: wrote {directory / file.filename}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
