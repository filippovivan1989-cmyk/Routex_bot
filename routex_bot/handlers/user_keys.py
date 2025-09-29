"""Handlers related to VPN keys."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from routex_bot import texts
from routex_bot.config import Settings
from routex_bot.db import Database
from tenacity import RetryError

from routex_bot.services.xui_client import XUIClient, XUIError, ensure_or_create_key

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
    try:
        key = await ensure_or_create_key(db, xui_client, user.id)
    except XUIError as exc:
        await message.answer(texts.PANEL_TEMPORARY_ERROR)
        await db.write_audit(
            user.id,
            "panel_error",
            {"command": "getkey", "error": str(exc), "tg_id": user.id},
        )
        return
    await message.answer(
        texts.KEY_RESPONSE.format(key=key),
        reply_markup=_instructions_keyboard(settings),
    )
    await db.touch_activity(user.id)


@router.message(Command("mykey"))
@router.message(F.text == texts.START_BUTTONS["my_key"])
async def cmd_my_key(
    message: Message,
    db: Database,
    settings: Settings,
    xui_client: XUIClient,
) -> None:
    user = message.from_user
    if not user:
        return
    record = await db.ensure_user(user.id, user.username)
    try:
        remote_key = await xui_client.fetch_client_by_remark(user.id)
    except RetryError as exc:
        inner_exc = exc.last_attempt.exception() if exc.last_attempt else exc
        await db.write_audit(
            user.id,
            "panel_error",
            {"command": "mykey", "error": str(inner_exc), "tg_id": user.id},
        )
        await message.answer(texts.PANEL_TEMPORARY_ERROR)
        return
    except XUIError as exc:
        await db.write_audit(
            user.id,
            "panel_error",
            {"command": "mykey", "error": str(exc), "tg_id": user.id},
        )
        await message.answer(texts.PANEL_TEMPORARY_ERROR)
        return

    if not remote_key:
        if record["key"]:
            await db.clear_user_key(user.id)
            await db.write_audit(
                user.id,
                "panel_client_missing",
                {"command": "mykey", "remark": f"routex-{user.id}"},
            )
            await message.answer(texts.MY_KEY_MISSING_REMOTE)
        else:
            await message.answer(texts.MY_KEY_EMPTY)
        await db.touch_activity(user.id)
        return

    if record["key"] != remote_key:
        await db.update_user_key(user.id, remote_key)
    await message.answer(
        texts.MY_KEY_RESPONSE.format(key=remote_key),
        reply_markup=_instructions_keyboard(settings),
    )
    await db.touch_activity(user.id)


@router.message(F.text == texts.START_BUTTONS["instructions"])
async def btn_instructions(message: Message, settings: Settings) -> None:
    await message.answer(texts.INSTRUCTIONS_TEXT.format(link=settings.guide_url))
