"""User /start handler."""

from __future__ import annotations

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from aiogram.types.input_file import FSInputFile

from routex_bot import texts
from routex_bot.config import Settings
from routex_bot.db import Database

router = Router(name="user_start")


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, settings: Settings) -> None:
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=texts.START_BUTTONS["get_key"]),
                KeyboardButton(text=texts.START_BUTTONS["my_key"]),
            ],
            [
                KeyboardButton(text=texts.START_BUTTONS["instructions"]),
                KeyboardButton(text=texts.START_BUTTONS["donate"]),
            ],
        ],
        resize_keyboard=True,
    )
    caption = f"{texts.WELCOME}\n\nДоступные команды: /getkey, /mykey, /donate"
    logo_path = "assets/logo.svg"
    try:
        await message.answer_photo(
            FSInputFile(logo_path), caption=caption, reply_markup=keyboard
        )
    except TelegramBadRequest:
        await message.answer_document(
            FSInputFile(logo_path), caption=caption, reply_markup=keyboard
        )
    await db.touch_activity(user.id)
