"""Handlers aggregation."""

from __future__ import annotations

from aiogram import Dispatcher

from routex_bot.handlers import (
    admin_menu,
    admin_schedule,
    user_donate,
    user_keys,
    user_opt,
    user_start,
)
from routex_bot.middlewares.auth_admin import AdminMiddleware


def setup_handlers(dp: Dispatcher, admin_ids: set[int]) -> None:
    """Register bot handlers and middlewares."""

    dp.include_router(user_start.router)
    dp.include_router(user_keys.router)
    dp.include_router(user_donate.router)
    dp.include_router(user_opt.router)

    admin_router = admin_menu.router
    admin_router.message.middleware(AdminMiddleware(admin_ids))
    dp.include_router(admin_router)

    schedule_router = admin_schedule.router
    schedule_router.message.middleware(AdminMiddleware(admin_ids))
    dp.include_router(schedule_router)


__all__ = ["setup_handlers"]
