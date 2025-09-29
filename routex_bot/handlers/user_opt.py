"""Subscription management handlers."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from routex_bot import texts
from routex_bot.db import Database

router = Router(name="user_opt")


@router.message(Command("optout"))
async def cmd_optout(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username)
    await db.update_subscription(user.id, False)
    await message.answer(texts.OPT_OUT_TEXT)


@router.message(Command("optin"))
async def cmd_optin(message: Message, db: Database) -> None:
    user = message.from_user
    if not user:
        return
    await db.ensure_user(user.id, user.username)
    await db.update_subscription(user.id, True)
    await message.answer(texts.OPT_IN_TEXT)
