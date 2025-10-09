from __future__ import annotations

import hmac
import time
from hashlib import sha256
from typing import Mapping

from fastapi import HTTPException


class SignatureError(Exception):
    """Raised when HMAC validation fails."""


def make_signature(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    if secret is None:
        raise ValueError("HMAC secret must be provided")
    message = f"{timestamp}:{nonce}:".encode("utf-8") + body
    signature = hmac.new(secret.encode("utf-8"), message, sha256)
    return signature.hexdigest()


def verify_hmac(
    headers: Mapping[str, str],
    body: bytes,
    *,
    secret: str,
    max_age_seconds: int | None = 300,
) -> None:
    timestamp = headers.get("X-Timestamp")
    nonce = headers.get("X-Nonce")
    signature = headers.get("X-Signature")

    if not (timestamp and nonce and signature):
        raise SignatureError("Missing HMAC headers")

    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise SignatureError("Invalid timestamp") from exc

    if max_age_seconds is not None:
        now = int(time.time())
        if abs(now - timestamp_value) > max_age_seconds:
            raise SignatureError("Timestamp is out of allowed window")

    expected = make_signature(secret, timestamp, nonce, body)
    if not hmac.compare_digest(expected, signature):
        raise SignatureError("Invalid signature")


def ensure_hmac(headers: Mapping[str, str], body: bytes, *, secret: str) -> None:
    try:
        verify_hmac(headers, body, secret=secret)
    except SignatureError as exc:
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": str(exc)}) from exc
