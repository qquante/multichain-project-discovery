FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir redis requests

# Copy service files
COPY services/telegram-chains/main.py /app/

# Run
CMD ["python", "-u", "main.py"]

