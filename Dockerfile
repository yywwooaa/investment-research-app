FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app

COPY frontend/package*.json ./frontend/
RUN npm --prefix frontend ci

COPY frontend ./frontend
RUN npm --prefix frontend run build


FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VRW_DATA_SOURCE=yahoo
ENV VRW_LOCAL_DATA_DIR=/tmp/variant-research-workbench
ENV VRW_SQLITE_PATH=/tmp/variant-research-workbench/workbench.sqlite3

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY app.py ./app.py
COPY backend ./backend
COPY data/fixtures ./data/fixtures
COPY scripts ./scripts
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

