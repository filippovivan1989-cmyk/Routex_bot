FROM python:3.11-slim

WORKDIR /app

COPY service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY service /app/service
COPY bot /app/bot

ENV PYTHONPATH=/app

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8080"]
