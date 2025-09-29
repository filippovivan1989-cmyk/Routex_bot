"""Donate handler."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from routex_bot import texts
from routex_bot.config import Settings
from routex_bot.db import Database

router = Router(name="user_donate")


def _donate_keyboard(settings: Settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Сделать донат", url=str(settings.cloudtips_link))]]
    )


@router.message(Command("donate"))
@router.message(F.text == texts.START_BUTTONS["donate"])
async def cmd_donate(message: Message, settings: Settings, db: Database) -> None:
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username)
    await db.mark_donor(user.id)
    await message.answer(texts.DONATE_TEXT, reply_markup=_donate_keyboard(settings))
