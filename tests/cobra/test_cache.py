import logging
from datetime import UTC, datetime, timedelta

import pytest

from cobra_bot.cobra.cache import (
    CachedObject,
    CacheResult,
    InMemoryCacheStore,
    TournamentCache,
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


def test_ac17_failing_fetch_serves_old_entry_marked_stale() -> None:
    store = _with_old_entry(minutes=10)
    cache, _, _ = _cache(FakeFetcher(error=Unavailable("down")), store)

    result = cache.tournament(1)

    assert result == CacheResult(
        OLD, T0 - timedelta(minutes=10), stale=True, private=False
    )


def test_ac17_failing_fetch_without_cache_raises_unavailable() -> None:
    cache, _, _ = _cache(FakeFetcher(error=Unavailable("down")))

    with pytest.raises(Unavailable):
        cache.tournament(1)


def test_ac17_not_found_is_raised_and_not_cached() -> None:
    store = _with_old_entry()
    cache, _, _ = _cache(FakeFetcher(error=NotFound("gone")), store)

    with pytest.raises(NotFound):
        cache.tournament(1)
    with pytest.raises(NotFound):
        cache.tournament(2)
    assert set(store.objects) == {tournament_key(1)}


# --- AC-25 (FR-21) ----------------------------------------------------------------


def test_ac25_private_tournament_serves_cache_marked_private_and_keeps_entry() -> None:
    store = _with_old_entry(minutes=10)
    before = dict(store.objects)
    cache, _, _ = _cache(FakeFetcher(error=Private("401")), store)

    result = cache.tournament(1)

    assert (result.body, result.stale, result.private) == (OLD, True, True)
    assert store.objects == before


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
