"""Split a Document into Discord embeds and messages (SPEC §9, FR-14).

Limits: embed description ≤ 4096 chars; per message ≤ 10 embeds and ≤ 6000
chars in total (title + descriptions); at most 5 messages. Entries are never
split across embeds. When everything does not fit, entries are dropped from the
end and the last line of the last message says how many, with a Cobra link.
"""

from dataclasses import dataclass

from cobra_bot import messages
from cobra_bot.formatting.document import Document

ELLIPSIS = "…"


@dataclass(frozen=True)
class Limits:
    description: int = 4096
    title: int = 256
    embeds_per_message: int = 10
    chars_per_message: int = 6000
    messages: int = 5


@dataclass(frozen=True)
class Embed:
    description: str
    title: str | None = None
    url: str | None = None

    @property
    def chars(self) -> int:
        """Characters Discord counts towards the per-message total."""
        return len(self.title or "") + len(self.description)


type Message = tuple[Embed, ...]

DISCORD_LIMITS = Limits()


def chunk(doc: Document, limits: Limits = DISCORD_LIMITS) -> tuple[Message, ...]:
    title = _clip(doc.title, limits.title)
    blocks = [*doc.header, *doc.entries]
    packed = _pack(blocks, title, doc.url, limits)
    if packed is not None:
        return packed
    # Keep the longest prefix of entries that still fits with the omission line.
    # Fit is monotone in the number of kept entries, so binary search it.
    lo, hi = 0, len(doc.entries)
    best: tuple[Message, ...] | None = None
    while lo <= hi:
        kept = (lo + hi) // 2
        omitted = messages.omitted_entries(len(doc.entries) - kept, doc.url)
        attempt = _pack(
            [*doc.header, *doc.entries[:kept], omitted], title, doc.url, limits
        )
        if attempt is None:
            hi = kept - 1
        else:
            best, lo = attempt, kept + 1
    if best is None:
        raise ValueError("header does not fit in the message limits")
    return best


def _pack(
    blocks: list[str], title: str, url: str, limits: Limits
) -> tuple[Message, ...] | None:
    """Greedy packing; None if more than `limits.messages` messages are needed."""
    max_block = min(limits.description, limits.chars_per_message - len(title))
    result: list[Message] = []
    embeds: list[Embed] = []
    lines: list[str] = []
    message_chars = 0  # chars of closed embeds in the current message
    first = True  # the current embed is the first one and carries the title

    def current() -> Embed:
        if first:
            return Embed("\n".join(lines), title=title, url=url)
        return Embed("\n".join(lines))

    for raw in blocks:
        block = _clip(raw, max_block)
        candidate = "\n".join([*lines, block])
        title_chars = len(title) if first else 0
        if len(candidate) <= limits.description and (
            message_chars + title_chars + len(candidate) <= limits.chars_per_message
        ):
            lines.append(block)
            continue
        # Close the current embed and start a new one with this block.
        embed = current()
        embeds.append(embed)
        message_chars += embed.chars
        first = False
        if (
            len(embeds) >= limits.embeds_per_message
            or message_chars + len(block) > limits.chars_per_message
        ):
            result.append(tuple(embeds))
            if len(result) >= limits.messages:
                return None
            embeds, message_chars = [], 0
        lines = [block]
    embeds.append(current())
    result.append(tuple(embeds))
    return tuple(result)


def _clip(text: str, limit: int) -> str:
    """Last-resort guard for a single pathological block or title."""
    return text if len(text) <= limit else text[: limit - len(ELLIPSIS)] + ELLIPSIS
