FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN addgroup --system routex && adduser --system --ingroup routex routex

WORKDIR /app

COPY pyproject.toml ./
COPY routex_bot ./routex_bot
COPY assets ./assets
COPY README.md ./

RUN pip install --upgrade pip && pip install .

COPY . .
RUN mkdir -p /app/data && chown -R routex:routex /app

USER routex

CMD ["python", "-m", "routex_bot.main"]
