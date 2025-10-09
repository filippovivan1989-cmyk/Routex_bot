from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import httpx

logger = logging.getLogger(__name__)


def _extract_items(items: Iterable[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    flattened: Dict[str, Mapping[str, Any]] = {}
    for item in items:
        if "item" in item:
            flattened.update(_extract_items(item["item"]))
        else:
            name = item.get("name")
            if name:
                flattened[name] = item
    return flattened


class PostmanRunner:
    def __init__(
        self,
        collection_path: Path,
        *,
        environment_path: Optional[Path] = None,
        timeout: float = 20.0,
    ) -> None:
        if not collection_path.exists():
            raise FileNotFoundError(f"Postman collection not found: {collection_path}")
        with collection_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        self._requests = _extract_items(data.get("item", []))

        self._env: Dict[str, str] = {}
        if environment_path and environment_path.exists():
            with environment_path.open("r", encoding="utf-8") as fp:
                env_data = json.load(fp)
            for value in env_data.get("values", []):
                if value.get("enabled", True):
                    self._env[value["key"]] = value.get("value", "")

        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def call(
        self,
        name: str,
        *,
        path_params: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Mapping[str, Any]] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
    ) -> httpx.Response:
        if name not in self._requests:
            raise KeyError(f"Request '{name}' not found in Postman collection")

        request_def = self._requests[name]["request"]
        method = request_def.get("method", "GET")
        url_info = request_def.get("url")
        if isinstance(url_info, str):
            raw_url = url_info
        else:
            raw_url = url_info.get("raw", "")
        if not raw_url:
            raise ValueError(f"Request '{name}' is missing URL definition")

        url = self._prepare_url(raw_url, path_params or {}, query or {})

        headers = {header["key"]: header.get("value", "") for header in request_def.get("header", []) if header.get("key")}
        if extra_headers:
            headers.update(extra_headers)

        response = await self._client.request(method, url, json=json_body, headers=headers)
        return response

    def _prepare_url(
        self,
        raw_url: str,
        path_params: Mapping[str, Any],
        query_params: Mapping[str, Any],
    ) -> str:
        url = self._substitute_env(raw_url)
        for key, value in path_params.items():
            pattern = re.compile(rf"[:{{]{{1}}{re.escape(key)}[}}]?")
            url = pattern.sub(str(value), url)
        if query_params:
            url = self._append_query_params(url, query_params)
        return url

    def _substitute_env(self, raw: str) -> str:
        result = raw
        for key, value in self._env.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result

    def _append_query_params(self, url: str, query: Mapping[str, Any]) -> str:
        separator = '&' if '?' in url else '?'
        query_parts = []
        for key, value in query.items():
            if value is None:
                continue
            query_parts.append(f"{key}={httpx.QueryParams({key: value})[key]}")
        return url + (separator + '&'.join(query_parts) if query_parts else '')
