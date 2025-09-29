"""Text templates for RouteX VPN bot."""

from __future__ import annotations

from typing import Dict

WELCOME = (
    "Привет! Это RouteX VPN — быстрый и приватный доступ в сеть.\n"
    "Мы бесплатно выдаём ключи, чтобы ты оставался на связи."
)
START_BUTTONS = {
    "get_key": "Получить ключ",
    "my_key": "Мой ключ",
    "instructions": "Инструкции",
    "donate": "Поддержать проект",
}
GET_KEY_INSTRUCTIONS = (
    "Готово! Скопируй ключ и добавь его в клиент VPN. Подробный гайд — ниже по кнопке."
)
MY_KEY_EMPTY = (
    "У тебя пока нет ключа. Нажми кнопку или команду /getkey, чтобы получить личный ключ."
)
DONATE_TEXT = (
    "RouteX VPN живёт на пожертвования. Любая сумма помогает оплачивать сервера и развивать сервис."
)
OPT_OUT_TEXT = "Ты отписался от рассылок. Возвращайся, если захочешь — команда /optin."
OPT_IN_TEXT = "Отлично! Теперь ты снова будешь получать важные новости и напоминания."
ADMIN_MENU = (
    "<b>Панель администратора RouteX</b>\n"
    "• Рассылки по расписанию\n"
    "• Мгновенная рассылка\n"
    "• Сегменты и фильтры\n"
    "• Статусы доставки\n"
    "• Настройки"
)
SCHEDULE_CREATED = "Рассылка «{name}» создана и будет запускаться по расписанию."
SCHEDULE_DISABLED = "Рассылка {id} отключена."
SCHEDULE_ENABLED = "Рассылка {id} активирована."
SCHEDULE_DELETED = "Расписание {id} удалено."
SCHEDULE_LIST_EMPTY = "Активных расписаний пока нет."
BROADCAST_STARTED = "Запущена рассылка. В очереди {total} получателей."
BROADCAST_FINISHED = "Рассылка завершена: {sent} доставлено, {failed} ошибок."
BROADCAST_CONFIRM = "Начать рассылку по сегменту «{segment_name}» для {total} пользователей?"
NO_PERMISSION = "Эта команда только для администраторов."
KEY_RESPONSE = (
    "Твой ключ RouteX VPN:\n"
    "<code>{key}</code>\n\n"
    "Как подключиться: открой клиент XRay/V2Ray и вставь ключ. Подробные инструкции — по кнопке."
)
MY_KEY_RESPONSE = (
    "Вот твой текущий ключ:\n"
    "<code>{key}</code>\n\n"
    "Не делись им с другими. Если нужна помощь — загляни в гайд."
)
INSTRUCTIONS_TEXT = "Подробный гид по настройке: {link}"
NO_RECIPIENTS = "В сегменте сейчас нет пользователей."
EVENT_ACCEPTED = "Событие {event_type} поставлено в очередь."

EVENT_TEMPLATE_FALLBACK = (
    "{greeting}! У нас свежие новости: {payload_message}."
)

SEGMENT_LABELS: Dict[str, str] = {
    "all_subscribed": "Все подписанные",
    "no_key": "Без ключа",
    "inactive_30d": "Неактивные 30 дней",
    "donors": "Доноры",
    "custom_sql": "Произвольный фильтр",
}

HELP_SCHEDULE_SEGMENTS = (
    "Доступные сегменты:\n"
    "• all_subscribed — все с подпиской\n"
    "• no_key — пользователи без ключа\n"
    "• inactive_30d — не взаимодействовали 30+ дней\n"
    "• donors — кто нажимал донат\n"
    "• custom_sql — запрос WHERE (используй с осторожностью)"
)

__all__ = [name for name in globals() if name.isupper()]
