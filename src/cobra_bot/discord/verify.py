"""Ed25519 verification of Discord interaction requests (NFR-07;
docs/spec/architecture.md).

Discord signs `timestamp + body` with the application's key and sends the
signature in `X-Signature-Ed25519` and the timestamp in `X-Signature-Timestamp`.
Anything missing or malformed is simply "not verified"; the handler answers 401.
"""

from collections.abc import Mapping

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

SIGNATURE_HEADER = "x-signature-ed25519"
TIMESTAMP_HEADER = "x-signature-timestamp"


class SignatureVerifier:
    def __init__(self, public_key_hex: str) -> None:
        """Raises ValueError if the configured key is not a 32-byte hex string."""
        try:
            self._key = VerifyKey(bytes.fromhex(public_key_hex))
        except Exception as err:
            raise ValueError("invalid Discord public key") from err

    def verify(self, headers: Mapping[str, str], body: bytes) -> bool:
        lowered = {k.lower(): v for k, v in headers.items()}
        signature = lowered.get(SIGNATURE_HEADER)
        timestamp = lowered.get(TIMESTAMP_HEADER)
        if not signature or not timestamp:
            return False
        try:
            self._key.verify(timestamp.encode() + body, bytes.fromhex(signature))
        except BadSignatureError, ValueError, TypeError:
            return False
        return True
