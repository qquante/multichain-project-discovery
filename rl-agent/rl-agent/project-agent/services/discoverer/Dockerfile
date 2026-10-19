FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY services/discoverer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY config.py /app/shared/
COPY agent/ /app/shared/agent/
COPY users/ /app/shared/users/
COPY tweets/ /app/shared/tweets/
COPY db/ /app/shared/db/

# Copy service
COPY services/discoverer/main.py .

CMD ["python", "-u", "main.py"]

