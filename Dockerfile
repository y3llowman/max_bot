FROM node:20 AS frontend-builder
WORKDIR /app
COPY miniapp/package.json miniapp/package-lock.json ./
RUN npm ci
COPY miniapp/ ./
RUN npm run build

FROM python:3.12-slim AS backend
WORKDIR /code
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=frontend-builder /app/build ./miniapp/build
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "backend/main.py"]
