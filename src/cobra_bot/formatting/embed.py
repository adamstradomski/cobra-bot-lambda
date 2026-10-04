"""Discord embeds of a reply: an image page or an embed without an image
(docs/spec/output.md)."""

from dataclasses import dataclass, field

EMBED_COLOR = 0xE0B23A
MAX_PAGES = 5  # image pages per reply; the rest are counted in the last one (FR-14)


@dataclass(frozen=True)
class Embed:
    description: str
    title: str | None = None
    url: str | None = None
    footer: str | None = None
    color: int | None = None
    image: str | None = None  # filename of an attached image shown in the embed


@dataclass(frozen=True)
class ImagePage:
    """One page of an image reply (`formatting.image`): an embed showing the PNG
    attached as `filename`."""

    embed: Embed
    filename: str
    png: bytes = field(repr=False)
