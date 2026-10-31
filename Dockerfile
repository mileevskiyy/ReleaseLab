FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd -m -U releaselab && mkdir data && chown releaselab:releaselab data
COPY backend/ ./backend/
COPY --from=web /web/dist ./frontend/dist/
USER releaselab
ENV HOST=0.0.0.0 PORT=3800 DATABASE_PATH=:memory: PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 3800
CMD ["sh", "-c", "exec uvicorn backend.app:create_app --factory --host ${HOST} --port ${PORT} --workers 1"]
