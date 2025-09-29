"""Admin menu command."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from routex_bot import texts

router = Router(name="admin_menu")


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer(texts.ADMIN_MENU)
