"""Client for interacting with X-UI/py3xui panel."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable

import httpx
from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from routex_bot.db import Database


class XUIError(Exception):
    """Raised when X-UI API returns an unexpected response."""


class XUIClient:
    """Thin wrapper around X-UI/py3xui HTTP API."""

    def __init__(self, base_url: str, login: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.login = login
        self.password = password
        self._client = httpx.AsyncClient(timeout=10.0)
        self._session_cookie: str | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def ensure_logged_in(self) -> None:
        if self._session_cookie:
            return
        response = await self._client.post(
            f"{self.base_url}/login",
            data={"username": self.login, "password": self.password},
        )
        if response.status_code != 200:
            raise XUIError(f"Не удалось авторизоваться в панели: {response.text}")
        self._session_cookie = response.headers.get("set-cookie")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, XUIError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def fetch_client_by_remark(self, tg_id: int) -> str | None:
        """Return client's UUID from panel by remark or ``None`` if absent."""

        await self.ensure_logged_in()
        headers = {"Cookie": self._session_cookie} if self._session_cookie else {}
        remark = f"routex-{tg_id}"
        response = await self._client.get(
            f"{self.base_url}/xui/inbound/list",
            headers=headers,
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise XUIError(
                f"Ошибка панели при получении клиента: {response.status_code} {response.text}"
            )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise XUIError("Панель вернула некорректный JSON при поиске клиента") from exc
        obj = payload.get("obj") if isinstance(payload, dict) else None
        if not obj:
            return None

        def _iter_clients(items: Iterable[Any]) -> Iterable[Dict[str, Any]]:
            for item in items:
                if not isinstance(item, dict):
                    continue
                stats = item.get("clientStats")
                if isinstance(stats, list):
                    for stat in stats:
                        if isinstance(stat, dict):
                            yield stat
                settings = item.get("settings")
                if isinstance(settings, str):
                    try:
                        settings = json.loads(settings)
                    except json.JSONDecodeError:
                        settings = None
                if isinstance(settings, dict):
                    clients = settings.get("clients")
                    if isinstance(clients, list):
                        for client in clients:
                            if isinstance(client, dict):
                                yield client

        def _looks_like_uuid(value: Any) -> bool:
            return isinstance(value, str) and value.count("-") >= 4 and len(value) >= 8

        for client in _iter_clients(obj if isinstance(obj, list) else [obj]):
            if client.get("remark") != remark:
                continue
            for key in ("clientId", "uuid", "id"):
                candidate = client.get(key)
                if _looks_like_uuid(candidate):
                    return candidate
        return None

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, XUIError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def create_client(self, tg_id: int) -> str:
        """Create a VPN client in X-UI and return its key/UUID."""

        await self.ensure_logged_in()
        headers = {"Cookie": self._session_cookie} if self._session_cookie else {}
        payload = {
            "remark": f"routex-{tg_id}",
            "enable": True,
            "expiryTime": 0,
        }
        response = await self._client.post(
            f"{self.base_url}/xui/inbound/addClient",
            headers=headers,
            json=payload,
        )
        if response.status_code not in {200, 201}:
            raise XUIError(f"Ошибка панели: {response.status_code} {response.text}")
        data = response.json()
        key = data.get("obj", {}).get("clientId") or data.get("obj", {}).get("uuid")
        if not key:
            raise XUIError("Панель не вернула ключ клиента")
        return key


async def ensure_or_create_key(db: Database, client: XUIClient, tg_id: int) -> str:
    """Return existing key from DB or create a new one via X-UI."""

    user = await db.ensure_user(tg_id)
    try:
        remote_key = await client.fetch_client_by_remark(tg_id)
    except RetryError as exc:  # pragma: no cover - defensive
        inner_exc = exc.last_attempt.exception() if exc.last_attempt else exc
        raise XUIError("Не удалось получить ключ из панели") from inner_exc
    if remote_key:
        if user["key"] != remote_key:
            await db.update_user_key(tg_id, remote_key)
        return remote_key
    if user["key"]:
        # локальный ключ устарел, но клиента в панели нет — выпускаем новый
        await db.clear_user_key(tg_id)
    try:
        key = await client.create_client(tg_id)
    except RetryError as exc:  # pragma: no cover - defensive
        inner_exc = exc.last_attempt.exception() if exc.last_attempt else exc
        raise XUIError("Не удалось создать ключ после нескольких попыток") from inner_exc
    await db.update_user_key(tg_id, key)
    return key


__all__ = ["XUIClient", "XUIError", "ensure_or_create_key"]
