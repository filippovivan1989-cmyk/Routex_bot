from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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

app = FastAPI(title="VPN Service Adapter")
app.state.idempotency_cache = IdempotencyCache(ttl_seconds=300)
app.state.postman_runner = None


@app.on_event("startup")
async def startup_event() -> None:
    if not collection_path.exists():
        logger.warning("Postman collection is not provided at %s", collection_path)
        return
    try:
        app.state.postman_runner = PostmanRunner(
            collection_path,
            environment_path=environment_path if environment_path.exists() else None,
            timeout=settings.timeout,
        )
        logger.info("Postman runner initialized", extra={"collection": str(collection_path)})
    except Exception:  # pragma: no cover - start failures are logged and surfaced
        logger.exception("Failed to initialize Postman runner")
        raise


@app.on_event("shutdown")
async def shutdown_event() -> None:
    runner: Optional[PostmanRunner] = getattr(app.state, "postman_runner", None)
    if runner:
        await runner.aclose()


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(HTTPException)
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


async def hmac_guard(request: Request) -> None:
    body = await request.body()
    try:
        verify_hmac(request.headers, body, secret=settings.hmac_secret)
    except SignatureError as exc:
        raise ServiceError(401, "unauthorized", str(exc)) from exc


def get_runner() -> PostmanRunner:
    runner: Optional[PostmanRunner] = getattr(app.state, "postman_runner", None)
    if runner is None:
        raise ServiceError(503, "service_unavailable", "Postman runner is not configured")
    return runner


async def handle_panel_error(response: Any) -> None:
    try:
        payload = response.json()
    except Exception:
        payload = {}
    message = payload.get("error") if isinstance(payload, dict) else None
    raise ServiceError(response.status_code, "panel_error", message or "Upstream request failed")




@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
@app.get("/api/v1/keys/by-user", dependencies=[Depends(hmac_guard)])
async def get_key_by_user(tg_user_id: int, inbound_id: int) -> Dict[str, Any]:
    runner = get_runner()
    mapping_name = settings.postman_mapping.get("find_by_user")
    if not mapping_name:
        raise ServiceError(500, "configuration_error", "Mapping for find_by_user is missing")

    response = await runner.call(
        mapping_name,
        query={"tg_user_id": tg_user_id, "inbound_id": inbound_id},
    )
    if response.status_code == 404:
        raise ServiceError(404, "not_found", "Key not found")
    if response.status_code >= 400:
        await handle_panel_error(response)
    try:
        normalized = normalize_key_payload(response.json())
    except MappingError as exc:
        raise ServiceError(502, "mapping_error", str(exc)) from exc
    result = {"status": "ok", "action": None, **normalized}
    logger.info(
        "key_lookup_success",
        extra={"tg_user_id": tg_user_id, "inbound_id": inbound_id, "panel_user_id": normalized["client"]["panel_user_id"]},
    )
    return result


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
        raise ServiceError(502, "mapping_error", str(exc)) from exc

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
    logger.info(
        "revoke_key",
        extra={"tg_user_id": payload.tg_user_id, "inbound_id": payload.inbound_id},
    )
    return {"status": "ok", "result": normalized}


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
