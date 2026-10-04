"""Shared tournament cache over a `CacheStore` (docs/spec/cache.md; NFR-02,
FR-15, FR-21).

- Fresh entry (age ≤ `TTL`, 60 s): served without contacting Cobra.
- Expired or missing: fetch from Cobra, store, serve.
- Cobra unavailable or the tournament now private: serve the cached copy marked
  stale (any age), else re-raise. The cache entry is never overwritten then.
- Not found: re-raised, nothing is cached.
- Single-flight (NFR-03): before fetching, take `locks/{id}`. If another caller
  holds it, wait up to 2 s for a fresh entry, then serve whatever is cached, else
  fetch anyway. A lock older than 15 s is abandoned and may be taken over.

Store failures never block a reply: a failed read counts as a miss, a failed
write is logged, and a failed lock operation means fetching without the lock.
"""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Protocol, TypeGuard

from cobra_bot.cobra.client import Private, Unavailable

log = logging.getLogger(__name__)

TTL = timedelta(seconds=60)
LOCK_WAIT = timedelta(seconds=2)
LOCK_POLL = timedelta(seconds=0.25)
LOCK_ABANDONED_AFTER = timedelta(seconds=15)

type Clock = Callable[[], datetime]
type Sleep = Callable[[float], None]


@dataclass(frozen=True)
class CachedObject:
    body: bytes
    fetched_at: datetime


class CacheStore(Protocol):
    def get(self, key: str) -> CachedObject | None: ...

    def put(self, key: str, body: bytes, fetched_at: datetime) -> None: ...

    def acquire_lock(self, key: str, now: datetime, abandoned_after: timedelta) -> bool:
        """Create the lock if absent (or abandoned); False if someone holds it."""
        ...

    def release_lock(self, key: str) -> None: ...


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


def lock_key(tournament_id: int) -> str:
    return f"locks/{tournament_id}"


class _Lock(Enum):
    ACQUIRED = auto()
    HELD_ELSEWHERE = auto()
    UNAVAILABLE = auto()  # the store failed; proceed without a lock


class InMemoryCacheStore:
    """`CacheStore` kept in a dict; for tests and local runs."""

    def __init__(self) -> None:
        self.objects: dict[str, CachedObject] = {}
        self.locks: dict[str, datetime] = {}

    def get(self, key: str) -> CachedObject | None:
        return self.objects.get(key)

    def put(self, key: str, body: bytes, fetched_at: datetime) -> None:
        self.objects[key] = CachedObject(body, fetched_at)

    def acquire_lock(self, key: str, now: datetime, abandoned_after: timedelta) -> bool:
        taken = self.locks.get(key)
        if taken is not None and now - taken <= abandoned_after:
            return False
        self.locks[key] = now
        return True

    def release_lock(self, key: str) -> None:
        self.locks.pop(key, None)


class TournamentCache:
    def __init__(
        self,
        store: CacheStore,
        fetcher: Fetcher,
        clock: Clock,
        sleep: Sleep = time.sleep,
        ttl: timedelta = TTL,
    ) -> None:
        self._store = store
        self._fetcher = fetcher
        self._clock = clock
        self._sleep = sleep
        self._ttl = ttl

    def tournament(self, tournament_id: int) -> CacheResult:
        """Raises NotFound, Private or Unavailable when there is nothing to serve."""
        key = tournament_key(tournament_id)
        cached = self._read(key)
        if self._is_fresh(cached):
            return _served(cached)
        lock = self._acquire(lock_key(tournament_id))
        if lock is _Lock.HELD_ELSEWHERE:
            waited = self._wait_for_fresh(key)
            if waited is not None:
                return _served(waited)
            if cached is not None:
                return _served(cached)  # older than the TTL, but no failure occurred
        try:
            return self._fetch(tournament_id, key, cached)
        finally:
            if lock is _Lock.ACQUIRED:
                self._release(lock_key(tournament_id))

    def _fetch(
        self, tournament_id: int, key: str, cached: CachedObject | None
    ) -> CacheResult:
        now = self._clock()
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

    def _is_fresh(self, cached: CachedObject | None) -> TypeGuard[CachedObject]:
        return cached is not None and self._clock() - cached.fetched_at <= self._ttl

    def _wait_for_fresh(self, key: str) -> CachedObject | None:
        deadline = self._clock() + LOCK_WAIT
        while self._clock() < deadline:
            self._sleep(LOCK_POLL.total_seconds())
            cached = self._read(key)
            if self._is_fresh(cached):
                return cached
        return None

    def _acquire(self, key: str) -> _Lock:
        try:
            if self._store.acquire_lock(key, self._clock(), LOCK_ABANDONED_AFTER):
                return _Lock.ACQUIRED
            return _Lock.HELD_ELSEWHERE
        except Exception:
            log.warning("lock failed for %s; fetching without it", key, exc_info=True)
            return _Lock.UNAVAILABLE

    def _release(self, key: str) -> None:
        try:
            self._store.release_lock(key)
        except Exception:
            log.warning("lock release failed for %s", key, exc_info=True)

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


def _served(cached: CachedObject) -> CacheResult:
    return CacheResult(cached.body, cached.fetched_at, stale=False, private=False)
