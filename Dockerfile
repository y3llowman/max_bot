FROM node:20 AS frontend-builder
WORKDIR /app
COPY miniapp/package.json miniapp/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY miniapp/ ./
RUN npm run build

FROM python:3.12-slim AS backend
WORKDIR /code
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt ./
RUN pip install --no-cache-dir --root-user-action=ignore uv==0.12.13 \
    && uv pip install --system --no-cache -r requirements.txt \
    && useradd --create-home --uid 10001 app
COPY backend/ ./backend/
COPY --from=frontend-builder /app/build ./miniapp/build
USER app
EXPOSE 8000
CMD ["python", "backend/main.py"]
