FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir requests

COPY services/telegram-chains-callback/main.py /app/
COPY agent/ /app/shared/agent/
COPY db/ /app/shared/db/
COPY users/ /app/shared/users/
COPY tweets/ /app/shared/tweets/
COPY config.py /app/shared/

ENV PYTHONPATH=/app:/app/shared

CMD ["python", "-u", "main.py"]

