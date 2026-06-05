FROM python:3.11-slim

WORKDIR /app

# Node.js LTS — required to run the Dynatrace MCP server via npx
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Pre-cache the Dynatrace MCP package so first agent run isn't slow
RUN npx -y @dynatrace-oss/dynatrace-mcp --version 2>/dev/null || true

COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ ./agent/
COPY webhook/ ./webhook/

ENV PYTHONPATH=/app
ENV PORT=8080

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "3600", "webhook.main:app"]
