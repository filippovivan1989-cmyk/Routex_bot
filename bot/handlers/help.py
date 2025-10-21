from __future__ import annotations

import logging
from typing import Dict, Tuple

from aiogram import F, Router
from aiogram.types import CallbackQuery

logger = logging.getLogger(__name__)
router = Router()


HELP_LINKS: Dict[str, Tuple[str, str]] = {
    "help:android": ("📱 Android", "android_client_url"),
    "help:ios": ("🍏 iOS", "ios_client_url"),
    "help:windows": ("🖥 Windows", "windows_client_url"),
}


def _get_config(callback: CallbackQuery):
    return getattr(callback.bot, "config", None)


@router.callback_query(F.data == "menu:help")
async def show_help_root(callback: CallbackQuery) -> None:
    menu_renderer = getattr(callback.bot, "menu_renderer", None)
    if not menu_renderer:
        logger.error("menu_renderer is not configured")
        await callback.answer()
        return
    if callback.message:
        text, keyboard = menu_renderer.help_root()
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.in_(set(HELP_LINKS)))
async def send_client_link(callback: CallbackQuery) -> None:
    config = _get_config(callback)
    if not config:
        logger.error("config is not configured")
        await callback.answer()
        return

    label, link_key = HELP_LINKS.get(callback.data or "", ("", ""))
    url = config.links.get(link_key, "")
    common_tips = config.texts.get("help_common", "")

    if not url:
        message = f"{label}\nСсылка не настроена."
    else:
        message = f"{label}\n{url}"
    if common_tips:
        message += f"\n\nСоветы:\n{common_tips}"

    if callback.message:
        await callback.message.answer(message)
    await callback.answer()


@router.callback_query(F.data == "help:faq")
async def send_common_help(callback: CallbackQuery) -> None:
    config = _get_config(callback)
    text = (config.texts.get("help_common", "") if config else "").strip()
    if not text:
        text = "Советы пока не добавлены."
    if callback.message:
        await callback.message.answer(f"❓ Общие советы\n{text}")
    await callback.answer()
