# FloodPulse production image: builds the React app, then runs FastAPI serving both the API
# and the built site from one origin. Secrets are never baked in; they arrive as environment
# variables at run time (see deploy/docker-compose.yml).

FROM node:22-bookworm-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/app backend/app
COPY backend/alembic backend/alembic
COPY backend/alembic.ini backend/alembic.ini
COPY backend/models backend/models
# Read at run time: map evidence, the Karnataka place directory and the state boundary used by the risk engine.
COPY data/processed data/processed
COPY data/reference data/reference
COPY frontend/src/data/karnatakaHomeBoundary.json frontend/src/data/karnatakaHomeBoundary.json
COPY --from=web /src/frontend/dist frontend/dist
COPY deploy/telegram_webhook.py deploy-tools/telegram_webhook.py
RUN useradd --system --uid 10001 --home /nonexistent floodpulse && mkdir -p /cache && chown floodpulse /cache
USER floodpulse
WORKDIR /app/backend
ENV FLOODPULSE_STATIC_DIR=/app/frontend/dist FLOODPULSE_RISK_CACHE_DIR=/cache
EXPOSE 8000
# One worker: the risk engine and the place lookup keep in-memory caches and rate limits.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
