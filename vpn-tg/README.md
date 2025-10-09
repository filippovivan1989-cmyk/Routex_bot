# VPN Telegram Bot & Service Adapter

Двухкомпонентный проект для Telegram-бота (aiogram 3) и FastAPI-сервиса-адаптера, который вызывает методы панели через Postman-коллекцию и не хранит состояние.

## Структура

```
vpn-tg/
  bot/                  # код aiogram-бота
  service/              # FastAPI адаптер панели
  config/               # конфигурация и Postman экспорт
  tests/                # unit-тесты
  docker-compose.yml    # запуск двух сервисов
```

## Подготовка

1. Скопируйте пример `.env`:
   ```bash
   cp config/.env.example config/.env
   ```
2. Заполните значения в `config/.env`:
   - `BOT_TOKEN` — токен Telegram-бота.
   - `SERVICE_HMAC_SECRET` — общий секрет между ботом и сервисом.
   - `SERVICE_BASE_URL`, `SERVICE_PORT`, `DEFAULT_INBOUND_ID`, `DEFAULT_PROTOCOL` и др.
3. Отредактируйте `config/config.yaml` под свои ссылки и тексты. Проверьте блок `postman_mapping` — названия должны совпадать с именами запросов в вашей коллекции.
4. Экспортируйте Postman collection v2.1 и (при необходимости) environment. Поместите файлы в `config/postman.collection.json` и `config/postman.environment.json`.

## Запуск через Docker

```bash
docker compose up --build
```

- Сервис поднимется на `SERVICE_PORT` (по умолчанию 8080).
- Бот стартует после готовности сервиса и работает через long polling.
- Оба контейнера получают доступ к `config/` как к общему тому.

## Тесты

Локально можно запустить unit-тесты:

```bash
pip install -r service/requirements.txt -r bot/requirements.txt
pytest
```

## Как пользоваться

1. Откройте бота и выполните `/start`.
2. Пройдите сценарий «🔑 → Получить ключ → QR-код» — бот обратится в сервис, который сначала ищет существующий ключ, а при отсутствии создаёт новый.
3. Опция «♻️ Пересоздать ключ» вызывает последовательность Revoke → Issue.
4. Вкладки «Помощь», «Расширение», «Донат» подтягивают тексты и ссылки из `config.yaml`.

## Безопасность и особенности

- Все запросы бота к сервису подписаны HMAC SHA-256 с заголовками `X-Timestamp`, `X-Nonce`, `X-Signature`.
- POST `/api/v1/keys/issue` использует заголовок `Idempotency-Key`, кэш ответа хранится 5 минут.
- Сервис не хранит состояние и проксирует вызовы из Postman-коллекции через адаптер.
- Ответы унифицированы и не содержат тайм-аутов или квот.
