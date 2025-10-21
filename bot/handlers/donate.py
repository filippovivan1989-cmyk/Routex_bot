from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data == "menu:donate")
async def show_donate(callback: CallbackQuery) -> None:
    menu_renderer = getattr(callback.bot, "menu_renderer", None)
    if menu_renderer and callback.message:
        text, keyboard = menu_renderer.donate()
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
