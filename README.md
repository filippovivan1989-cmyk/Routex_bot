# RouteX VPN Telegram Bot

Production-ready Telegram-бот для сервиса RouteX VPN на базе `aiogram 3.x`.

## Возможности

- Выдача и показ личного VPN-ключа через X-UI/py3xui API.
- Управление подпиской на рассылки и фиксация доноров.
- Админ-панель с расписаниями (CRON/interval), мгновенными рассылками и статистикой.
- Хранение данных в SQLite (aiosqlite) с миграциями при старте.
- Очередь доставки с учётом лимитов Telegram и повторными попытками.
- Веб-хуки для внешних событий (`/webhook/event`) с токен-аутентификацией.
- Health-check эндпоинт `/healthz`.

## Структура проекта

```
routex_bot/
├── assets/logo.svg
├── routex_bot/
│   ├── main.py              # Точка входа
│   ├── config.py            # Настройки и загрузка env
│   ├── db.py                # Модели и CRUD на aiosqlite
│   ├── texts.py             # Все текстовые шаблоны
│   ├── handlers/            # Пользовательские и админские хендлеры
│   ├── middlewares/         # Админская авторизация
│   ├── services/            # Интеграции (X-UI, рассылки, планировщик)
│   └── web/                 # aiohttp-приложение (healthz, webhook)
├── assets/                  # Медиа
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Подготовка окружения

Создайте файл `.env` по образцу ниже:

```
BOT_TOKEN=123456:ABCDEF
ADMIN_IDS=11111111,22222222
TZ=Europe/Helsinki
CLOUDTIPS_LINK=https://pay.cloudtips.ru/p/EXAMPLE
PANEL_URL=http://185.254.190.58:54321/panel
PANEL_LOGIN=admin
PANEL_PASSWORD=secret
EVENTS_WEBHOOK_TOKEN=supersecret
WEBHOOK_URL=
HOST=0.0.0.0
PORT=8080
DATABASE_PATH=./data/routex.sqlite3
GUIDE_URL=https://telegra.ph/RouteX-VPN-Guide-01-01
BATCH_SIZE=30
BATCH_DELAY_SECONDS=1.5
```

По умолчанию бот работает в режиме long-polling и поднимает aiohttp-сервер для `/healthz` и `/webhook/event`.

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
python -m routex_bot.main
```

При первом запуске создаётся база SQLite и запускается планировщик рассылок.

## Docker

```bash
docker compose up --build
```

`docker-compose.yml` создаёт volume `./data` для базы и пробрасывает порт 8080 (веб-хуки/healthcheck).

## Админские команды

- `/admin` — показать меню администратора.
- `/schedule_add` — мастер создания расписания (название → тип → параметры → текст → сегмент → подтверждение).
- `/schedule_list` — список расписаний с ID, статусом и ближайшим запуском.
- `/schedule_toggle <id>` — включить/выключить рассылку.
- `/schedule_delete <id>` — удалить расписание.
- `/broadcast_now` — мгновенная рассылка по выбранному сегменту с предварительной оценкой аудитории.
- `/events_push_token` — показать токен для внешних веб-хуков.
- `/stats` — статистика пользователей и последних рассылок.

## Сегменты пользователей

- `all_subscribed` — все пользователи с активной подпиской (по умолчанию).
- `no_key` — пользователи без сгенерированного ключа.
- `inactive_30d` — не взаимодействовали 30+ дней.
- `donors` — нажимали кнопку доната.
- `custom_sql` — произвольный `WHERE` (например, `is_donor = 1 AND key IS NOT NULL`).

## Веб-хуки внешних событий

`POST /webhook/event` с заголовком `X-Admin-Token: <EVENTS_WEBHOOK_TOKEN>`:

```bash
curl -X POST "http://localhost:8080/webhook/event" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: supersecret" \
  -d '{
        "event_type": "donation_reminder",
        "payload": {"amount": "5€", "message": "Спасибо за поддержку!"}
      }'
```

Событие ставится в очередь и рассылается по сегменту `all_subscribed` или по шаблону из таблицы `settings` (`event_template:<event_type>`).

## Как это работает

1. **Инициализация** — при старте загружаются настройки, выполняется миграция SQLite и поднимается `AsyncIOScheduler` с расписаниями из таблицы `schedules`.
2. **Очередь доставки** — сообщения рассылаются батчами по 30 пользователей с задержкой 1.5 с, учитываются лимиты Telegram и повторные попытки при `FloodWait`.
3. **Сегментация** — целевая аудитория строится SQL-фильтрами (готовые сегменты + `custom_sql`). Для рассылок сохраняются записи в `deliveries` со статусами `queued/sent/failed`.
4. **Ключи VPN** — команда `/getkey` вызывает API панели X-UI (через `services/xui_client`) и кэширует результат в таблице `users`.
5. **Логи и аудит** — все ключевые действия админов попадают в `audit_log`, а веб-хуки логируются через `structlog`.

## Пример CRON-интервалов

- `0 10 * * 1` — каждый понедельник в 10:00 по таймзоне из `TZ`.
- `0 */6 * * *` — каждые 6 часов.
- `minutes=30` — интервал каждые 30 минут.
- `hours=24` — раз в сутки.

## Полезные команды для пользователя

- `/start` — приветствие, логотип, клавиатура с быстрыми действиями.
- `/getkey` — получить или восстановить свой ключ.
- `/mykey` — показать сохранённый ключ и гайд.
- `/donate` — ссылка на поддержку проекта.
- `/optout` / `/optin` — управление подпиской на рассылки.

