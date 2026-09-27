FROM node:20 AS frontend-builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run prepare && npm run build

FROM python:3.12-slim AS backend
WORKDIR /code
RUN pip install --no-cache-dir uv
COPY pyproject.toml README.md ./
RUN uv pip install --system .
COPY backend/ ./backend/
COPY --from=frontend-builder /app/build ./frontend/build
ENV PYTHONUNBUFFERED=1
CMD ["python", "backend/main.py"]
