import logging
from datetime import UTC, datetime, timedelta

import pytest

from cobra_bot.cobra.cache import (
    CachedObject,
    CacheResult,
    InMemoryCacheStore,
    TournamentCache,
    lock_key,
    shortcode_key,
    tournament_key,
)
from cobra_bot.cobra.client import NotFound, Private, Unavailable

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
FRESH = b'{"name": "fresh"}'
OLD = b'{"name": "old"}'


class FakeClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeFetcher:
    """Counts calls; raises `error` if set, else returns `body`."""

    def __init__(self, body: bytes = FRESH, error: Exception | None = None) -> None:
        self.body = body
        self.error = error
        self.shortcode_id = 5018
        self.calls: list[object] = []

    def fetch_tournament(self, tournament_id: int) -> bytes:
        self.calls.append(tournament_id)
        if self.error:
            raise self.error
        return self.body

    def resolve_shortcode(self, code: str) -> int:
        self.calls.append(code)
        if self.error:
            raise self.error
        return self.shortcode_id


class BrokenStore:
    def get(self, key: str) -> CachedObject | None:
        raise OSError("S3 down")

    def put(self, key: str, body: bytes, fetched_at: datetime) -> None:
        raise OSError("S3 down")

    def acquire_lock(self, key: str, now: datetime, abandoned_after: timedelta) -> bool:
        raise OSError("S3 down")

    def release_lock(self, key: str) -> None:
        raise OSError("S3 down")


def _cache(
    fetcher: FakeFetcher, store: InMemoryCacheStore | None = None
) -> tuple[TournamentCache, InMemoryCacheStore, FakeClock]:
    store = store or InMemoryCacheStore()
    clock = FakeClock()
    return TournamentCache(store, fetcher, clock), store, clock


def _with_old_entry(minutes: int = 10) -> InMemoryCacheStore:
    store = InMemoryCacheStore()
    store.put(tournament_key(1), OLD, T0 - timedelta(minutes=minutes))
    return store


# --- AC-16 ------------------------------------------------------------------------


@pytest.mark.req("NFR-02", "AC-16")
def test_ac16_second_request_within_ttl_uses_cache_and_after_ttl_refetches() -> None:
    fetcher = FakeFetcher()
    cache, _, clock = _cache(fetcher)

    cache.tournament(1)
    clock.advance(60)
    assert cache.tournament(1) == CacheResult(FRESH, T0, stale=False, private=False)
    assert len(fetcher.calls) == 1

    clock.advance(1)  # 61 s after the fetch
    cache.tournament(1)
    assert len(fetcher.calls) == 2


def test_fetched_body_is_stored_with_fetch_time() -> None:
    cache, store, _ = _cache(FakeFetcher())

    cache.tournament(7)

    assert store.objects[tournament_key(7)] == CachedObject(FRESH, T0)


# --- AC-17 ------------------------------------------------------------------------


@pytest.mark.req("FR-15", "AC-17")
def test_ac17_failing_fetch_serves_old_entry_marked_stale() -> None:
    store = _with_old_entry(minutes=10)
    cache, _, _ = _cache(FakeFetcher(error=Unavailable("down")), store)

    result = cache.tournament(1)

    assert result == CacheResult(
        OLD, T0 - timedelta(minutes=10), stale=True, private=False
    )


@pytest.mark.req("FR-15", "AC-17")
def test_ac17_failing_fetch_without_cache_raises_unavailable() -> None:
    cache, _, _ = _cache(FakeFetcher(error=Unavailable("down")))

    with pytest.raises(Unavailable):
        cache.tournament(1)


@pytest.mark.req("AC-17")
def test_ac17_not_found_is_raised_and_not_cached() -> None:
    store = _with_old_entry()
    cache, _, _ = _cache(FakeFetcher(error=NotFound("gone")), store)

    with pytest.raises(NotFound):
        cache.tournament(1)
    with pytest.raises(NotFound):
        cache.tournament(2)
    assert set(store.objects) == {tournament_key(1)}


# --- AC-25 (FR-21) ----------------------------------------------------------------


@pytest.mark.req("FR-21", "AC-25")
def test_ac25_private_tournament_serves_cache_marked_private_and_keeps_entry() -> None:
    store = _with_old_entry(minutes=10)
    before = dict(store.objects)
    cache, _, _ = _cache(FakeFetcher(error=Private("401")), store)

    result = cache.tournament(1)

    assert (result.body, result.stale, result.private) == (OLD, True, True)
    assert store.objects == before


@pytest.mark.req("FR-21", "AC-25")
def test_ac25_private_tournament_without_cache_raises_private() -> None:
    cache, _, _ = _cache(FakeFetcher(error=Private("401")))

    with pytest.raises(Private):
        cache.tournament(1)


# --- store failures ---------------------------------------------------------------


def test_broken_store_still_serves_from_cobra(caplog: pytest.LogCaptureFixture) -> None:
    fetcher = FakeFetcher()
    cache = TournamentCache(BrokenStore(), fetcher, FakeClock())

    with caplog.at_level(logging.WARNING):
        result = cache.tournament(1)

    assert result.body == FRESH
    assert "cache read failed" in caplog.text
    assert "cache write failed" in caplog.text


# --- shortcodes -------------------------------------------------------------------


@pytest.mark.req("FR-12")
def test_shortcode_is_resolved_and_remembered() -> None:
    cache, store, _ = _cache(FakeFetcher())

    assert cache.shortcode("QNSF") == 5018
    assert store.objects[shortcode_key("QNSF")].body == b'{"id": 5018}'


@pytest.mark.parametrize("error", [Private("private"), Unavailable("down")])
def test_remembered_shortcode_is_used_when_cobra_cannot_resolve(
    error: Exception,
) -> None:
    fetcher = FakeFetcher()
    cache, _, _ = _cache(fetcher)
    cache.shortcode("N9WI")

    fetcher.error = error

    assert cache.shortcode("N9WI") == 5018


@pytest.mark.parametrize("error", [Private("private"), Unavailable("down")])
def test_unknown_shortcode_without_memory_reraises(error: Exception) -> None:
    cache, _, _ = _cache(FakeFetcher(error=error))

    with pytest.raises(type(error)):
        cache.shortcode("N9WI")


def test_unknown_shortcode_is_not_found_even_if_remembered() -> None:
    fetcher = FakeFetcher()
    cache, _, _ = _cache(fetcher)
    cache.shortcode("QNSF")
    fetcher.error = NotFound("gone")

    with pytest.raises(NotFound):
        cache.shortcode("QNSF")


def test_corrupt_shortcode_entry_is_ignored() -> None:
    store = InMemoryCacheStore()
    store.put(shortcode_key("QNSF"), b"not json", T0)
    cache, _, _ = _cache(FakeFetcher(error=Private("private")), store)

    with pytest.raises(Private):
        cache.shortcode("QNSF")


# --- single-flight (T17, NFR-03) ----------------------------------------------------


class SleepingClock(FakeClock):
    """A clock whose sleep advances time and can run a hook on each call."""

    def __init__(self) -> None:
        super().__init__()
        self.sleeps = 0
        self.on_sleep: list[object] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps += 1
        self.advance(seconds)
        for hook in self.on_sleep:
            hook(self)  # type: ignore[operator]


def _single_flight(
    fetcher: FakeFetcher, store: InMemoryCacheStore
) -> tuple[TournamentCache, SleepingClock]:
    clock = SleepingClock()
    return TournamentCache(store, fetcher, clock, sleep=clock.sleep), clock


def _locked_store(cached_minutes_ago: int | None = 10) -> InMemoryCacheStore:
    store = (
        _with_old_entry(cached_minutes_ago)
        if cached_minutes_ago is not None
        else InMemoryCacheStore()
    )
    store.locks[lock_key(1)] = T0  # another worker is fetching right now
    return store


@pytest.mark.req("NFR-03", "AC-18")
def test_ac18_waiting_caller_gets_fresh_object_without_http() -> None:
    store = _locked_store()
    fetcher = FakeFetcher()
    cache, clock = _single_flight(fetcher, store)

    def winner_finishes(c: SleepingClock) -> None:
        if c.sleeps == 2:
            store.put(tournament_key(1), FRESH, c.now)

    clock.on_sleep.append(winner_finishes)

    result = cache.tournament(1)

    assert fetcher.calls == []
    assert (result.body, result.stale) == (FRESH, False)
    assert clock.now - T0 <= timedelta(seconds=2)


def test_lock_held_and_nothing_new_serves_older_copy_after_2_s() -> None:
    fetcher = FakeFetcher()
    cache, clock = _single_flight(fetcher, _locked_store(cached_minutes_ago=2))

    result = cache.tournament(1)

    assert fetcher.calls == []
    assert (result.body, result.stale) == (OLD, False)
    assert clock.now - T0 == timedelta(seconds=2)


def test_lock_held_and_nothing_cached_fetches_after_waiting() -> None:
    fetcher = FakeFetcher()
    cache, _ = _single_flight(fetcher, _locked_store(cached_minutes_ago=None))

    assert cache.tournament(1).body == FRESH
    assert fetcher.calls == [1]


def test_winner_takes_and_releases_the_lock() -> None:
    store = InMemoryCacheStore()
    taken: list[bool] = []

    class Spy(FakeFetcher):
        def fetch_tournament(self, tournament_id: int) -> bytes:
            taken.append(lock_key(tournament_id) in store.locks)
            return super().fetch_tournament(tournament_id)

    cache, _ = _single_flight(Spy(), store)
    cache.tournament(1)

    assert taken == [True]
    assert store.locks == {}


def test_lock_is_released_when_the_fetch_fails() -> None:
    store = InMemoryCacheStore()
    cache, _ = _single_flight(FakeFetcher(error=Unavailable("down")), store)

    with pytest.raises(Unavailable):
        cache.tournament(1)
    assert store.locks == {}


@pytest.mark.req("NFR-03")
def test_abandoned_lock_is_taken_over() -> None:
    store = _locked_store()
    store.locks[lock_key(1)] = T0 - timedelta(seconds=16)
    fetcher = FakeFetcher()
    cache, clock = _single_flight(fetcher, store)

    assert cache.tournament(1).body == FRESH
    assert fetcher.calls == [1]
    assert clock.sleeps == 0


def test_broken_lock_fetches_without_waiting() -> None:
    fetcher = FakeFetcher()
    clock = SleepingClock()
    cache = TournamentCache(BrokenStore(), fetcher, clock, sleep=clock.sleep)

    assert cache.tournament(1).body == FRESH
    assert clock.sleeps == 0
