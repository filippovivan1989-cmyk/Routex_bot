FROM python:3.11-slim

WORKDIR /app

COPY bot/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY bot /app/bot

ENV PYTHONPATH=/app

CMD ["python", "-m", "bot.main"]
