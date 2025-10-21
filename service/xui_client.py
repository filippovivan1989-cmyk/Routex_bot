# service/xui_client.py
from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional

import httpx
from httpx import Response


class XuiAuthError(Exception):
    pass


class XuiNotFound(Exception):
    pass


class XuiBadResponse(Exception):
    pass


class XuiClient:
    """
    Клиент к 3x-ui с постоянной cookie-сессией:
    - логин при старте,
    - на любой 401 — один relogin + один ретрай,
    - никогда не шлёт запросы «напрямую» без куки.
    """
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        api_prefix: str = "/panel/api",
        timeout: float = 10.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._prefix = api_prefix.rstrip("/")
        self._username = username
        self._password = password
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=timeout,
            follow_redirects=False,
        )
        self._login_lock = asyncio.Lock()

    async def aclose(self) -> None:
        """Закрывает httpx-клиент (нужно при завершении FastAPI)."""
        await self._client.aclose()


    async def login(self) -> None:
        """Выполнить логин и получить cookie session."""
        async with self._login_lock:
            # логинимся всегда по /login, независимо от префикса
            login_url = f"{self._base}/login"
            r = await self._client.post(
                login_url,
                json={"username": self._username, "password": self._password},
            )
            if r.status_code != 200:
                raise XuiAuthError(f"login failed: {r.status_code} {r.text}")

            # Формально x-ui кладёт Set-Cookie: session=...
            # httpx сам положит её в cookie-jar клиента.


    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
    ) -> Response:
        """Один ретрай при 401: relogin() + повтор."""
        url = f"{self._prefix}{path}"
        r = await self._client.request(method, url, params=params, json=json)
        if r.status_code == 401:
            await self.login()
            r = await self._client.request(method, url, params=params, json=json)
        return r

    # ====== Обёртки по API панели ======

    async def get_inbound(self, inbound_id: int) -> Dict[str, Any]:
        r = await self._request("GET", f"/inbounds/get/{inbound_id}")
        if r.status_code == 404:
            raise XuiNotFound(f"Inbound {inbound_id} not found")
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise XuiBadResponse(f"get_inbound failed: {e.response.status_code} {e.response.text}") from e
        return r.json()

    async def list_inbounds(self) -> Dict[str, Any]:
        r = await self._request("GET", "/inbounds/list")
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise XuiBadResponse(f"list_inbounds failed: {e.response.status_code} {e.response.text}") from e
        return r.json()

    async def update_inbound_settings(self, inbound_id: int, settings_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет settings инбаунда целиком.
        В большинстве сборок 3x-ui действует POST /panel/api/inbounds/update
        с телом: {"id": <inbound_id>, "settings": "<json-string>"}
        """
        import json as _json  # локальный импорт, чтобы не тянуть наверх
        payload = {
            "id": inbound_id,
            "settings": _json.dumps(settings_dict, ensure_ascii=False),
        }
        r = await self._request("POST", "/inbounds/update", json=payload)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Некоторые форки возвращают 200/400 с полезным текстом — отдаём как есть
            raise XuiBadResponse(f"update_inbound_settings failed: {e.response.status_code} {e.response.text}") from e
        return r.json()
