"""The image cache: 10 minutes, its own prefix, never blocking a reply."""

import logging
from datetime import datetime, timedelta

import pytest

from builders import FETCHED_AT
from cobra_bot.cobra.cache import CachedObject, InMemoryCacheStore
from cobra_bot.image_cache import IMAGE_TTL, ImageCache, image_key


class Clock:
    def __init__(self) -> None:
        self.now = FETCHED_AT

    def __call__(self) -> datetime:
        return self.now


class Drawer:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> bytes:
        self.calls += 1
        return f"png-{self.calls}".encode()


def _cache() -> tuple[ImageCache, InMemoryCacheStore, Clock, Drawer]:
    store, clock = InMemoryCacheStore(), Clock()
    return ImageCache(store, clock), store, clock, Drawer()


def test_ttl_is_ten_minutes() -> None:
    assert timedelta(minutes=10) == IMAGE_TTL


def test_miss_draws_and_stores_under_its_own_prefix() -> None:
    images, store, _, draw = _cache()

    assert images.png("abc", draw) == b"png-1"

    assert store.objects == {"images/abc.png": CachedObject(b"png-1", FETCHED_AT)}
    assert image_key("abc") == "images/abc.png"
    assert (images.hits, images.misses) == (0, 1)


@pytest.mark.parametrize(
    ("age", "drawn"),
    [
        (timedelta(0), 1),
        (timedelta(minutes=10), 1),  # exactly the TTL: still fresh
        (timedelta(minutes=10, seconds=1), 2),  # past it: drawn again
    ],
)
def test_reuse_within_ten_minutes(age: timedelta, drawn: int) -> None:
    images, store, clock, draw = _cache()
    images.png("abc", draw)
    clock.now = FETCHED_AT + age

    images.png("abc", draw)

    assert draw.calls == drawn
    assert store.objects["images/abc.png"].fetched_at == (
        FETCHED_AT if drawn == 1 else clock.now
    )


def test_other_key_draws() -> None:
    images, _, _, draw = _cache()
    images.png("abc", draw)

    assert images.png("def", draw) == b"png-2"


class Broken(InMemoryCacheStore):
    def __init__(self, *, read: bool = False, write: bool = False) -> None:
        super().__init__()
        self.fail_read, self.fail_write = read, write

    def get(self, key: str) -> CachedObject | None:
        if self.fail_read:
            raise OSError("s3 down")
        return super().get(key)

    def put(self, key: str, body: bytes, fetched_at: datetime) -> None:
        if self.fail_write:
            raise OSError("s3 down")
        super().put(key, body, fetched_at)


def test_read_failure_draws_and_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    images, draw = ImageCache(Broken(read=True), Clock()), Drawer()

    with caplog.at_level(logging.WARNING):
        assert images.png("abc", draw) == b"png-1"

    assert "image cache read failed" in caplog.text


def test_write_failure_still_returns_the_image(
    caplog: pytest.LogCaptureFixture,
) -> None:
    images, draw = ImageCache(Broken(write=True), Clock()), Drawer()

    with caplog.at_level(logging.WARNING):
        assert images.png("abc", draw) == b"png-1"

    assert "image cache write failed" in caplog.text


def test_draw_failure_is_not_swallowed() -> None:
    """Only store failures are; a bug in drawing reaches the Worker's handler."""
    images, _, _, _ = _cache()

    def broken() -> bytes:
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        images.png("abc", broken)
