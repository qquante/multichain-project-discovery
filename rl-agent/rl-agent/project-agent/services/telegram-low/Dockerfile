FROM python:3.11-slim

WORKDIR /app

COPY services/telegram-low/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/telegram/formatter.py .
COPY services/telegram-low/main.py .

RUN mkdir -p /app/data

CMD ["python", "main.py"]



