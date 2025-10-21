from __future__ import annotations

import logging
from aiogram import F, Router
from aiogram.types import CallbackQuery

logger = logging.getLogger(__name__)
router = Router()

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
