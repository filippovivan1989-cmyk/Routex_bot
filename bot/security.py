from __future__ import annotations

import hmac
from hashlib import sha256


def make_signature(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    message = f"{timestamp}:{nonce}:".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, sha256).hexdigest()


def build_signature_headers(secret: str, body: bytes, *, timestamp: str, nonce: str) -> dict[str, str]:
    signature = make_signature(secret, timestamp, nonce, body)
    return {"X-Timestamp": timestamp, "X-Nonce": nonce, "X-Signature": signature}
