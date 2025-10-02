"""Broadcast service handling segmentation and delivery."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any, Dict, List, Tuple

import aiosqlite
from aiogram import Bot
from aiogram.exceptions import (TelegramAPIError, TelegramBadRequest, TelegramForbiddenError,
                                TelegramNotFound, TelegramRetryAfter)
import structlog

from routex_bot.db import Database
from routex_bot import texts


def chunked(iterable: Iterable[Any], size: int) -> Iterable[List[Any]]:
    chunk: List[Any] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


class BroadcastService:
    """Service responsible for queued message delivery."""

    def __init__(self, bot: Bot, db: Database, *, batch_size: int, delay_seconds: float) -> None:
        self.bot = bot
        self.db = db
        self.batch_size = max(1, batch_size)
        self.delay_seconds = max(0.1, delay_seconds)
        self.logger = structlog.get_logger(__name__)

    async def broadcast(
        self,
        text: str,
        segment: Dict[str, Any],
        *,
        schedule_id: int | None = None,
        parse_mode: str = "HTML",
    ) -> Tuple[int, int, int]:
        """Send message to users in the segment."""

        recipients = await self.db.list_users_for_segment(segment)
        if not recipients:
            return 0, 0, 0

        sent = 0
        failed = 0
        queued = 0
        for batch in chunked(recipients, self.batch_size):
            for user in batch:
                user_id = user["id"]
                if schedule_id and await self.db.has_recent_delivery(schedule_id, user_id):
                    continue
                delivery_id = await self.db.enqueue_delivery(schedule_id, user_id)
                queued += 1
                message_text = self._render_text(text, user)
                try:
                    await self.bot.send_message(user["tg_id"], message_text, parse_mode=parse_mode)
                    await self.db.update_delivery(delivery_id, "sent")
                    await self.db.touch_activity(user["tg_id"])
                    sent += 1
                except TelegramRetryAfter as exc:
                    self.logger.warning("Flood wait encountered", seconds=exc.retry_after, user=user["tg_id"])
                    await asyncio.sleep(exc.retry_after)
                    if await self._retry_delivery(delivery_id, user, message_text, parse_mode):
                        sent += 1
                    else:
                        failed += 1
                except (TelegramForbiddenError, TelegramNotFound) as exc:
                    await self.db.update_delivery(delivery_id, "failed", error=str(exc))
                    failed += 1
                    await self.db.update_subscription(user["tg_id"], False)
                except (TelegramBadRequest, TelegramAPIError) as exc:
                    await self.db.update_delivery(delivery_id, "failed", error=str(exc))
                    failed += 1
                    self.logger.error("Failed to send broadcast", user=user["tg_id"], error=str(exc))
                except Exception as exc:  # pragma: no cover - safety net
                    await self.db.update_delivery(delivery_id, "failed", error=str(exc))
                    failed += 1
                    self.logger.error("Unexpected broadcast error", user=user["tg_id"], error=str(exc))
            await asyncio.sleep(self.delay_seconds)
        return queued, sent, failed

    async def _retry_delivery(
        self,
        delivery_id: int,
        user: aiosqlite.Row,
        text: str,
        parse_mode: str,
    ) -> bool:
        tries = 0
        while tries < 3:
            try:
                await self.bot.send_message(user["tg_id"], text, parse_mode=parse_mode)
                await self.db.update_delivery(delivery_id, "sent")
                await self.db.touch_activity(user["tg_id"])
                return True
            except TelegramRetryAfter as exc:
                tries += 1
                await asyncio.sleep(exc.retry_after)
                continue
            except (TelegramForbiddenError, TelegramNotFound) as exc:
                await self.db.update_delivery(delivery_id, "failed", error=str(exc))
                await self.db.update_subscription(user["tg_id"], False)
                return False
            except (TelegramBadRequest, TelegramAPIError) as exc:
                await self.db.update_delivery(delivery_id, "failed", error=str(exc))
                self.logger.error("Retry failed", user=user["tg_id"], error=str(exc))
                return False
        await self.db.update_delivery(delivery_id, "failed", error="Retry limit exceeded")
        return False

    def _render_text(self, template: str, user: Any) -> str:
        placeholders = {
            "username": user["username"] or f"друг RouteX #{user['tg_id']}",
            "key": user["key"] or "—",
        }
        try:
            return template.format(**placeholders)
        except (KeyError, ValueError) as e:
            self.logger.warning("Template rendering failed", error=str(e), template=template[:100])
            return template

    async def broadcast_event(self, event_type: str, payload: Dict[str, Any]) -> Tuple[int, int, int]:
        template_key = f"event_template:{event_type}"
        template = await self.db.get_setting(template_key) or texts.EVENT_TEMPLATE_FALLBACK
        payload_message = json.dumps(payload, ensure_ascii=False)
        text = template.format(greeting="Привет", payload_message=payload_message)
        return await self.broadcast(text, {"type": "all_subscribed"}, schedule_id=None)


__all__ = ["BroadcastService"]
