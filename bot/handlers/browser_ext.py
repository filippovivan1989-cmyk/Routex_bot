from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data == "menu:browser")
async def show_browser_menu(callback: CallbackQuery) -> None:
    menu_renderer = getattr(callback.bot, "menu_renderer", None)
    if menu_renderer and callback.message:
        text, keyboard = menu_renderer.browser()
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "browser:link")
async def browser_link(callback: CallbackQuery) -> None:
    config = getattr(callback.bot, "config", None)
    url = config.links.get("browser_ext_url", "") if config else ""
    if callback.message:
        await callback.message.answer(f"🌍 Расширение\n{url}")
    await callback.answer()


@router.callback_query(F.data == "browser:guide")
async def browser_guide(callback: CallbackQuery) -> None:
    config = getattr(callback.bot, "config", None)
    guide_text = config.texts.get("browser_ext_install", "") if config else ""
    guide_url = config.links.get("browser_ext_guide_url", "") if config else ""
    message = f"📘 Инструкция\n{guide_text}"
    if guide_url:
        message += f"\n\nПодробности: {guide_url}"
    if callback.message:
        await callback.message.answer(message)
    await callback.answer()
