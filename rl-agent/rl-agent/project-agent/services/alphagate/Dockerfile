FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for caching
COPY services/alphagate/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY agent/ /app/agent/
COPY db/ /app/db/
COPY users/ /app/users/
COPY tweets/ /app/tweets/
COPY config.py /app/

# Copy service code
COPY services/alphagate/main.py .

CMD ["python", "main.py"]

