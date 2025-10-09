import asyncio

import pytest

from service.idempotency import IdempotencyCache


@pytest.mark.asyncio
async def test_idempotency_cache_reuses_response() -> None:
    cache = IdempotencyCache(ttl_seconds=300)
    key = "abc"
    payload = {"status": "ok"}

    await cache.set(key, 200, payload)
    cached = await cache.get(key)
    assert cached == (200, payload)


@pytest.mark.asyncio
async def test_idempotency_cache_expires() -> None:
    cache = IdempotencyCache(ttl_seconds=1)
    key = "xyz"
    payload = {"status": "ok"}

    await cache.set(key, 200, payload)
    await asyncio.sleep(1.1)
    cached = await cache.get(key)
    assert cached is None
