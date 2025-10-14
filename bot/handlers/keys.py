from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..service_client import NotFoundError, ServiceClient, ServiceClientError
from ..utils import ensure_png_bytes, get_bot_data

logger = logging.getLogger(__name__)

router = Router()


class UserLockManager:
    def __init__(self, hold_seconds: int = 7) -> None:
        self._locks: Dict[int, asyncio.Lock] = {}
        self._hold_seconds = hold_seconds

    @asynccontextmanager
    async def lock(self, user_id: int):
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
            loop = asyncio.get_running_loop()
            loop.call_later(self._hold_seconds, self._cleanup, user_id, lock)

    def _cleanup(self, user_id: int, lock: asyncio.Lock) -> None:
        if not lock.locked():
            self._locks.pop(user_id, None)


default_lock_manager = UserLockManager()


def _get_defaults(callback: CallbackQuery) -> Dict[str, int | str]:
    defaults = get_bot_data(callback.bot, "defaults", {}) or {}
    return {
        "protocol": defaults.get("protocol", "vless"),
        "inbound_id": defaults.get("inbound_id", 1),
    }


@router.callback_query(F.data == "menu:keys")
async def show_keys_menu(callback: CallbackQuery) -> None:
    menu_renderer = get_bot_data(callback.bot, "menu_renderer")
    if menu_renderer and callback.message:
        text, keyboard = menu_renderer.keys()
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


async def _send_key_details(callback: CallbackQuery, data: Dict[str, Any]) -> None:
    delivery = data.get("delivery", {})
    client = data.get("client", {})
    uri = delivery.get("uri")
    qr_bytes = ensure_png_bytes(delivery.get("qr_png_base64"), uri)
    action = data.get("action")
    status_flag = "✅ Активен" if client.get("active") else "⛔️ Отключен"
    panel_user_id = client.get("panel_user_id") or "—"
    header = "🔑 Ваш ключ"
    if action == "created":
        header = "✨ Создан новый ключ"
    text = (
        f"{header}\n\n"
        f"• Статус: {status_flag}\n"
        f"• ID панели: `{panel_user_id}`\n"
        "\nИспользуй кнопку ниже, чтобы скопировать URI."
    )
    keyboard_builder = InlineKeyboardBuilder()
    if uri:
        keyboard_builder.button(text="Показать ссылку", url=uri)
    keyboard = keyboard_builder.as_markup() if keyboard_builder.buttons else None
    if callback.message:
        await callback.message.answer_photo(
            BufferedInputFile(qr_bytes, filename="vpn_key.png"),
            caption=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
    await callback.answer("Готово")


async def _handle_service_error(callback: CallbackQuery, error: Exception) -> None:
    logger.exception("Service call failed", exc_info=error)
    message = "Не удалось выполнить запрос. Попробуйте позже."
    if callback.message:
        await callback.message.answer(message)
    await callback.answer()


@router.callback_query(F.data == "keys:get")
async def handle_get_key(callback: CallbackQuery) -> None:
    service_client: ServiceClient | None = get_bot_data(callback.bot, "service_client")
    if not service_client:
        await _handle_service_error(callback, RuntimeError("Service client unavailable"))
        return

    defaults = _get_defaults(callback)
    tg_user_id = callback.from_user.id
    username = callback.from_user.username

    async with default_lock_manager.lock(tg_user_id):
        try:
            data = await service_client.get_key(tg_user_id, defaults["inbound_id"])
        except NotFoundError:
            data = await service_client.issue_key(
                tg_user_id=tg_user_id,
                tg_username=username,
                protocol=defaults["protocol"],
                inbound_id=defaults["inbound_id"],
            )
        except ServiceClientError as error:
            await _handle_service_error(callback, error)
            return
        await _send_key_details(callback, data)


@router.callback_query(F.data == "keys:qr")
async def handle_show_qr(callback: CallbackQuery) -> None:
    service_client: ServiceClient | None = get_bot_data(callback.bot, "service_client")
    if not service_client:
        await _handle_service_error(callback, RuntimeError("Service client unavailable"))
        return

    defaults = _get_defaults(callback)
    tg_user_id = callback.from_user.id

    async with default_lock_manager.lock(tg_user_id):
        try:
            data = await service_client.get_key(tg_user_id, defaults["inbound_id"])
        except NotFoundError:
            data = await service_client.issue_key(
                tg_user_id=tg_user_id,
                tg_username=callback.from_user.username,
                protocol=defaults["protocol"],
                inbound_id=defaults["inbound_id"],
            )
        except ServiceClientError as error:
            await _handle_service_error(callback, error)
            return
        await _send_key_details(callback, data)


@router.callback_query(F.data == "keys:recreate")
async def handle_recreate_key(callback: CallbackQuery) -> None:
    service_client: ServiceClient | None = get_bot_data(callback.bot, "service_client")
    if not service_client:
        await _handle_service_error(callback, RuntimeError("Service client unavailable"))
        return

    defaults = _get_defaults(callback)
    tg_user_id = callback.from_user.id

    async with default_lock_manager.lock(tg_user_id):
        try:
            await service_client.revoke_key(tg_user_id, defaults["inbound_id"], reason="user_requested")
        except ServiceClientError as error:
            # revoke may fail if key absent; log but continue to create new one
            logger.warning("Failed to revoke key", extra={"tg_user_id": tg_user_id}, exc_info=error)
        try:
            data = await service_client.issue_key(
                tg_user_id=tg_user_id,
                tg_username=callback.from_user.username,
                protocol=defaults["protocol"],
                inbound_id=defaults["inbound_id"],
            )
        except ServiceClientError as error:
            await _handle_service_error(callback, error)
            return
        await _send_key_details(callback, data)
