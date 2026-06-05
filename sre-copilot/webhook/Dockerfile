FROM python:3.11-slim

WORKDIR /app

COPY ../agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ../agent/ ./agent/
COPY . ./webhook/

ENV PORT=8090

EXPOSE 8090

CMD ["gunicorn", "--bind", "0.0.0.0:8090", "--workers", "1", "--timeout", "120", "webhook.main:app"]
