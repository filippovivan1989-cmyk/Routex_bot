import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routex_bot.services.xui_client import XUIClient


class DummyResponse:
    def __init__(self, *, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers: dict[str, str] = {}
        self.text = json.dumps(self._payload)

    def json(self) -> dict:
        return self._payload


class DummyHTTPClient:
    def __init__(self, response: DummyResponse):
        self._response = response
        self.last_request = None

    async def get(self, url: str, *, headers: dict | None = None):
        self.last_request = {"url": url, "headers": headers or {}}
        return self._response


def test_fetch_client_by_remark_handles_nested_data():
    client = XUIClient("https://panel", "login", "password")
    client._session_cookie = "session=abc"
    payload = {
        "obj": {
            "data": {
                "inbounds": [
                    {
                        "clientStats": [
                            {
                                "remark": "routex-111",
                                "uuid": "00000000-0000-0000-0000-000000000111",
                            },
                            {
                                "remark": "routex-222",
                                "uuid": "00000000-0000-0000-0000-000000000222",
                            },
                        ]
                    }
                ]
            }
        }
    }
    client._client = DummyHTTPClient(DummyResponse(payload=payload))

    assert (
        asyncio.run(client.fetch_client_by_remark(222))
        == "00000000-0000-0000-0000-000000000222"
    )


def test_fetch_client_by_remark_reads_settings_clients():
    client = XUIClient("https://panel", "login", "password")
    client._session_cookie = "session=abc"
    payload = {
        "obj": {
            "data": [
                {
                    "settings": json.dumps(
                        {
                            "clients": [
                                {
                                    "remark": "routex-123",
                                    "clientId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                                },
                                {
                                    "remark": "routex-999",
                                    "clientId": "ffffffff-1111-2222-3333-444444444444",
                                },
                            ]
                        }
                    )
                }
            ]
        }
    }
    client._client = DummyHTTPClient(DummyResponse(payload=payload))

    assert (
        asyncio.run(client.fetch_client_by_remark(123))
        == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    )
    assert asyncio.run(client.fetch_client_by_remark(321)) is None
