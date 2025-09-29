"""Entrypoint for RouteX VPN bot."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from routex_bot.config import get_settings
from routex_bot.db import Database
from routex_bot.handlers import setup_handlers
from routex_bot.services.broadcast import BroadcastService
from routex_bot.services.scheduler import SchedulerService
from routex_bot.services.xui_client import XUIClient
from routex_bot.web.app import create_web_app


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    structlog.configure(processors=[structlog.processors.JSONRenderer()])


async def start_web_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner


async def stop_web_server(runner: web.AppRunner) -> None:
    with suppress(Exception):
        await runner.cleanup()


async def main() -> None:
    configure_logging()
    settings = get_settings()

    db = Database(settings.database_path)
    await db.connect()
    await db.init_models()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    setup_handlers(dp, set(settings.admin_ids))

    xui_client = XUIClient(settings.panel_url, settings.panel_login, settings.panel_password)
    broadcast_service = BroadcastService(
        bot,
        db,
        batch_size=settings.batch_size,
        delay_seconds=settings.batch_delay_seconds,
    )
    scheduler_service = SchedulerService(db, broadcast_service, settings.tz)

    web_app = create_web_app(settings, broadcast_service)
    web_runner = await start_web_server(web_app, settings.host, settings.port)

    await scheduler_service.start()

    try:
        await dp.start_polling(
            bot,
            settings=settings,
            db=db,
            xui_client=xui_client,
            broadcast_service=broadcast_service,
            scheduler_service=scheduler_service,
        )
    finally:
        await scheduler_service.shutdown()
        await xui_client.close()
        await db.close()
        await bot.session.close()
        await stop_web_server(web_runner)


if __name__ == "__main__":
    asyncio.run(main())
