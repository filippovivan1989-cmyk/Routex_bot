"""aiohttp application providing health and event endpoints."""

from __future__ import annotations

import structlog
from aiohttp import web

from routex_bot.config import Settings
from routex_bot.services.broadcast import BroadcastService

LOGGER = structlog.get_logger(__name__)


def create_web_app(settings: Settings, broadcast_service: BroadcastService) -> web.Application:
    app = web.Application(middlewares=[auth_middleware(settings)])
    app["settings"] = settings
    app["broadcast_service"] = broadcast_service
    app.router.add_get("/healthz", healthcheck)
    app.router.add_post("/webhook/event", handle_event)
    return app


def auth_middleware(settings: Settings):
    @web.middleware
    async def middleware(request: web.Request, handler):
        if request.path == "/webhook/event":
            token = request.headers.get("X-Admin-Token")
            if token != settings.events_webhook_token:
                LOGGER.warning("Invalid webhook token", ip=request.remote)
                return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    return middleware


async def healthcheck(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def handle_event(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    broadcast_service: BroadcastService = request.app["broadcast_service"]
    
    try:
        data = await request.json()
    except Exception as e:
        LOGGER.warning("Invalid JSON in webhook request", error=str(e))
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    event_type = data.get("event_type")
    payload = data.get("payload", {})
    
    if not event_type:
        return web.json_response({"error": "event_type required"}, status=400)
    
    # Валидация event_type
    if not isinstance(event_type, str) or len(event_type) > 100:
        return web.json_response({"error": "Invalid event_type"}, status=400)
    
    # Валидация payload
    if not isinstance(payload, dict):
        return web.json_response({"error": "payload must be a dictionary"}, status=400)
    
    LOGGER.info("Webhook event received", event_type=event_type, payload_size=len(str(payload)))
    await broadcast_service.broadcast_event(event_type, payload)
    return web.json_response({"status": "queued"})


__all__ = ["create_web_app"]
