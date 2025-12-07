FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/monitor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY tweets/ ./shared/tweets/
COPY users/ ./shared/users/
COPY agent/ ./shared/agent/
COPY db/ ./shared/db/
COPY config.py ./shared/

# Copy config to root
COPY config.py .

# Copy service code
COPY services/monitor/main.py .

# Create data directory
RUN mkdir -p /app/data

# Set Python path
ENV PYTHONPATH=/app:/app/shared

CMD ["python", "-u", "main.py"]

