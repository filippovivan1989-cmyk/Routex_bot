import json
import os
from typing import Any, Dict, List

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("SERVICE_HMAC_SECRET", "test_secret")

from service.app import app, settings  # noqa: E402
from service.security import make_signature  # noqa: E402


class MockResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any]):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Dict[str, Any]:
        return self._payload


class MockRunner:
    def __init__(self) -> None:
        self.calls: List[str] = []
        self._created = False
        self.payload = {
            "data": {
                "uri": "vless://example",
                "qr_png_base64": None,
                "panel_user_id": "42",
                "active": True,
            }
        }

    async def call(self, name: str, **kwargs: Any) -> MockResponse:
        self.calls.append(name)
        if name == settings.postman_mapping["find_by_user"]:
            if not self._created:
                return MockResponse(404, {"error": "not found"})
            return MockResponse(200, self.payload)
        if name == settings.postman_mapping["create_for_user"]:
            self._created = True
            return MockResponse(200, self.payload)
        if name == settings.postman_mapping["status_by_user"]:
            return MockResponse(200, {"data": {"active": True}})
        raise AssertionError(f"Unexpected call: {name}")


def sign_headers(body: bytes) -> Dict[str, str]:
    import time
    timestamp = str(int(time.time()))
    nonce = "nonce"
    signature = make_signature(settings.hmac_secret, timestamp, nonce, body)
    return {
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
    }


@pytest.mark.asyncio
async def test_issue_flow() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        mock_runner = MockRunner()
        app.state.postman_runner = mock_runner

        # First lookup returns 404
        headers = sign_headers(b"")
        response = await client.get(
            "/api/v1/keys/by-user",
            params={"tg_user_id": 1, "inbound_id": 1},
            headers=headers,
        )
        assert response.status_code == 404, response.json()
        assert response.json()["error"]["code"] == "not_found"

        # Issue new key
        payload = {"tg_user_id": 1, "tg_username": "user", "protocol": "vless", "inbound_id": 1}
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = sign_headers(body)
        headers["Idempotency-Key"] = "test-key"
        headers["Content-Type"] = "application/json"

        response = await client.post("/api/v1/keys/issue", content=body, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "created"
        assert data["delivery"]["uri"] == "vless://example"

        # Subsequent lookup returns existing key
        headers = sign_headers(b"")
        response = await client.get(
            "/api/v1/keys/by-user",
            params={"tg_user_id": 1, "inbound_id": 1},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["delivery"]["uri"] == "vless://example"

        assert mock_runner.calls.count(settings.postman_mapping["find_by_user"]) >= 2
        assert settings.postman_mapping["create_for_user"] in mock_runner.calls
