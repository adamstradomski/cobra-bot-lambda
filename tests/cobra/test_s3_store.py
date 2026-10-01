import io
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import boto3  # type: ignore[import-untyped]  # dev dependency without stubs
import pytest
from botocore.response import StreamingBody  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]

from cobra_bot.cobra.cache import CachedObject
from cobra_bot.cobra.s3_store import S3CacheStore

BUCKET = "cobra-cache"
KEY = "cache/4909.json"
FETCHED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
EPOCH = "1790856000"


@pytest.fixture
def s3() -> Iterator[tuple[Any, Stubber]]:
    # Any: the boto3 client is untyped. Dummy credentials; Stubber blocks the network.
    client = boto3.client(
        "s3",
        region_name="eu-central-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with Stubber(client) as stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(io.BytesIO(data), len(data))


def test_hit(s3: tuple[Any, Stubber]) -> None:
    client, stubber = s3
    stubber.add_response(
        "get_object",
        {"Body": _body(b'{"a": 1}'), "Metadata": {"fetched-at": EPOCH}},
        {"Bucket": BUCKET, "Key": KEY},
    )

    assert S3CacheStore(client, BUCKET).get(KEY) == CachedObject(b'{"a": 1}', FETCHED)


def test_miss(s3: tuple[Any, Stubber]) -> None:
    client, stubber = s3
    stubber.add_client_error(
        "get_object", service_error_code="NoSuchKey", http_status_code=404
    )

    assert S3CacheStore(client, BUCKET).get(KEY) is None


def test_other_errors_propagate(s3: tuple[Any, Stubber]) -> None:
    client, stubber = s3
    stubber.add_client_error(
        "get_object", service_error_code="AccessDenied", http_status_code=403
    )

    with pytest.raises(Exception, match="AccessDenied"):
        S3CacheStore(client, BUCKET).get(KEY)


def test_missing_metadata_counts_as_expired(s3: tuple[Any, Stubber]) -> None:
    client, stubber = s3
    stubber.add_response("get_object", {"Body": _body(b"{}"), "Metadata": {}})

    cached = S3CacheStore(client, BUCKET).get(KEY)

    assert cached is not None
    assert cached.fetched_at == datetime.fromtimestamp(0, tz=UTC)


def test_put(s3: tuple[Any, Stubber]) -> None:
    client, stubber = s3
    stubber.add_response(
        "put_object",
        {},
        {
            "Bucket": BUCKET,
            "Key": KEY,
            "Body": b'{"a": 1}',
            "ContentType": "application/json",
            "Metadata": {"fetched-at": EPOCH},
        },
    )

    S3CacheStore(client, BUCKET).put(KEY, b'{"a": 1}', FETCHED)
