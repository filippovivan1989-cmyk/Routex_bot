# service/app.py
from __future__ import annotations

import logging
import os
import json
import uuid as uuidlib
from urllib.parse import quote
from pathlib import Path
from typing import Any, Dict, Optional
from contextlib import asynccontextmanager

import yaml
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .xui_client import XuiClient, XuiNotFound, XuiBadResponse
from .idempotency import IdempotencyCache
from .mapping import MappingError, normalize_key_payload, normalize_revoke_payload, normalize_status_payload
from .postman_runner import PostmanRunner
from .security import SignatureError, verify_hmac

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("service")

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "config"
load_dotenv(CONFIG_DIR / ".env")


class ServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class IssueRequest(BaseModel):
    tg_user_id: int = Field(..., description="Telegram user id")
    tg_username: Optional[str] = Field(None, description="Telegram username")
    protocol: Optional[str] = Field(None, description="VPN protocol to issue")
    inbound_id: Optional[int] = Field(None, description="Inbound identifier")


class RevokeRequest(BaseModel):
    tg_user_id: int
    inbound_id: int
    reason: Optional[str] = Field(None, description="Reason of revocation")


class ServiceSettings(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080)
    hmac_secret: str
    timeout: float = Field(default=20.0)
    postman_mapping: Dict[str, str]
    defaults: Dict[str, Any]


with (CONFIG_DIR / "config.yaml").open("r", encoding="utf-8") as fp:
    yaml_config = yaml.safe_load(fp) or {}

settings = ServiceSettings(
    host=os.getenv("SERVICE_HOST", "0.0.0.0"),
    port=int(os.getenv("SERVICE_PORT", "8080")),
    hmac_secret=os.getenv("SERVICE_HMAC_SECRET", ""),
    timeout=float(os.getenv("HTTP_TIMEOUT_SECONDS", yaml_config.get("timeout", 20))),
    postman_mapping=yaml_config.get("postman_mapping", {}),
    defaults=yaml_config.get("defaults", {}),
)

if not settings.hmac_secret:
    raise RuntimeError("SERVICE_HMAC_SECRET must be set")

collection_path = CONFIG_DIR / "postman.collection.json"
environment_path = CONFIG_DIR / "postman.environment.json"

# === Хелперы/обработчики ошибок ===

app_exception_logger = logging.getLogger("service.exceptions")

async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "error": {"code": exc.code, "message": exc.message}},
    )


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail or {}
    if isinstance(detail, dict):
        code = detail.get("code", "http_error")
        message = detail.get("message", detail.get("detail", ""))
    else:
        code = "http_error"
        message = str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "error": {"code": code, "message": message}},
    )


# FastAPI создадим ниже (после описания lifespan); хэндлеры регистрируем после app = FastAPI(...)

async def hmac_guard(request: Request) -> None:
    body = await request.body()
    try:
        verify_hmac(request.headers, body, secret=settings.hmac_secret)
    except SignatureError as exc:
        raise ServiceError(401, "unauthorized", str(exc)) from exc


def _extract_clients_from_inbound(payload: dict) -> list[dict]:
    """
    В 3x-ui клиенты лежат в obj.settings.clients[], а obj.settings приходит строкой JSON.
    Поддерживаем разные формы ответа (fork-и иногда заворачивают в data/obj).
    """
    candidates = [
        payload,
        payload.get("data") or {},
        (payload.get("data") or {}).get("obj") or {},
        payload.get("obj") or {},
    ]
    obj = {}
    for c in candidates:
        if isinstance(c, dict) and "settings" in c:
            obj = c
            break
    settings_raw = obj.get("settings")
    if settings_raw is None:
        return []
    if isinstance(settings_raw, str):
        try:
            settings_parsed = json.loads(settings_raw)
        except Exception:
            return []
    elif isinstance(settings_raw, dict):
        settings_parsed = settings_raw
    else:
        return []
    clients = settings_parsed.get("clients") or []
    return clients if isinstance(clients, list) else []


def _find_client_uuid(clients: list[dict], email: str) -> str | None:
    for c in clients:
        if isinstance(c, dict) and str(c.get("email", "")).lower() == email.lower():
            cid = c.get("id")
            if isinstance(cid, str) and len(cid) >= 8:
                return cid
    return None


def _merge_client_into_settings(inbound_payload: dict, new_client: dict) -> dict:
    """
    Возвращает НОВЫЙ dict settings со вставленным/обновлённым клиентом.
    """
    # достанем settings из inbound_payload
    obj = (inbound_payload.get("data") or {}).get("obj") or inbound_payload.get("obj") or {}
    settings_raw = obj.get("settings")
    if isinstance(settings_raw, str):
        try:
            s = json.loads(settings_raw)
        except Exception:
            s = {}
    elif isinstance(settings_raw, dict):
        s = settings_raw.copy()
    else:
        s = {}

    clients_list = s.get("clients") or []
    if not isinstance(clients_list, list):
        clients_list = []

    # если такой email уже есть — заменим id, иначе добавим
    replaced = False
    for i, c in enumerate(clients_list):
        if isinstance(c, dict) and str(c.get("email", "")).lower() == str(new_client.get("email", "")).lower():
            clients_list[i] = new_client
            replaced = True
            break
    if not replaced:
        clients_list.append(new_client)

    s["clients"] = clients_list
    return s


def _build_vless_uri(host: str, uuid: str, email: str, defaults: dict) -> str:
    """
    vless://<UUID>@HOST:PORT?type=tcp&encryption=none&security=reality
      &pbk=...&fp=chrome&sni=...&sid=...&spx=%2F#<email_urlencoded>
    """
    vless_host = host or defaults.get("public_host") or "185.254.190.58"
    vless_port = int(defaults.get("vless_port") or 443)
    pbk = defaults.get("reality_pbk") or "z5DopT_JthDMuQYIlrnttFTc2hlFmJd1Tkq6bhH7niE"
    sni = defaults.get("reality_sni") or "www.googletagmanager.com"
    fp = defaults.get("reality_fp") or "chrome"
    sid = defaults.get("reality_sid") or "3484e9e698f44c88"
    spx = defaults.get("reality_spx") or "/"
    _ = spx  # spx кодируется как %2F согласно ТЗ
    query = (
        "type=tcp&encryption=none&security=reality"
        f"&pbk={pbk}&fp={fp}&sni={sni}&sid={sid}&spx=%2F"
    )
    return f"vless://{uuid}@{vless_host}:{vless_port}?{query}#{quote(email, safe='')}"

# ====== Унифицированный обработчик ошибок панели ======
async def handle_panel_error(response: Any) -> None:
    """
    Унифицированный прокси-обработчик ошибок из PostmanRunner.
    Ставит код панели в наш формат {"status":"error","error":{...}}.
    """
    try:
        payload = response.json()
    except Exception:
        payload = {}
    message = payload.get("error") if isinstance(payload, dict) else None
    raise ServiceError(response.status_code, "panel_error", message or "Upstream request failed")


# ====== Инициализация (lifespan) и DI ======

def _build_xui() -> XuiClient:
    base = os.getenv("XUI_BASE_URL", "http://127.0.0.1:54321")
    user = os.getenv("XUI_USERNAME")
    pwd = os.getenv("XUI_PASSWORD")
    pref = os.getenv("XUI_API_PREFIX", "/panel/api")
    if not (user and pwd):
        raise RuntimeError("XUI_USERNAME/XUI_PASSWORD must be set in .env")
    return XuiClient(base, user, pwd, api_prefix=pref, timeout=10.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.idempotency_cache = IdempotencyCache(ttl_seconds=300)

    # 1) XuiClient (обязателен)
    xui_client: Optional[XuiClient] = None
    try:
        xui_client = _build_xui()
        await xui_client.login()
    except Exception as exc:  # noqa: BLE001 - хотим отлавливать любые ошибки старта
        logger.warning("XUI client disabled", extra={"reason": str(exc)})
        xui_client = None
    app.state.xui = xui_client

    # 2) PostmanRunner (опционален, для старых эндпоинтов)
    app.state.postman_runner = None
    if collection_path.exists():
        try:
            app.state.postman_runner = PostmanRunner(
                collection_path,
                environment_path=environment_path if environment_path.exists() else None,
                timeout=settings.timeout,
            )
            logger.info("Postman runner initialized", extra={"collection": str(collection_path)})
        except Exception:
            logger.exception("Failed to initialize Postman runner")
    else:
        logger.warning("Postman collection is not provided at %s", collection_path)

    try:
        yield
    finally:
        runner: Optional[PostmanRunner] = getattr(app.state, "postman_runner", None)
        if runner:
            await runner.aclose()
        xui_from_state: Optional[XuiClient] = getattr(app.state, "xui", None)
        if xui_from_state:
            await xui_from_state.aclose()


app = FastAPI(title="VPN Service Adapter", lifespan=lifespan)

# значения по умолчанию, если lifespan не успел выполниться
app.state.idempotency_cache = IdempotencyCache(ttl_seconds=300)
app.state.postman_runner = None
app.state.xui = None

# регистрируем exception handlers
app.add_exception_handler(ServiceError, service_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)


def get_runner() -> PostmanRunner:
    runner: Optional[PostmanRunner] = getattr(app.state, "postman_runner", None)
    if runner is None:
        raise ServiceError(503, "service_unavailable", "Postman runner is not configured")
    return runner


# ====== Роуты ======

@app.get("/health")
async def healthcheck() -> dict[str, str]:
    xui: Optional[XuiClient] = getattr(app.state, "xui", None)
    if not xui:
        return {"status": "degraded", "xui": "not_configured"}
    try:
        _ = await xui.list_inbounds()
        return {"status": "ok", "xui": "up"}
    except Exception as e:
        return {"status": "degraded", "xui": f"error: {e!s}"}


@app.get("/api/v1/keys/by-user", dependencies=[Depends(hmac_guard)])
async def get_key_by_user(
    request: Request,
    tg_user_id: int | None = None,
    inbound_id: int | None = None,
    email: str | None = None,
    nickname: str | None = None,
) -> Dict[str, Any]:
    """
    1) GET /panel/api/inbounds/get/:inbound_id — читаем клиентов
    2) Ищем по email (или nickname@routex)
    3) Если нет — обновляем settings: добавляем клиента (UUID + email)
    4) Возвращаем {status, action, client{email, uuid}, delivery_uri}
    """
    inbound_id = inbound_id or settings.defaults.get("inbound_id")
    if not inbound_id:
        raise ServiceError(400, "bad_request", "inbound_id is required")

    # Если указали email/nickname — работаем напрямую через XUI (создаём при необходимости)
    user_email = (email or (f"{nickname}@routex" if nickname else None))
    if user_email:
        user_email = user_email.lower()
        xui_client: Optional[XuiClient] = getattr(request.app.state, "xui", None)
        if not xui_client:
            raise ServiceError(503, "service_unavailable", "XUI client is not configured")

        try:
            inbound_payload = await xui_client.get_inbound(int(inbound_id))
        except XuiNotFound:
            raise ServiceError(404, "not_found", "Inbound not found")
        except (XuiBadResponse, Exception) as e:
            raise ServiceError(502, "panel_error", f"Failed to read inbound: {e!s}")

        clients = _extract_clients_from_inbound(inbound_payload)
        uuid = _find_client_uuid(clients, user_email)
        action = "existing"

        if not uuid:
            new_uuid = str(uuidlib.uuid4())
            new_client = {"id": new_uuid, "email": user_email}
            new_settings = _merge_client_into_settings(inbound_payload, new_client)

            try:
                await xui_client.update_inbound_settings(int(inbound_id), new_settings)
            except (XuiBadResponse, Exception) as e:
                raise ServiceError(502, "panel_error", f"Failed to update inbound settings: {e!s}")

            try:
                reread_payload = await xui_client.get_inbound(int(inbound_id))
            except (XuiNotFound, XuiBadResponse, Exception) as e:
                raise ServiceError(502, "panel_error", f"Failed to reread inbound: {e!s}")

            clients2 = _extract_clients_from_inbound(reread_payload)
            uuid = _find_client_uuid(clients2, user_email)
            if not uuid:
                raise ServiceError(502, "panel_error", "Client was created but not found on reread")
            action = "created"

        delivery_uri = _build_vless_uri(settings.defaults.get("public_host"), uuid, user_email, settings.defaults)
        raw_payload = {
            "data": {
                "email": user_email,
                "uuid": uuid,
                "panel_user_id": uuid,
                "active": True,
                "uri": delivery_uri,
            }
        }
        try:
            normalized = normalize_key_payload(raw_payload)
        except MappingError as exc:
            logger.error(
                "xui_mapping_failed",
                extra={"raw_payload": raw_payload, "reason": str(exc), "tg_user_id": tg_user_id},
            )
            normalized = {"client": {}, "delivery": None, "raw": raw_payload}

        return {"status": "ok", "action": action, **normalized}

    # Иначе — старый режим через Postman коллекцию
    if tg_user_id is None:
        raise ServiceError(400, "bad_request", "tg_user_id or email is required")

    runner = get_runner()
    mapping_name = settings.postman_mapping.get("find_by_user")
    if not mapping_name:
        raise ServiceError(500, "configuration_error", "Mapping for find_by_user is missing")

    response = await runner.call(
        mapping_name,
        query={"tg_user_id": tg_user_id, "inbound_id": inbound_id},
    )
    if response.status_code == 404:
        raise ServiceError(404, "not_found", "Client not found")
    if response.status_code >= 400:
        await handle_panel_error(response)

    base_payload = response.json()
    try:
        normalized = normalize_key_payload(base_payload)
    except MappingError as exc:
        logger.error(
            "find_mapping_failed",
            extra={"raw_panel_payload": base_payload, "reason": str(exc), "tg_user_id": tg_user_id},
        )
        normalized = {"client": {}, "delivery": None, "raw": base_payload}

    return {"status": "ok", "action": "existing", **normalized}


# — Остальные эндпоинты остаются на PostmanRunner (как у тебя было)

@app.post("/api/v1/keys/issue", dependencies=[Depends(hmac_guard)])
async def issue_key(request: Request, payload: IssueRequest) -> JSONResponse:
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise ServiceError(400, "missing_idempotency_key", "Idempotency-Key header is required")

    cache: IdempotencyCache = app.state.idempotency_cache
    cached = await cache.get(idempotency_key)
    if cached:
        status_code, content = cached
        logger.info(
            "idempotent_cache_hit",
            extra={"idempotency_key": idempotency_key, "tg_user_id": payload.tg_user_id},
        )
        return JSONResponse(status_code=status_code, content=content)

    runner = get_runner()
    mapping_find = settings.postman_mapping.get("find_by_user")
    mapping_create = settings.postman_mapping.get("create_for_user")
    if not mapping_find or not mapping_create:
        raise ServiceError(500, "configuration_error", "Mapping for find/create is missing")

    inbound_id = payload.inbound_id or settings.defaults.get("inbound_id")
    protocol = payload.protocol or settings.defaults.get("protocol")

    find_response = await runner.call(
        mapping_find,
        query={"tg_user_id": payload.tg_user_id, "inbound_id": inbound_id},
    )
    action = "existing"
    if find_response.status_code == 404:
        action = "created"
        create_payload = {
            "tg_user_id": payload.tg_user_id,
            "tg_username": payload.tg_username,
            "protocol": protocol,
            "inbound_id": inbound_id,
        }
        create_response = await runner.call(
            mapping_create,
            json_body=create_payload,
        )
        if create_response.status_code >= 400:
            await handle_panel_error(create_response)
        base_payload = create_response.json()
    elif find_response.status_code >= 400:
        await handle_panel_error(find_response)
    else:
        base_payload = find_response.json()

    try:
        normalized = normalize_key_payload(base_payload)
    except MappingError as exc:
        logger.error("issue_mapping_failed", extra={"raw_panel_payload": base_payload, "reason": str(exc)})
        normalized = {"client": {}, "delivery": None, "raw": base_payload}

    content = {"status": "ok", "action": action, **normalized}
    await cache.set(idempotency_key, 200, content)

    logger.info(
        "issue_key_success",
        extra={"tg_user_id": payload.tg_user_id, "action": action, "inbound_id": inbound_id},
    )
    return JSONResponse(status_code=200, content=content)


@app.post("/api/v1/keys/revoke", dependencies=[Depends(hmac_guard)])
async def revoke_key(payload: RevokeRequest) -> Dict[str, Any]:
    runner = get_runner()
    mapping_name = settings.postman_mapping.get("revoke_by_user")
    if not mapping_name:
        raise ServiceError(500, "configuration_error", "Mapping for revoke is missing")

    response = await runner.call(
        mapping_name,
        json_body={"tg_user_id": payload.tg_user_id, "inbound_id": payload.inbound_id, "reason": payload.reason},
    )
    if response.status_code >= 400:
        await handle_panel_error(response)

    normalized = normalize_revoke_payload(response.json())
    logger.info("revoke_success", extra={"tg_user_id": payload.tg_user_id, "inbound_id": payload.inbound_id})
    return {"status": "ok", **normalized}


@app.get("/api/v1/status", dependencies=[Depends(hmac_guard)])
async def status(tg_user_id: int) -> Dict[str, Any]:
    runner = get_runner()
    mapping_name = settings.postman_mapping.get("status_by_user")
    if not mapping_name:
        raise ServiceError(500, "configuration_error", "Mapping for status is missing")
    response = await runner.call(mapping_name, query={"tg_user_id": tg_user_id})
    if response.status_code >= 400:
        if response.status_code == 404:
            raise ServiceError(404, "not_found", "Client not found")
        await handle_panel_error(response)
    normalized = normalize_status_payload(response.json())
    logger.info("status_lookup", extra={"tg_user_id": tg_user_id, "active": normalized["active"]})
    return {"status": "ok", **normalized}
