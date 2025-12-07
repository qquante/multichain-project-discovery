FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir redis requests python-dotenv

# Copy shared modules
COPY agent/ /app/agent/
COPY db/ /app/db/
COPY users/ /app/users/
COPY tweets/ /app/tweets/
COPY config.py /app/

# Copy service
COPY services/calendar-alerter/main.py /app/

# Run
CMD ["python", "-u", "main.py"]

