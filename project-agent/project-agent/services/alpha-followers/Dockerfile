FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir redis requests

# Copy service
COPY services/alpha-followers/main.py /app/

# Shared modules
COPY agent/ /app/shared/agent/
COPY users/ /app/shared/users/
COPY db/ /app/shared/db/
COPY config.py /app/shared/

# Set PYTHONPATH
ENV PYTHONPATH=/app:/app/shared

CMD ["python", "-u", "main.py"]

