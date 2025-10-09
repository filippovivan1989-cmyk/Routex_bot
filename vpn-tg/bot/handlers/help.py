from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data == "menu:help")
async def show_help_root(callback: CallbackQuery) -> None:
    menu_renderer = callback.bot.get("menu_renderer")
    if menu_renderer and callback.message:
        text, keyboard = menu_renderer.help_root()
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


async def _send_link(callback: CallbackQuery, title: str, url: str) -> None:
    message = f"{title}\n{url}"
    if callback.message:
        await callback.message.answer(message)
    await callback.answer()


@router.callback_query(F.data == "help:android")
async def help_android(callback: CallbackQuery) -> None:
    config = callback.bot.get("config")
    url = config.links.get("android_client_url", "") if config else ""
    await _send_link(callback, "📱 Android клиент", url)


@router.callback_query(F.data == "help:ios")
async def help_ios(callback: CallbackQuery) -> None:
    config = callback.bot.get("config")
    url = config.links.get("ios_client_url", "") if config else ""
    await _send_link(callback, "🍏 iOS клиент", url)


@router.callback_query(F.data == "help:windows")
async def help_windows(callback: CallbackQuery) -> None:
    config = callback.bot.get("config")
    url = config.links.get("windows_client_url", "") if config else ""
    await _send_link(callback, "🖥 Windows клиент", url)


@router.callback_query(F.data == "help:faq")
async def help_common(callback: CallbackQuery) -> None:
    config = callback.bot.get("config")
    text = config.texts.get("help_common", "") if config else ""
    if callback.message:
        await callback.message.answer(f"❓ Общие советы\n{text}")
    await callback.answer()
