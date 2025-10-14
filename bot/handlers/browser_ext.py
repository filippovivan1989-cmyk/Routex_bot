from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..utils import get_bot_data

router = Router()


@router.callback_query(F.data == "menu:browser")
async def show_browser_menu(callback: CallbackQuery) -> None:
    menu_renderer = get_bot_data(callback.bot, "menu_renderer")
    if menu_renderer and callback.message:
        text, keyboard = menu_renderer.browser()
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "browser:link")
async def browser_link(callback: CallbackQuery) -> None:
    config = get_bot_data(callback.bot, "config")
    url = config.links.get("browser_ext_url", "") if config else ""
    if callback.message:
        await callback.message.answer(f"🌍 Расширение\n{url}")
    await callback.answer()


@router.callback_query(F.data == "browser:guide")
async def browser_guide(callback: CallbackQuery) -> None:
    config = get_bot_data(callback.bot, "config")
    guide_text = config.texts.get("browser_ext_install", "") if config else ""
    guide_url = config.links.get("browser_ext_guide_url", "") if config else ""
    message = f"📘 Инструкция\n{guide_text}"
    if guide_url:
        message += f"\n\nПодробности: {guide_url}"
    if callback.message:
        await callback.message.answer(message)
    await callback.answer()
