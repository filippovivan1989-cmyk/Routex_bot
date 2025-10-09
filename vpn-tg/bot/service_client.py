from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

import httpx

from .security import build_signature_headers


class ServiceClientError(Exception):
    pass


class NotFoundError(ServiceClientError):
    pass


class ServiceClient:
    def __init__(self, base_url: str, secret: str, *, timeout: float = 20.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._secret = secret

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers: Dict[str, str] = {}
        if json_body is not None:
            body_bytes = json.dumps(json_body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            body_bytes = b""

        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        headers.update(build_signature_headers(self._secret, body_bytes, timestamp=timestamp, nonce=nonce))
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        response = await self._client.request(
            method,
            url,
            params=params,
            content=body_bytes if body_bytes else None,
            headers=headers,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise ServiceClientError('Invalid JSON from service') from exc
        if response.status_code == 404:
            raise NotFoundError(data.get("error", {}).get("message", "Not found"))
        if response.status_code >= 400:
            message = data.get("error", {}).get("message", "Service request failed")
            raise ServiceClientError(message)
        return data

    async def get_key(self, tg_user_id: int, inbound_id: int) -> Dict[str, Any]:
        return await self._request(
            "GET",
            "/api/v1/keys/by-user",
            params={"tg_user_id": tg_user_id, "inbound_id": inbound_id},
        )

    async def issue_key(
        self,
        *,
        tg_user_id: int,
        tg_username: Optional[str],
        protocol: str,
        inbound_id: int,
    ) -> Dict[str, Any]:
        idempotency_key = str(uuid.uuid4())
        payload = {
            "tg_user_id": tg_user_id,
            "tg_username": tg_username,
            "protocol": protocol,
            "inbound_id": inbound_id,
        }
        return await self._request(
            "POST",
            "/api/v1/keys/issue",
            json_body=payload,
            idempotency_key=idempotency_key,
        )

    async def revoke_key(self, tg_user_id: int, inbound_id: int, reason: Optional[str] = None) -> Dict[str, Any]:
        payload = {"tg_user_id": tg_user_id, "inbound_id": inbound_id, "reason": reason}
        return await self._request("POST", "/api/v1/keys/revoke", json_body=payload)

    async def status(self, tg_user_id: int) -> Dict[str, Any]:
        return await self._request("GET", "/api/v1/status", params={"tg_user_id": tg_user_id})
