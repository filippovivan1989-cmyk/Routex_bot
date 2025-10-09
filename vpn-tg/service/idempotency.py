from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class CachedResponse:
    status_code: int
    content: Dict[str, Any]
    expires_at: float


class IdempotencyCache:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._storage: Dict[str, CachedResponse] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Tuple[int, Dict[str, Any]]]:
        async with self._lock:
            cached = self._storage.get(key)
            if not cached:
                return None
            if cached.expires_at < time.time():
                del self._storage[key]
                return None
            return cached.status_code, cached.content

    async def set(self, key: str, status_code: int, content: Dict[str, Any]) -> None:
        async with self._lock:
            self._storage[key] = CachedResponse(
                status_code=status_code,
                content=content,
                expires_at=time.time() + self._ttl,
            )

    async def clear(self) -> None:
        async with self._lock:
            self._storage.clear()
