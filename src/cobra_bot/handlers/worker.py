"""WorkerFunction: runs a deferred command and sends the reply (SPEC §1, §3).

Invoked asynchronously by InteractionsFunction with no retries (NFR-06), so it
never raises: every failure ends in a logged error and, where possible, an error
message to the user.

Environment: `CACHE_BUCKET`, the S3 bucket of the shared cache.
"""

import logging
import os
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from cobra_bot import fonts, messages
from cobra_bot.cobra import client as cobra
from cobra_bot.cobra.cache import TournamentCache
from cobra_bot.cobra.s3_store import S3CacheStore
from cobra_bot.commands import Images, Job, execute
from cobra_bot.discord import api as discord
from cobra_bot.discord.api import DiscordError, WebhookClient
from cobra_bot.formatting.image import Fonts
from cobra_bot.handlers.logging_setup import configure_logging
from cobra_bot.image_cache import ImageCache

log = logging.getLogger(__name__)

CACHE_BUCKET_ENV = "CACHE_BUCKET"

type Event = Mapping[str, Any]  # Any: Lambda events are untyped JSON
type WebhookFactory = Callable[[str], WebhookClient]  # application ID -> client


class WorkerApp:
    def __init__(
        self,
        cache: TournamentCache,
        webhooks: WebhookFactory,
        fonts: Fonts,
        images: ImageCache | None = None,
    ) -> None:
        self._cache = cache
        self._webhooks = webhooks
        self._fonts = fonts
        self._images = images

    def handle(self, event: Event) -> None:
        try:
            job = Job.from_payload(event)
        except ValueError:
            log.error("malformed job; nothing to reply to")
            return
        started = time.monotonic()
        before = (self._images.hits, self._images.misses) if self._images else (0, 0)
        try:
            reply = execute(job.command, self._cache, self._fonts, self._images)
        except Exception:
            log.exception("command %s failed", job.command.name)
            reply = messages.INTERNAL_ERROR
        webhook = self._webhooks(job.application_id)
        try:
            if isinstance(reply, str):
                webhook.send_text(job.token, reply)
            elif isinstance(reply, Images):
                webhook.send_images(job.token, reply.pages)
            else:
                webhook.send(job.token, reply)
        except DiscordError as err:
            # Discord's short error body names the cause (e.g. Unknown Message);
            # it never holds the token, which is only in the URL.
            log.error(
                "reply to %s not delivered: %s %s",
                job.command.name,
                err,
                err.detail,
            )
            return
        hits, misses = (
            (self._images.hits - before[0], self._images.misses - before[1])
            if self._images
            else (0, 0)
        )
        log.info(
            "command=%s done in %.0f ms images cached=%d drawn=%d",
            job.command.name,
            (time.monotonic() - started) * 1000,
            hits,
            misses,
        )


def utc_now() -> datetime:
    return datetime.now(UTC)


# --- Lambda entry point -------------------------------------------------------------

_app: WorkerApp | None = None


def _app_from_environment() -> WorkerApp:  # pragma: no cover - needs AWS
    import boto3  # type: ignore[import-untyped]  # provided by the Lambda runtime

    store = S3CacheStore(boto3.client("s3"), os.environ[CACHE_BUCKET_ENV])
    cache = TournamentCache(
        store, cobra.CobraClient(cobra.make_http_client()), clock=utc_now
    )
    discord_http = discord.make_http_client()
    return WorkerApp(
        cache,
        lambda app_id: WebhookClient(discord_http, app_id),
        fonts.load(),
        ImageCache(store, clock=utc_now),  # same bucket, own prefix and TTL
    )


def handler(event: Event, context: object) -> None:
    global _app
    if _app is None:
        configure_logging()
        _app = _app_from_environment()
    _app.handle(event)
