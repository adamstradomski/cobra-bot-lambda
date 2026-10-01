"""Shared tournament cache over a `CacheStore` (SPEC §7, NFR-02, FR-15, FR-21).

- Fresh entry (age ≤ TTL): served without contacting Cobra.
- Expired or missing: fetch from Cobra, store, serve.
- Cobra unavailable or the tournament now private: serve the cached copy marked
  stale (any age), else re-raise. The cache entry is never overwritten then.
- Not found: re-raised, nothing is cached.

Store failures never block a reply: a failed read counts as a miss, a failed
write is logged.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from cobra_bot.cobra.client import Private, Unavailable

log = logging.getLogger(__name__)

TTL = timedelta(seconds=60)

type Clock = Callable[[], datetime]


@dataclass(frozen=True)
class CachedObject:
    body: bytes
    fetched_at: datetime


class CacheStore(Protocol):
    def get(self, key: str) -> CachedObject | None: ...

    def put(self, key: str, body: bytes, fetched_at: datetime) -> None: ...


class Fetcher(Protocol):
    def fetch_tournament(self, tournament_id: int) -> bytes: ...

    def resolve_shortcode(self, code: str) -> int: ...


@dataclass(frozen=True)
class CacheResult:
    body: bytes  # raw Cobra JSON
    fetched_at: datetime
    stale: bool  # served from cache because Cobra could not provide fresh data
    private: bool  # stale because the tournament is now private (FR-21)


def tournament_key(tournament_id: int) -> str:
    return f"cache/{tournament_id}.json"


def shortcode_key(code: str) -> str:
    return f"codes/{code}.json"


class InMemoryCacheStore:
    """`CacheStore` kept in a dict; for tests and local runs."""

    def __init__(self) -> None:
        self.objects: dict[str, CachedObject] = {}

    def get(self, key: str) -> CachedObject | None:
        return self.objects.get(key)

    def put(self, key: str, body: bytes, fetched_at: datetime) -> None:
        self.objects[key] = CachedObject(body, fetched_at)


class TournamentCache:
    def __init__(
        self, store: CacheStore, fetcher: Fetcher, clock: Clock, ttl: timedelta = TTL
    ) -> None:
        self._store = store
        self._fetcher = fetcher
        self._clock = clock
        self._ttl = ttl

    def tournament(self, tournament_id: int) -> CacheResult:
        """Raises NotFound, Private or Unavailable when there is nothing to serve."""
        key = tournament_key(tournament_id)
        now = self._clock()
        cached = self._read(key)
        if cached is not None and now - cached.fetched_at <= self._ttl:
            return CacheResult(
                cached.body, cached.fetched_at, stale=False, private=False
            )
        try:
            body = self._fetcher.fetch_tournament(tournament_id)
        except Private:
            if cached is None:
                raise
            return CacheResult(cached.body, cached.fetched_at, stale=True, private=True)
        except Unavailable:
            if cached is None:
                raise
            return CacheResult(
                cached.body, cached.fetched_at, stale=True, private=False
            )
        self._write(key, body, now)
        return CacheResult(body, now, stale=False, private=False)

    def shortcode(self, code: str) -> int:
        """Tournament ID for a shortcode.

        The mapping never changes, so it is remembered whenever Cobra resolves it;
        while the tournament is private or Cobra is down, the remembered ID is used.
        """
        key = shortcode_key(code)
        try:
            tournament_id = self._fetcher.resolve_shortcode(code)
        except Private, Unavailable:
            remembered = self._remembered_id(key)
            if remembered is None:
                raise
            return remembered
        self._write(key, json.dumps({"id": tournament_id}).encode(), self._clock())
        return tournament_id

    def _remembered_id(self, key: str) -> int | None:
        cached = self._read(key)
        if cached is None:
            return None
        try:
            value = json.loads(cached.body).get("id")
        except ValueError, AttributeError:
            return None
        return value if isinstance(value, int) else None

    def _read(self, key: str) -> CachedObject | None:
        try:
            return self._store.get(key)
        except Exception:
            log.warning(
                "cache read failed for %s; treating as a miss", key, exc_info=True
            )
            return None

    def _write(self, key: str, body: bytes, fetched_at: datetime) -> None:
        try:
            self._store.put(key, body, fetched_at)
        except Exception:
            log.warning("cache write failed for %s", key, exc_info=True)
