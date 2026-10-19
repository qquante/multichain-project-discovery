FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for caching
COPY services/alpha-hunter/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules (REQUIRED for saving to tweets.db)
COPY tweets/ /app/tweets/
COPY db/ /app/db/
COPY config.py /app/

# Copy service code
COPY services/alpha-hunter/main.py .

CMD ["python", "main.py"]
