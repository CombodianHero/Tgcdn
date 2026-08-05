FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal -- Telethon/cryptg pull in build tools if a wheel
# isn't available for the target platform, so keep pip's cache and a C
# toolchain around just in case, then it's fine to leave build-essential out
# unless you hit a "failed building wheel" error, in which case add it.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite + session config live here; harmless if the platform's disk is
# ephemeral, just means it resets on redeploy (see README).
RUN mkdir -p /app/data

ENV DATA_DIR=/app/data
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
