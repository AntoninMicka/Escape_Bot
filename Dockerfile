FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    ESCAPEBOT_ENV=production \
    ESCAPEBOT_DATA_DIR=/data

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY client /app/client

RUN useradd --system --uid 10001 --home /app escapebot && mkdir -p /data && chown escapebot:escapebot /data
USER escapebot
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=3)"

CMD ["uvicorn", "escape_bot.server:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*", "--ws-max-size", "1048576"]
