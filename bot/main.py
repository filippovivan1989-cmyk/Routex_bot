from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from dotenv import load_dotenv

from .handlers import browser_ext, donate, help as help_handler, keys
from .menu import MenuRenderer
from .service_client import ServiceClient
from .utils import BotConfig, load_yaml_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("bot")


async def start_handler(message: Message) -> None:
    bot = message.bot
    menu_renderer: MenuRenderer = bot["menu_renderer"]
    text, keyboard = menu_renderer.root()
    await message.answer(text, reply_markup=keyboard)


async def back_to_root(callback: CallbackQuery) -> None:
    menu_renderer: MenuRenderer = callback.bot["menu_renderer"]
    if callback.message:
        text, keyboard = menu_renderer.root()
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


async def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    config_dir = base_dir / "config"
    load_dotenv(config_dir / ".env")

    yaml_config: BotConfig = load_yaml_config(config_dir / "config.yaml")

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")

    service_base = os.getenv("SERVICE_BASE_URL")
    hmac_secret = os.getenv("SERVICE_HMAC_SECRET")
    if not service_base or not hmac_secret:
        raise RuntimeError("Service configuration is incomplete")

    timeout = float(os.getenv("HTTP_TIMEOUT_SECONDS", "20"))
    default_protocol = os.getenv("DEFAULT_PROTOCOL", yaml_config.defaults.get("protocol", "vless"))
    default_inbound_id = int(os.getenv("DEFAULT_INBOUND_ID", yaml_config.defaults.get("inbound_id", 1)))

    bot = Bot(bot_token, parse_mode=ParseMode.MARKDOWN)
    dp = Dispatcher()

    service_client = ServiceClient(service_base, hmac_secret, timeout=timeout)
    menu_renderer = MenuRenderer(yaml_config)

    bot["config"] = yaml_config
    bot["service_client"] = service_client
    bot["menu_renderer"] = menu_renderer
    bot["defaults"] = {"protocol": default_protocol, "inbound_id": default_inbound_id}

    dp.message.register(start_handler, CommandStart())
    dp.callback_query.register(back_to_root, F.data == "menu:root")

    dp.include_router(keys.router)
    dp.include_router(help_handler.router)
    dp.include_router(browser_ext.router)
    dp.include_router(donate.router)

    try:
        await dp.start_polling(bot)
    finally:
        await service_client.close()


if __name__ == "__main__":
    asyncio.run(main())
