"""Handlers related to VPN keys."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from routex_bot import texts
from routex_bot.config import Settings
from routex_bot.db import Database
from routex_bot.services.xui_client import XUIClient, ensure_or_create_key

router = Router(name="user_keys")


def _instructions_keyboard(settings: Settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть гайд", url=settings.guide_url)]]
    )


@router.message(Command("getkey"))
@router.message(F.text == texts.START_BUTTONS["get_key"])
async def cmd_get_key(
    message: Message,
    db: Database,
    settings: Settings,
    xui_client: XUIClient,
) -> None:
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username)
    key = await ensure_or_create_key(db, xui_client, user.id)
    await message.answer(
        texts.KEY_RESPONSE.format(key=key),
        reply_markup=_instructions_keyboard(settings),
    )
    await db.touch_activity(user.id)


@router.message(Command("mykey"))
@router.message(F.text == texts.START_BUTTONS["my_key"])
async def cmd_my_key(message: Message, db: Database, settings: Settings) -> None:
    user = message.from_user
    if not user:
        return
    record = await db.ensure_user(user.id, user.username)
    key = record["key"]
    if not key:
        await message.answer(texts.MY_KEY_EMPTY)
        return
    await message.answer(
        texts.MY_KEY_RESPONSE.format(key=key),
        reply_markup=_instructions_keyboard(settings),
    )
    await db.touch_activity(user.id)


@router.message(F.text == texts.START_BUTTONS["instructions"])
async def btn_instructions(message: Message, settings: Settings) -> None:
    await message.answer(texts.INSTRUCTIONS_TEXT.format(link=settings.guide_url))
