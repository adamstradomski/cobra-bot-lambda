"""`CacheStore` on Amazon S3 (SPEC §7).

Each object holds the raw body; its `fetched-at` metadata is the fetch time as
UTC epoch seconds. The boto3 client is injected (provided by the Lambda runtime;
a dev dependency for tests only), so this module does not import boto3.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from cobra_bot.cobra.cache import CachedObject

FETCHED_AT = "fetched-at"
MISSING_CODES = frozenset({"NoSuchKey", "404"})


class S3Client(Protocol):
    """The subset of the boto3 S3 client used here.

    Any: boto3 responses are untyped dictionaries.
    """

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, Any]: ...

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        Metadata: Mapping[str, str],
    ) -> Mapping[str, Any]: ...


def error_code(err: Exception) -> str | None:
    """The S3 error code of a botocore ClientError, without importing botocore."""
    response = getattr(err, "response", None)
    if not isinstance(response, Mapping):
        return None
    error = response.get("Error")
    code = error.get("Code") if isinstance(error, Mapping) else None
    return code if isinstance(code, str) else None


class S3CacheStore:
    def __init__(self, client: S3Client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def get(self, key: str) -> CachedObject | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as err:
            if error_code(err) in MISSING_CODES:
                return None
            raise
        body = response["Body"].read()
        return CachedObject(body=body, fetched_at=_fetched_at(response))

    def put(self, key: str, body: bytes, fetched_at: datetime) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={FETCHED_AT: str(int(fetched_at.timestamp()))},
        )


def _fetched_at(response: Mapping[str, Any]) -> datetime:
    """Missing or malformed metadata counts as infinitely old, forcing a refetch."""
    metadata = response.get("Metadata")
    raw = metadata.get(FETCHED_AT) if isinstance(metadata, Mapping) else None
    try:
        return datetime.fromtimestamp(int(str(raw)), tz=UTC)
    except ValueError, OverflowError, OSError:
        return datetime.fromtimestamp(0, tz=UTC)
