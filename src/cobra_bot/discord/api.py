"""Discord interaction webhooks: edit the deferred response, post follow-ups
(SPEC §3, §9; NFR-06, NFR-10).

- Every payload sets `allowed_mentions: {"parse": []}` so nothing pings.
- Only HTTP 429 is retried, after `Retry-After` (Discord did not process the
  request). Network errors are not retried: a POST that timed out may have been
  delivered, and a retry could duplicate the message.
- The interaction token is part of the URL; it never appears in errors.
"""

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import httpx

from cobra_bot.formatting.chunking import FIELD_NAME, Embed, ImagePage, Message
from cobra_bot.formatting.document import EMBED_COLOR

DISCORD_API = "https://discord.com/api/v10"
USER_AGENT = "DiscordBot (https://github.com/adamstradomski/cobra-bot-lambda, 0.1)"
TIMEOUT_S = 10.0
MAX_RATE_LIMIT_RETRIES = 3
MAX_RETRY_AFTER_S = 10.0
DETAIL_CHARS = 300  # of Discord's error body kept in DiscordError.detail

type Sleep = Callable[[float], None]
type Payload = dict[str, object]


class DiscordError(Exception):
    """A webhook request failed; the message says how, never with the token.

    `detail`: the start of Discord's error body (it says which field it
    rejected), kept out of the message so it is not logged by default.
    """

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


def make_http_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})


def embed_payload(embed: Embed) -> Payload:
    """Discord rejects an empty description, so an empty one is left out (an
    image page after the first has none)."""
    payload: Payload = {}
    if embed.description:
        payload["description"] = embed.description
    if embed.title is not None:
        payload["title"] = embed.title
    if embed.url is not None:
        payload["url"] = embed.url
    if embed.color is not None:
        payload["color"] = embed.color
    if embed.fields:
        payload["fields"] = [
            {"name": FIELD_NAME, "value": value, "inline": False}
            for value in embed.fields
        ]
    if embed.image is not None:
        payload["image"] = {"url": f"attachment://{embed.image}"}
    if embed.footer is not None:
        payload["footer"] = {"text": embed.footer}
    return payload


def message_payload(embeds: Sequence[Embed]) -> Payload:
    return {
        "embeds": [embed_payload(e) for e in embeds],
        "allowed_mentions": {"parse": []},
    }


MAX_EMBEDS = 10  # per message (Discord)


def image_payload(pages: Sequence[ImagePage]) -> Payload:
    """One message showing every page: an embed per page, its PNG declared as
    attachment n (sent as `files[n]`). One upload instead of one per page is
    what makes a long reply fast."""
    if not 1 <= len(pages) <= MAX_EMBEDS:
        raise ValueError(f"{len(pages)} image pages; one message holds 1 to 10")
    payload = message_payload([page.embed for page in pages])
    payload["attachments"] = [
        {"id": n, "filename": page.filename} for n, page in enumerate(pages)
    ]
    return payload


def image_files(pages: Sequence[ImagePage]) -> tuple[Attachment, ...]:
    return tuple(Attachment(p.filename, p.png, "image/png") for p in pages)


def text_payload(text: str) -> Payload:
    """A single-embed reply, e.g. an error message: one sentence, no code block,
    in the bot colour (embed format C-2, C-12)."""
    return message_payload([Embed(description=text, color=EMBED_COLOR)])


class WebhookClient:
    def __init__(
        self,
        http: httpx.Client,
        application_id: str,
        sleep: Sleep = time.sleep,
        base_url: str = DISCORD_API,
    ) -> None:
        self._http = http
        self._application_id = application_id
        self._sleep = sleep
        self._base_url = base_url.rstrip("/")

    def send(self, token: str, messages: Sequence[Message]) -> None:
        """First message edits the deferred response; the rest are follow-ups.
        Every reply is public."""
        for index, message in enumerate(messages):
            if index == 0:
                self.edit_original(token, message_payload(message))
            else:
                self.follow_up(token, message_payload(message))

    def send_images(self, token: str, pages: Sequence[ImagePage]) -> None:
        """Every page in one message, in place of the deferral."""
        self.edit_original(token, image_payload(pages), files=image_files(pages))

    def send_text(self, token: str, text: str) -> None:
        """`text_payload` in place of the deferral."""
        self.edit_original(token, text_payload(text))

    def edit_original(
        self, token: str, payload: Payload, *, files: Sequence[Attachment] = ()
    ) -> None:
        url = f"{self._webhook(token)}/messages/@original"
        self._request("PATCH", url, payload, files)

    def follow_up(
        self, token: str, payload: Payload, *, files: Sequence[Attachment] = ()
    ) -> None:
        """`files` are sent as `files[n]` next to the payload (multipart)."""
        self._request("POST", self._webhook(token), payload, files)

    def _webhook(self, token: str) -> str:
        return f"{self._base_url}/webhooks/{self._application_id}/{token}"

    def _request(
        self,
        method: str,
        url: str,
        payload: Payload,
        files: Sequence[Attachment] = (),
    ) -> None:
        for _ in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                if files:
                    response = self._http.request(
                        method,
                        url,
                        data={"payload_json": json.dumps(payload)},
                        files=[
                            (f"files[{n}]", (a.filename, a.content, a.content_type))
                            for n, a in enumerate(files)
                        ],
                    )
                else:
                    response = self._http.request(method, url, json=payload)
            except httpx.HTTPError as err:
                raise DiscordError(f"{method} failed: {type(err).__name__}") from None
            if response.status_code != 429:
                if response.is_success:
                    return
                raise DiscordError(
                    f"{method} failed: HTTP {response.status_code}",
                    detail=response.text[:DETAIL_CHARS],
                )
            delay = _retry_after(response)
            if delay is None or delay > MAX_RETRY_AFTER_S:
                raise DiscordError(f"{method} rate limited for too long")
            self._sleep(delay)
        raise DiscordError(f"{method} still rate limited after retries")


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds to wait: the `Retry-After` header, else `retry_after` in the body."""
    header = response.headers.get("Retry-After")
    candidates: list[object] = [header]
    try:
        body = json.loads(response.content)
        if isinstance(body, dict):
            candidates.append(body.get("retry_after"))
    except ValueError:
        pass
    for value in candidates:
        try:
            seconds = float(str(value))
        except ValueError:
            continue
        if seconds >= 0:
            return seconds
    return None
