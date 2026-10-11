FROM node:24-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 AI_ENABLED=false DATABASE_URL=sqlite:////app/runtime/opspilot.db
COPY backend/ backend/
RUN pip install --no-cache-dir uv==0.13.0 && uv sync --project backend --locked --no-dev
COPY --from=frontend /build/dist/ frontend/dist/
RUN useradd --create-home opspilot && mkdir -p runtime && chown -R opspilot:opspilot /app
USER opspilot
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD ["backend/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=3)"]
CMD ["backend/.venv/bin/python", "-m", "uvicorn", "opspilot.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
