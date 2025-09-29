"""Middleware to ensure only admins can access certain routers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from routex_bot import texts


class AdminMiddleware(BaseMiddleware):
    """Allow only administrators to use commands handled by this router."""

    def __init__(self, admin_ids: set[int]) -> None:
        super().__init__()
        self.admin_ids = admin_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user or user.id not in self.admin_ids:
            if isinstance(event, Message):
                await event.answer(texts.NO_PERMISSION)
            return None
        return await handler(event, data)


__all__ = ["AdminMiddleware"]
