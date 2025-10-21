import time

import pytest

from bot.security import make_signature
from service.security import SignatureError, verify_hmac


def test_hmac_signature_verification() -> None:
    secret = "secret"
    body = b'{"hello":"world"}'
    timestamp = str(int(time.time()))
    nonce = "abc123"

    signature = make_signature(secret, timestamp, nonce, body)
    headers = {
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
    }

    verify_hmac(headers, body, secret=secret)


def test_hmac_invalid_signature() -> None:
    secret = "secret"
    body = b"{}"
    timestamp = str(int(time.time()))
    headers = {
        "X-Timestamp": timestamp,
        "X-Nonce": "nonce",
        "X-Signature": "invalid",
    }

    with pytest.raises(SignatureError):
        verify_hmac(headers, body, secret=secret)
