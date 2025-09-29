"""Tests for the XUI client integration."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from typing import Any, Dict
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from routex_bot.db import Database
from routex_bot.services.xui_client import XUIClient, ensure_or_create_key


class _MockResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> Dict[str, Any]:
        return self._payload


class XUIClientCreateTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = XUIClient("https://panel", "user", "pass", inbound_id=77)
        self.client._session_cookie = "sid=123"  # bypass login
        self.addAsyncCleanup(self.client.close)

    async def test_create_client_sends_settings_and_returns_uuid(self) -> None:
        expected_uuid = "11111111-2222-3333-4444-555555555555"
        remark = "routex-12345"
        response_payload = {
            "obj": {
                "clientStats": [{"clientId": expected_uuid, "remark": remark}],
                "settings": json.dumps(
                    {
                        "clients": [
                            {
                                "id": expected_uuid,
                                "uuid": expected_uuid,
                                "remark": remark,
                            }
                        ]
                    }
                ),
            }
        }
        mock_response = _MockResponse(200, response_payload)

        with patch("routex_bot.services.xui_client.uuid.uuid4", return_value=uuid.UUID(expected_uuid)):
            self.client._client.post = AsyncMock(return_value=mock_response)
            key = await self.client.create_client(12345)

        self.assertEqual(key, expected_uuid)
        self.client._client.post.assert_awaited_once()
        _, kwargs = self.client._client.post.call_args
        self.assertEqual(kwargs["headers"], {"Cookie": "sid=123"})
        request_payload = kwargs["json"]
        self.assertEqual(request_payload["id"], 77)
        self.assertEqual(request_payload["remark"], remark)
        self.assertTrue(request_payload["enable"])
        settings = json.loads(request_payload["settings"])
        client_settings = settings["clients"][0]
        self.assertEqual(client_settings["id"], expected_uuid)
        self.assertEqual(client_settings["uuid"], expected_uuid)
        self.assertEqual(client_settings["remark"], remark)


class EnsureOrCreateKeyTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        db_path = os.path.join(self.tmpdir.name, "test.sqlite3")
        self.db = Database(db_path)
        await self.db.connect()
        await self.db.init_models()
        self.addAsyncCleanup(self.db.close)

        self.client = XUIClient("https://panel", "user", "pass", inbound_id=42)
        self.client._session_cookie = "sid=abc"
        self.addAsyncCleanup(self.client.close)

    async def test_ensure_or_create_key_creates_remote_client(self) -> None:
        expected_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        remark = "routex-999"
        response_payload = {
            "obj": {
                "clientStats": [{"clientId": expected_uuid, "remark": remark}],
                "settings": json.dumps(
                    {
                        "clients": [
                            {
                                "id": expected_uuid,
                                "uuid": expected_uuid,
                                "remark": remark,
                            }
                        ]
                    }
                ),
            }
        }
        mock_response = _MockResponse(200, response_payload)
        self.client._client.post = AsyncMock(return_value=mock_response)
        self.client.fetch_client_by_remark = AsyncMock(return_value=None)

        with patch("routex_bot.services.xui_client.uuid.uuid4", return_value=uuid.UUID(expected_uuid)):
            key = await ensure_or_create_key(self.db, self.client, 999)

        self.assertEqual(key, expected_uuid)
        self.client._client.post.assert_awaited_once()
        user = await self.db.get_user(999)
        assert user is not None
        self.assertEqual(user["key"], expected_uuid)
