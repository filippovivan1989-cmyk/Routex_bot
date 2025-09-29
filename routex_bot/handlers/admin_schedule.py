"""Admin scheduling handlers."""

from __future__ import annotations

import json
from typing import Any, Dict

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from routex_bot import texts
from routex_bot.config import Settings
from routex_bot.db import Database
from routex_bot.services.broadcast import BroadcastService
from routex_bot.services.scheduler import SchedulerService

router = Router(name="admin_schedule")


class ScheduleAddStates(StatesGroup):
    name = State()
    schedule_type = State()
    spec = State()
    text = State()
    segment_type = State()
    segment_custom = State()
    confirm = State()


class BroadcastNowStates(StatesGroup):
    segment_type = State()
    segment_custom = State()
    text = State()
    confirm = State()


@router.message(Command("schedule_add"))
async def schedule_add_start(message: Message, state: FSMContext) -> None:
    await state.set_state(ScheduleAddStates.name)
    await message.answer("Введи название рассылки:")


@router.message(ScheduleAddStates.name)
async def schedule_add_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(ScheduleAddStates.schedule_type)
    await message.answer("Выбери тип расписания: cron или interval")


@router.message(ScheduleAddStates.schedule_type)
async def schedule_add_type(message: Message, state: FSMContext) -> None:
    value = message.text.strip().lower()
    if value not in {"cron", "interval"}:
        await message.answer("Допустимые значения: cron или interval")
        return
    await state.update_data(schedule_type=value)
    await state.set_state(ScheduleAddStates.spec)
    if value == "cron":
        await message.answer(
            "Введи CRON-маску (например, 0 10 * * 1 для понедельника в 10:00):"
        )
    else:
        await message.answer("Укажи интервал в формате minutes=30 или hours=2,days=1")


@router.message(ScheduleAddStates.spec)
async def schedule_add_spec(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    schedule_type = data["schedule_type"]
    spec_text = message.text.strip()
    if schedule_type == "cron":
        spec_value = spec_text
    else:
        try:
            spec_value = _parse_interval(spec_text)
        except ValueError as exc:
            await message.answer(str(exc))
            return
    await state.update_data(spec=spec_value)
    await state.set_state(ScheduleAddStates.text)
    await message.answer("Отправь текст сообщения. Можно использовать {username} и {key}.")


@router.message(ScheduleAddStates.text)
async def schedule_add_text(message: Message, state: FSMContext) -> None:
    await state.update_data(text=message.html_text or message.text or "")
    await state.set_state(ScheduleAddStates.segment_type)
    await message.answer(
        "Выбери сегмент получателей (например, all_subscribed).\n" + texts.HELP_SCHEDULE_SEGMENTS
    )


@router.message(ScheduleAddStates.segment_type)
async def schedule_add_segment(message: Message, state: FSMContext) -> None:
    segment_type = message.text.strip()
    if segment_type not in texts.SEGMENT_LABELS:
        await message.answer("Неверный сегмент. Попробуй ещё раз.")
        return
    await state.update_data(segment_type=segment_type)
    if segment_type == "custom_sql":
        await state.set_state(ScheduleAddStates.segment_custom)
        await message.answer("Введи условие WHERE без слова WHERE (например, is_donor = 1)")
    else:
        await state.set_state(ScheduleAddStates.confirm)
        await _schedule_confirm(message, state)


@router.message(ScheduleAddStates.segment_custom)
async def schedule_add_segment_custom(message: Message, state: FSMContext) -> None:
    where_clause = message.text.strip()
    await state.update_data(segment_custom=where_clause)
    await state.set_state(ScheduleAddStates.confirm)
    await _schedule_confirm(message, state)


async def _schedule_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    name = data["name"]
    schedule_type = data["schedule_type"]
    spec = data["spec"]
    text_body = data["text"]
    segment_type = data["segment_type"]
    summary = (
        f"Название: {name}\n"
        f"Тип: {schedule_type}\n"
        f"Параметры: {json.dumps(spec, ensure_ascii=False) if isinstance(spec, dict) else spec}\n"
        f"Сегмент: {segment_type}\n"
        f"Сообщение:\n{text_body}\n\n"
        "Подтвердить создание? (да/нет)"
    )
    await message.answer(summary)


@router.message(ScheduleAddStates.confirm)
async def schedule_add_confirm(
    message: Message,
    state: FSMContext,
    scheduler_service: SchedulerService,
    db: Database,
) -> None:
    answer = message.text.strip().lower()
    if answer not in {"да", "нет"}:
        await message.answer("Ответь «да» или «нет».")
        return
    if answer == "нет":
        await state.clear()
        await message.answer("Создание рассылки отменено.")
        return
    data = await state.get_data()
    segment: Dict[str, Any] = {"type": data["segment_type"]}
    if data["segment_type"] == "custom_sql":
        segment["where"] = data.get("segment_custom", "")
    spec_value = data["spec"]
    if isinstance(spec_value, dict):
        spec_serialized = json.dumps(spec_value)
    else:
        spec_serialized = spec_value
    schedule = await scheduler_service.add_schedule(
        data["name"],
        data["schedule_type"],
        spec_serialized,
        data["text"],
        segment,
    )
    await db.write_audit(
        message.from_user.id if message.from_user else None,
        "schedule_create",
        {
            "schedule_id": schedule.id,
            "type": data["schedule_type"],
            "segment": segment,
        },
    )
    await state.clear()
    await message.answer(texts.SCHEDULE_CREATED.format(name=schedule.name))


@router.message(Command("schedule_list"))
async def schedule_list(message: Message, db: Database) -> None:
    schedules = await db.list_schedules()
    if not schedules:
        await message.answer(texts.SCHEDULE_LIST_EMPTY)
        return
    lines = []
    for schedule in schedules:
        segment = json.loads(schedule.segment)
        next_run = schedule.next_run_at.isoformat() if schedule.next_run_at else "—"
        lines.append(
            f"#{schedule.id} {schedule.name} [{schedule.type}] {schedule.spec}\n"
            f"Сегмент: {segment.get('type')} | Вкл: {'да' if schedule.enabled else 'нет'} | next: {next_run}"
        )
    await message.answer("\n\n".join(lines))


@router.message(Command("schedule_toggle"))
async def schedule_toggle(message: Message, scheduler_service: SchedulerService) -> None:
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /schedule_toggle <id>")
        return
    schedule_id = int(parts[1])
    schedule = await scheduler_service.db.get_schedule(schedule_id)
    if not schedule:
        await message.answer("Расписание не найдено.")
        return
    enabled = not schedule.enabled
    await scheduler_service.toggle_schedule(schedule_id, enabled)
    text = texts.SCHEDULE_ENABLED if enabled else texts.SCHEDULE_DISABLED
    await message.answer(text.format(id=schedule_id))


@router.message(Command("schedule_delete"))
async def schedule_delete(message: Message, scheduler_service: SchedulerService) -> None:
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /schedule_delete <id>")
        return
    schedule_id = int(parts[1])
    await scheduler_service.delete_schedule(schedule_id)
    await message.answer(texts.SCHEDULE_DELETED.format(id=schedule_id))


@router.message(Command("broadcast_now"))
async def broadcast_now_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BroadcastNowStates.segment_type)
    await message.answer(
        "Выбери сегмент для мгновенной рассылки:\n" + texts.HELP_SCHEDULE_SEGMENTS
    )


@router.message(BroadcastNowStates.segment_type)
async def broadcast_now_segment(message: Message, state: FSMContext) -> None:
    segment_type = message.text.strip()
    if segment_type not in texts.SEGMENT_LABELS:
        await message.answer("Неверный сегмент. Попробуй ещё раз.")
        return
    await state.update_data(segment_type=segment_type)
    if segment_type == "custom_sql":
        await state.set_state(BroadcastNowStates.segment_custom)
        await message.answer("Введи условие WHERE без слова WHERE")
    else:
        await state.set_state(BroadcastNowStates.text)
        await message.answer("Введи текст рассылки:")


@router.message(BroadcastNowStates.segment_custom)
async def broadcast_now_custom(message: Message, state: FSMContext) -> None:
    await state.update_data(segment_custom=message.text.strip())
    await state.set_state(BroadcastNowStates.text)
    await message.answer("Введи текст рассылки:")


@router.message(BroadcastNowStates.text)
async def broadcast_now_text(message: Message, state: FSMContext, db: Database) -> None:
    await state.update_data(text=message.html_text or message.text or "")
    data = await state.get_data()
    segment = {"type": data["segment_type"]}
    if data["segment_type"] == "custom_sql":
        segment["where"] = data.get("segment_custom", "")
    users = await db.list_users_for_segment(segment)
    total = len(users)
    await state.update_data(segment=segment, audience=total)
    await state.set_state(BroadcastNowStates.confirm)
    await message.answer(
        texts.BROADCAST_CONFIRM.format(
            segment_name=texts.SEGMENT_LABELS.get(data["segment_type"], data["segment_type"]),
            total=total,
        )
        + " Ответь да/нет."
    )


@router.message(BroadcastNowStates.confirm)
async def broadcast_now_confirm(
    message: Message,
    state: FSMContext,
    broadcast_service: BroadcastService,
) -> None:
    answer = message.text.strip().lower()
    if answer not in {"да", "нет"}:
        await message.answer("Ответь «да» или «нет».")
        return
    if answer == "нет":
        await state.clear()
        await message.answer("Мгновенная рассылка отменена.")
        return
    data = await state.get_data()
    await message.answer(texts.BROADCAST_STARTED.format(total=data.get("audience", 0)))
    await state.clear()
    segment = data["segment"]
    total, sent, failed = await broadcast_service.broadcast(data["text"], segment, schedule_id=None)
    await message.answer(texts.BROADCAST_FINISHED.format(sent=sent, failed=failed))


@router.message(Command("stats"))
async def stats(message: Message, db: Database) -> None:
    stats_data = await db.get_stats()
    totals = stats_data.get("totals", {})
    deliveries = stats_data.get("deliveries", [])
    lines = [
        f"Пользователей: {totals.get('total', 0)}",
        f"Подписаны: {totals.get('subscribed', 0)}",
        f"Отписаны: {totals.get('unsubscribed', 0)}",
        f"Доноры: {totals.get('donors', 0)}",
    ]
    if deliveries:
        lines.append("Последние рассылки:")
        for delivery in deliveries:
            lines.append(
                f"• #{delivery['schedule_id']} — отправлено {delivery['sent']}, ошибок {delivery['failed']}"
            )
    await message.answer("\n".join(lines))


@router.message(Command("events_push_token"))
async def events_push_token(message: Message, settings: Settings) -> None:
    await message.answer(f"Токен для вебхуков: <code>{settings.events_webhook_token}</code>")


def _parse_interval(raw: str) -> Dict[str, int]:
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    result: Dict[str, int] = {}
    for part in parts:
        if "=" not in part:
            raise ValueError("Используй формат minutes=30, hours=2 и т.д.")
        key, value = part.split("=", 1)
        key = key.strip()
        try:
            result[key] = int(value.strip())
        except ValueError as exc:
            raise ValueError("Значения интервала должны быть числами") from exc
    if not result:
        raise ValueError("Укажи хотя бы один параметр интервала")
    return result
