from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..utils import get_bot_data

router = Router()


@router.callback_query(F.data == "menu:donate")
async def show_donate(callback: CallbackQuery) -> None:
    menu_renderer = get_bot_data(callback.bot, "menu_renderer")
    if menu_renderer and callback.message:
        text, keyboard = menu_renderer.donate()
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
