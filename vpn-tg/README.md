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

## Пошаговый деплой на свой сервер

1. **Подготовьте сервер.** Подойдёт любая актуальная Linux-система (Ubuntu 22.04+, Debian 12, Rocky Linux 9 и т.п.) с открытым доступом
   к интернету и установленным `git`.
2. **Установите Docker Engine и Compose Plugin.**
   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo apt-get install -y docker-compose-plugin  # для Debian/Ubuntu; для других ОС используйте пакетный менеджер
   sudo usermod -aG docker $USER                   # опционально, чтобы запускать docker без sudo
   newgrp docker                                   # применить группу без выхода из shell
   ```
3. **Склонируйте репозиторий на сервер.**
   ```bash
   git clone https://github.com/<your-org>/<your-repo>.git vpn-tg
   cd vpn-tg
   ```
   > Если проект уже загружен, просто скопируйте содержимое папки `vpn-tg/` на сервер.
4. **Заполните конфигурацию.**
   ```bash
   cp config/.env.example config/.env
   nano config/.env              # либо используйте любой другой редактор
   ```
   - Укажите `BOT_TOKEN`, `SERVICE_HMAC_SECRET`, `SERVICE_BASE_URL` (обычно `http://service:8080` для docker-compose),
     `DEFAULT_PROTOCOL`, `DEFAULT_INBOUND_ID` и другие параметры.
   - Убедитесь, что `SERVICE_PORT` свободен на сервере (по умолчанию 8080). Если нужно, замените на другое значение.
5. **Настройте `config/config.yaml`.** Проверьте блоки `links`, `texts` и `postman_mapping` — значения должны соответствовать вашей панели
   и экспортированной Postman-коллекции.
6. **Загрузите Postman-файлы.** Поместите экспорт `postman.collection.json` и (при необходимости) `postman.environment.json`
   в директорию `config/`.
7. **Запустите сервисы.**
   ```bash
   docker compose up --build -d
   ```
   - Флаг `-d` запускает контейнеры в фоне; можно опустить его, чтобы видеть логи.
   - Для просмотра логов бота и сервиса используйте:
     ```bash
     docker compose logs -f service
     docker compose logs -f bot
     ```
8. **Проверьте работу.** Откройте Telegram-бота, выполните `/start` и пройдите сценарии меню. Убедитесь, что запросы к сервису
   выполняются успешно.
9. **Обновление и перезапуск.** При изменениях в коде/конфигурации выполните:
   ```bash
   git pull
   docker compose up --build -d
   ```
   Docker автоматически пересоберёт контейнеры и применит обновления.

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
