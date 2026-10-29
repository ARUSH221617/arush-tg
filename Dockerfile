FROM python:3.11-slim

# Install system dependencies for audio/image processing and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV VAULT_DATA_DIR=/app/data
ENV HEALTHCHECK_PORT=8089

# Expose watchdog HTTP health check port
EXPOSE 8089

# Persist data directory
VOLUME ["/app/data"]

# Self-healing container healthcheck (Phase 7.3)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8089/health || exit 1

CMD ["python", "run.py"]
