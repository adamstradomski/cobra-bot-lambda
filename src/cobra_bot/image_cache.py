"""Cache of drawn reply images, separate from the Cobra data cache (SPEC §7).

The Cobra cache keeps tournament data for 60 s. Drawing the images is the slow
part of a reply, and when the data has not changed the images would be drawn
the same again, so they are kept for 10 minutes on their own:

- Key: `images/{sha256}.png`, the hash of exactly what the image shows
  (`formatting.image.table_key`: cells, colours, layout, fonts, renderer version).
  Changed data draws a new image; unchanged data reuses it, however often the
  Cobra cache refreshes. The embed text around it (header, `Data from …`) is
  built fresh for every reply.
- Fresh (age ≤ 10 min): served. Older or missing: drawn and stored.
- Store failures never block a reply: a failed read counts as a miss, a failed
  write is logged.
"""

import logging
from collections.abc import Callable
from datetime import timedelta

from cobra_bot.cobra.cache import CacheStore, Clock

log = logging.getLogger(__name__)

IMAGE_TTL = timedelta(minutes=10)
PREFIX = "images/"


def image_key(table_key: str) -> str:
    return f"{PREFIX}{table_key}.png"


class ImageCache:
    def __init__(self, store: CacheStore, clock: Clock, ttl: timedelta = IMAGE_TTL):
        self._store = store
        self._clock = clock
        self._ttl = ttl
        self.hits = 0  # since this instance was made; the Worker logs the change
        self.misses = 0

    def png(self, table_key: str, draw: Callable[[], bytes]) -> bytes:
        """The cached PNG for `table_key`, else `draw()`, stored."""
        key = image_key(table_key)
        try:
            cached = self._store.get(key)
        except Exception:
            log.warning("image cache read failed; drawing", exc_info=True)
            cached = None
        if cached is not None and self._clock() - cached.fetched_at <= self._ttl:
            self.hits += 1
            return cached.body
        self.misses += 1
        png = draw()
        try:
            self._store.put(key, png, self._clock())
        except Exception:
            log.warning("image cache write failed", exc_info=True)
        return png
