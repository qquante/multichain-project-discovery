FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir redis requests

# Copy service files
COPY services/telegram-chains/main.py /app/

# Copy ONLY chain_utils (not full agent package to avoid dependency chain)
RUN mkdir -p /app/agent
COPY agent/chain_utils.py /app/agent/
RUN touch /app/agent/__init__.py

# Run
CMD ["python", "-u", "main.py"]

