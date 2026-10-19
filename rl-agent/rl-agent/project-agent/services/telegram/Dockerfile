FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/telegram/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/telegram/ .

# Create data directory
RUN mkdir -p /app/data

CMD ["python", "-u", "main.py"]

