"""Split a Document into Discord messages of one embed each (SPEC §9, FR-14).

The table fills the embed description, then fields; each of them carries its own
```ansi code block, so every part renders on its own. Limits: description ≤ 4096
chars, field value ≤ 1024, ≤ 25 fields, ≤ 6000 chars per message (title,
description, field names and values, footer); at most 5 messages. Entries are
never split. When everything does not fit, entries are dropped from the end and
the last line of the last message says how many, with a Cobra link.
"""

from dataclasses import dataclass, field

from cobra_bot import messages
from cobra_bot.formatting.document import EMBED_COLOR, Document, Entry
from cobra_bot.formatting.text import ELLIPSIS

FENCE_OPEN = "```ansi\n"
FENCE_CLOSE = "\n```"
# Discord requires a field name; a zero-width space renders as nothing.
FIELD_NAME = "​"


@dataclass(frozen=True)
class Limits:
    description: int = 4096
    title: int = 256
    field_value: int = 1024
    fields: int = 25
    footer: int = 2048
    chars_per_message: int = 6000
    messages: int = 5


@dataclass(frozen=True)
class Embed:
    description: str
    title: str | None = None
    url: str | None = None
    fields: tuple[str, ...] = ()  # field values; every field is named FIELD_NAME
    footer: str | None = None
    color: int | None = None

    @property
    def chars(self) -> int:
        """Characters Discord counts towards the per-message total."""
        return (
            len(self.title or "")
            + len(self.description)
            + sum(len(FIELD_NAME) + len(value) for value in self.fields)
            + len(self.footer or "")
        )


type Message = tuple[Embed, ...]

DISCORD_LIMITS = Limits()


def chunk(doc: Document, limits: Limits = DISCORD_LIMITS) -> tuple[Message, ...]:
    title = _clip(doc.title, limits.title)
    footer = _clip(doc.footer, limits.footer)
    packed = _Packer(doc, title, footer, limits).pack(doc.entries, doc.notes)
    if packed is not None:
        return packed
    # Keep the longest prefix of entries that still fits with the omission line.
    # Fit is monotone in the number of kept entries, so binary search it.
    lo, hi = 0, len(doc.entries)
    best: tuple[Message, ...] | None = None
    while lo <= hi:
        kept = (lo + hi) // 2
        omitted = messages.omitted_entries(len(doc.entries) - kept, doc.url)
        attempt = _Packer(doc, title, footer, limits).pack(
            doc.entries[:kept], (*doc.notes, omitted)
        )
        if attempt is None:
            hi = kept - 1
        else:
            best, lo = attempt, kept + 1
    if best is None:
        raise ValueError("header does not fit in the message limits")
    return best


@dataclass
class _Part:
    """The description or a field being filled: markdown, code block, markdown."""

    prefix: str = ""  # markdown above the code block (the document header)
    lines: list[str] = field(default_factory=list)  # code block lines
    suffix: str = ""  # markdown below the code block (the notes)

    @property
    def empty(self) -> bool:
        return not (self.prefix or self.lines or self.suffix)

    def render(self) -> str:
        parts = [self.prefix] if self.prefix else []
        if self.lines:
            parts.append(FENCE_OPEN + "\n".join(self.lines) + FENCE_CLOSE)
        if self.suffix:
            parts.append(self.suffix)
        return "\n".join(parts)


class _Packer:
    """Greedy packing into messages of one embed: a description, then fields."""

    def __init__(self, doc: Document, title: str, footer: str, limits: Limits) -> None:
        self._doc = doc
        self._title = title
        self._footer = footer
        self._limits = limits
        self._done: list[list[str]] = []  # finished messages, as rendered parts
        self._parts: list[str] = []  # rendered parts of the open message
        header = "\n".join(doc.header)
        self._open = _Part(prefix=_clip(header, limits.description))
        self._columns = list(doc.columns)  # until the first entry is placed

    def pack(
        self, entries: tuple[Entry, ...], notes: tuple[str, ...]
    ) -> tuple[Message, ...] | None:
        """The messages, or None if more than `limits.messages` are needed."""
        for entry in entries:
            if not self._place_entry(entry):
                return None
        if notes and not self._place_notes("\n".join(notes)):
            return None
        if not self._open.empty:
            self._parts.append(self._open.render())
        self._done.append(self._parts)
        return tuple(self._message(i, parts) for i, parts in enumerate(self._done))

    def _place_entry(self, entry: Entry) -> bool:
        body = entry.text.split("\n")
        while True:
            lines = self._open.lines
            if lines:
                candidate = [*lines, *([""] if entry.gap else []), *body]
            else:
                candidate = [*self._columns, *body]
            if self._fits(_Part(self._open.prefix, candidate)):
                self._open.lines = candidate
                self._columns = []
                return True
            if self._open.empty and not self._parts:
                # A fresh description cannot hold the entry: clip it (last resort).
                room = self._room(_Part(lines=[*self._columns, ""]))
                if room <= 0:
                    raise ValueError("table columns do not fit in the message limits")
                body = _clip(entry.text, room).split("\n")
                continue
            if not self._advance():
                return False

    def _place_notes(self, notes: str) -> bool:
        while True:
            candidate = _Part(self._open.prefix, self._open.lines, notes)
            if self._fits(candidate):
                self._open = candidate
                return True
            if self._open.empty and not self._parts:
                notes = _clip(notes, self._room(_Part()))
                continue
            if not self._advance():
                return False

    def _advance(self) -> bool:
        """Close the open part; open a field, or a new message if needed."""
        if not self._open.empty:
            self._parts.append(self._open.render())
            self._open = _Part()
            if len(self._parts) <= self._limits.fields:
                return True  # a field may still fit; _fits decides
        # Callers never advance from an empty description, so the message has parts.
        self._done.append(self._parts)
        self._parts = []
        return len(self._done) < self._limits.messages

    def _cap(self) -> int:
        return self._limits.description if not self._parts else self._limits.field_value

    def _used(self) -> int:
        """Chars of the open message outside the open part."""
        used = len(self._footer) + (len(self._title) if not self._done else 0)
        if self._parts:
            # The description, the closed fields, and the name of the open field.
            used += sum(len(p) for p in self._parts)
            used += len(self._parts) * len(FIELD_NAME)
        return used

    def _room(self, part: _Part) -> int:
        """How many more chars `part` could take."""
        rendered = len(part.render())
        return min(
            self._cap() - rendered,
            self._limits.chars_per_message - self._used() - rendered,
        )

    def _fits(self, part: _Part) -> bool:
        return self._room(part) >= 0

    def _message(self, index: int, parts: list[str]) -> Message:
        description, *fields = parts
        first = index == 0
        return (
            Embed(
                description=description,
                title=self._title if first else None,
                url=self._doc.url if first else None,
                fields=tuple(fields),
                footer=self._footer or None,
                color=EMBED_COLOR,
            ),
        )


def _clip(text: str, limit: int) -> str:
    """Last-resort guard for a single pathological block, title or footer."""
    return text if len(text) <= limit else text[: limit - len(ELLIPSIS)] + ELLIPSIS
