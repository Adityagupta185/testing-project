# Pre-built: run `npx vite build` locally first, then deploy.
# dist/ is the React build output served as static by Flask.
FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir flask flask-cors gunicorn requests cryptography google-cloud-firestore

COPY server.py .
COPY dist ./static

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "server:app"]
