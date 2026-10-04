import pytest
from nacl.signing import SigningKey

from cobra_bot.discord.verify import SignatureVerifier

pytestmark = pytest.mark.req("NFR-07")


BODY = b'{"type": 1}'
TIMESTAMP = "1790856000"


@pytest.fixture(scope="module")
def key() -> SigningKey:
    return SigningKey.generate()


def _verifier(key: SigningKey) -> SignatureVerifier:
    return SignatureVerifier(key.verify_key.encode().hex())


def _headers(
    key: SigningKey, body: bytes = BODY, ts: str = TIMESTAMP
) -> dict[str, str]:
    signature = key.sign(ts.encode() + body).signature.hex()
    return {"X-Signature-Ed25519": signature, "X-Signature-Timestamp": ts}


def test_valid_signature(key: SigningKey) -> None:
    assert _verifier(key).verify(_headers(key), BODY)


def test_header_names_are_case_insensitive(key: SigningKey) -> None:
    headers = {k.lower(): v for k, v in _headers(key).items()}

    assert _verifier(key).verify(headers, BODY)


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(lambda h, b: (h, b + b" "), id="body-changed"),
        pytest.param(
            lambda h, b: ({**h, "X-Signature-Timestamp": "1790856001"}, b),
            id="timestamp-changed",
        ),
        pytest.param(
            lambda h, b: ({**h, "X-Signature-Ed25519": "00" * 64}, b),
            id="wrong-signature",
        ),
        pytest.param(
            lambda h, b: ({**h, "X-Signature-Ed25519": "not hex"}, b), id="not-hex"
        ),
        pytest.param(
            lambda h, b: ({**h, "X-Signature-Ed25519": "abcd"}, b), id="too-short"
        ),
    ],
)
def test_invalid_signature(key: SigningKey, tamper: object) -> None:
    headers, body = tamper(_headers(key), BODY)  # type: ignore[operator]

    assert not _verifier(key).verify(headers, body)


def test_signature_from_another_key(key: SigningKey) -> None:
    other = SigningKey.generate()

    assert not _verifier(key).verify(_headers(other), BODY)


@pytest.mark.parametrize(
    "missing", ["X-Signature-Ed25519", "X-Signature-Timestamp"], ids=["sig", "ts"]
)
def test_missing_header(key: SigningKey, missing: str) -> None:
    headers = _headers(key)
    del headers[missing]

    assert not _verifier(key).verify(headers, BODY)


def test_empty_header(key: SigningKey) -> None:
    headers = {**_headers(key), "X-Signature-Ed25519": ""}

    assert not _verifier(key).verify(headers, BODY)


@pytest.mark.parametrize("bad_key", ["", "zz", "ab" * 31])
def test_invalid_public_key_is_rejected_at_startup(bad_key: str) -> None:
    with pytest.raises(ValueError, match="invalid Discord public key"):
        SignatureVerifier(bad_key)
