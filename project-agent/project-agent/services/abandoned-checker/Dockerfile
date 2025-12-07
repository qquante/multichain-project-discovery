FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY services/abandoned-checker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY config.py /app/
COPY tweets/ /app/tweets/
COPY users/ /app/users/
COPY agent/ /app/agent/
COPY db/ /app/db/

# Copy shared to /app/shared for imports
COPY config.py /app/shared/
COPY tweets/ /app/shared/tweets/
COPY users/ /app/shared/users/
COPY agent/ /app/shared/agent/
COPY db/ /app/shared/db/

# Copy service code
COPY services/abandoned-checker/main.py /app/

CMD ["python", "-u", "main.py"]

