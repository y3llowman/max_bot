# MAX Mini App + FastAPI + PostgreSQL

Шаблон для хакатона: Mini App внутри мессенджера MAX (React + Vite, папка `frontend/`), FastAPI backend и PostgreSQL. Что сейчас умеет продукт — в [CURRENT_STATE.md](CURRENT_STATE.md).

## Что было изменено относительно исходного шаблона

Исходный проект был шаблоном Telegram WebApp: SvelteKit + FastAPI + MongoDB/Beanie/Motor + RabbitMQ + JWT. Это видно в исходной конфигурации и `README`, а также в исходных auth/db-модулях. Теперь активный runtime переведён на MAX Bridge и PostgreSQL/SQLAlchemy. Старые Telegram/RabbitMQ файлы и SvelteKit-фронтенд удалены.

### Новый стек

- **MAX Mini App / MAX Bridge** — окружение приложения внутри MAX.
- **React + Vite + TypeScript** (`frontend/`) — UI.
- **FastAPI** — REST API.
- **PostgreSQL** — основная БД.
- **SQLAlchemy 2 async + asyncpg** — доступ к PostgreSQL.
- **MAX initData + HMAC-SHA256** — проверка личности пользователя.
- **JWT** — сессия после первичной авторизации.
- **Docker Compose** — локальный запуск.

Официальная документация MAX описывает MAX Bridge как библиотеку, предоставляющую `window.WebApp`, включая `initData` и `initDataUnsafe`; `initData` предназначен для серверной проверки, а `initDataUnsafe` нельзя использовать как доказательство личности. urlMAX Bridge documentationhttps://dev.max.ru/docs/webapps/bridge

## Быстрый запуск

### 1. Переменные окружения

```bash
cp .env.example .env
```

Заполни:

```env
MAX_TOKEN=...
SECRET_KEY=...
```

`MAX_TOKEN` — секрет бота MAX. Никогда не коммить его в Git.

### 2. Docker

```bash
docker compose up --build
```

После запуска:

```text
http://localhost:8000/          # frontend
http://localhost:8000/health    # healthcheck
http://localhost:8000/docs      # Swagger/OpenAPI
```

Для реального MAX Mini App нужен публичный HTTPS URL. Официальная документация MAX указывает, что Mini Apps работают внутри чат-ботов MAX и приложение должно быть размещено по HTTPS. urlMAX Mini Apps introductionhttps://dev.max.ru/docs/webapps/introduction

## Как работает Docker в этом проекте и зачем он нужен

### Зачем он вообще нужен

Без Docker, чтобы запустить проект, пришлось бы вручную на каждой машине:

- поставить Python нужной версии + все pip-зависимости;
- поставить Node.js нужной версии и собрать frontend;
- поставить и настроить PostgreSQL, создать базу и пользователя;
- следить, чтобы версии всего этого совпадали у всех в команде и на сервере ("у меня локально работает" — классическая проблема).

Docker решает это так: всё окружение (ОС-слой, Python, зависимости, собранный frontend) один раз описывается в виде инструкции (`Dockerfile`) и упаковывается в **образ** (image) — неизменяемый архив со всем нужным внутри. Из образа поднимается **контейнер** — реально работающий изолированный процесс со своей файловой системой, но использующий ядро хост-ОС (поэтому легче полноценной виртуальной машины). Один и тот же образ запускается одинаково у тебя, у товарища по команде и на проде.

### Из чего состоит Docker-часть проекта

```text
Dockerfile           # инструкция "как собрать образ backend"
docker-compose.yml   # инструкция "какие контейнеры поднять и как их связать"
.dockerignore         # что НЕ копировать внутрь образа (node_modules, .git, .venv...)
```

**`Dockerfile`** собирает образ в два этапа (multi-stage build):

```text
Этап 1 (node:20)          Этап 2 (python:3.12-slim)
────────────────          ──────────────────────────
npm install                pip install зависимости (через uv)
npm run build         →    COPY backend/
(получили статику          COPY собранный frontend из этапа 1
 SvelteKit)                CMD python backend/main.py
```

Первый этап нужен только чтобы собрать frontend в статические файлы — сам Node.js в финальном образе не остаётся, там только Python + собранная статика. Это уменьшает итоговый образ.

**`docker-compose.yml`** описывает не один контейнер, а систему из двух сервисов:

```text
┌──────────────────────┐        ┌────────────────────────┐
│  backend (FastAPI)    │──TCP──▶│  postgres (PostgreSQL)  │
│  порт 8000 наружу      │        │  порт 5433 наружу        │
└──────────────────────┘        └────────────────────────┘
```

Контейнеры видят друг друга по имени сервиса как по hostname — поэтому в `DATABASE_URL` внутри `docker-compose.yml` указан хост `postgres`, а не `localhost`: `postgresql+asyncpg://max:max@postgres:5432/maxapp`. С хоста (например, для бота, запущенного вне Docker) та же база доступна как `localhost:5433` — порт 5433, чтобы не конфликтовать с локально установленным PostgreSQL. `depends_on: condition: service_healthy` заставляет backend ждать, пока Postgres не пройдёт `healthcheck` (`pg_isready`) — иначе backend упадёт при старте, пытаясь подключиться к ещё не готовой базе. `volumes: postgres_data` хранит данные Postgres отдельно от контейнера, поэтому `docker compose down` (без `-v`) их не стирает.

### Команды

```bash
docker compose up --build      # собрать образы и запустить оба контейнера
docker compose up -d           # то же самое, но в фоне
docker compose logs -f backend # смотреть логи backend в реальном времени
docker compose down            # остановить и удалить контейнеры (данные Postgres останутся в volume)
docker compose down -v         # то же самое, но и данные Postgres тоже удалить
```

## Как работает авторизация

### Шаг 1 — MAX открывает frontend

`frontend/index.html` подключает MAX Bridge:

```html
<script src="https://st.max.ru/js/max-web-app.js"></script>
```

После этого доступен:

```js
window.WebApp
```

Frontend получает:

```js
WebApp.initData
```

### Шаг 2 — JS отправляет initData в FastAPI

```ts
await fetch("/api/user/auth", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ initData: WebApp.initData }),
});
```

### Шаг 3 — FastAPI проверяет подпись

Backend не доверяет `user.id`, который просто прислал браузер. Он получает подписанную строку `initData` и проверяет HMAC.

### Шаг 4 — PostgreSQL

После успешной проверки пользователь создаётся или обновляется в таблице `users`.

### Шаг 5 — JWT

Backend выдаёт access token. Все следующие защищённые запросы используют:

```http
Authorization: Bearer <token>
```


## API

### `POST /api/user/auth`

Body:

```json
{
  "initData": "auth_date=...&user=...&hash=..."
}
```

Response:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

### `GET /api/user/me`

Header:

```http
Authorization: Bearer eyJ...
```

Response:

```json
{
  "id": 123,
  "username": "example",
  "first_name": "Ivan",
  "last_name": "Ivanov",
  "language_code": "ru",
  "photo_url": "https://...",
  "is_staff": false
}
```

### `GET /health`

```json
{"status":"ok"}
```

## Как думать о FastAPI backend

Самая важная схема:

```text
JavaScript
   │ fetch()
   ▼
HTTP request
   │
   ▼
FastAPI router
   │
   ├── Pydantic validation
   ├── Depends(auth)
   └── endpoint
          │
          ▼
      SQLAlchemy
          │
          ▼
      PostgreSQL
          │
          ▼
      Python object
          │
          ▼
      JSON response
          │
          ▼
      JavaScript
```

Если ты понял эту цепочку, то уже понимаешь основу большинства современных web backend'ов.

## Текущая структура backend

```text
backend/
├── main.py                    # FastAPI app, entrypoint контейнера
├── app/
│   ├── api/routes/            # HTTP endpoints (users, company, tasks, settings)
│   └── api/depends.py         # FastAPI-зависимости (auth и т.д.)
├── databases/                 # всё, что касается БД
│   ├── engine_start.py        # async engine + SessionLocal + get_db
│   ├── users_db.py            # Base (DeclarativeBase) + модель User, таблица `users`
│   └── businesses_db.py       # модели Business и UserBusiness, таблицы `businesses` и `user_businesses`
├── data_fetching/
│   └── rmsp_client.py         # клиент реестра МСП (rmsp.nalog.ru), поиск компании по ИНН
├── bot/                       # бот MAX: онбординг, кнопки под напоминаниями
└── core/
    ├── config.py
    ├── security.py
    └── env.py
```

Таблицы `users`, `businesses` и `user_businesses` живут на одном `Base.metadata` в `databases/users_db.py`, поэтому `databases/__init__.py` создаёт их все одним вызовом `init_db()` при старте приложения (`Base.metadata.create_all`).

### Схема данных

- **`users`** — участник MAX: `max_user_id`, `username`, `first_name`, `last_name`, `photo_url`.
- **`user_businesses`** — какие ИНН отслеживает пользователь, связь многие-ко-многим: `user_id` (`ForeignKey("users.id")`) + `inn` (`ForeignKey("businesses.inn")`), составной первичный ключ. У пользователя может быть несколько ИНН, один ИНН могут отслеживать несколько пользователей.
- **`businesses`** — данные компании из реестра МСП, ключ — `inn`: `name`, `subject_type` (`UL`/`IP`), `category`, `ogrn`, `main_activity_code/name` (ОКВЭД), `region_code`, даты регистрации/исключения из реестра, контакты, флаги (`has_licenses`, `is_hitech`, `is_partnership`, `is_social`).
- Заполняется через `data_fetching/rmsp_client.py::fetch_by_inn(inn)` — POST-запрос к недокументированному эндпоинту `rmsp.nalog.ru/search-proc.json`. Пока это отдельный скрипт, не подключённый как FastAPI-роут.

Дальше по мере роста доменной модели сюда стоит добавить `app/schemas/` (Pydantic DTO) и `app/services/` (бизнес-логика), чтобы не разрастался `main.py`/роуты.

Например:

```text
POST /api/orders
       ↓
orders.py
       ↓
OrderService.create_order()
       ↓
SQLAlchemy
       ↓
PostgreSQL
```

Так API остаётся тонким, а бизнес-логика не привязывается к HTTP.

## PostgreSQL vs MongoDB

Для хакатонного приложения я выбрал PostgreSQL.

Причины:

- пользователи, заказы, задачи, заявки и связи между сущностями естественно описываются таблицами;
- foreign keys защищают целостность данных;
- транзакции удобны для операций вида «создать заказ + записать событие»;
- SQL проще анализировать и отлаживать;
- PostgreSQL отлично подходит и для маленького MVP, и для дальнейшего роста.

MongoDB имеет смысл, если данные действительно документные и схема постоянно меняется. Для обычного Mini App backend PostgreSQL здесь практичнее.

## Что пока сознательно упрощено

1. Таблицы создаются через `Base.metadata.create_all()` при старте. Для production нужен Alembic.
2. JWT хранится в `localStorage` для простоты демо. Для более строгого production-сценария можно использовать возможности `SecureStorage` MAX Bridge.
3. Нет rate limiting.
4. Нет полноценного слоя service/repository — для хакатонного MVP это избыточно, его стоит добавить при росте логики.

## Важная безопасность

Никогда не делай так:

```ts
fetch("/api/user/me?user_id=" + user.id)
```

и не доверяй `user_id` из браузера.

Правильная модель:

```text
MAX → signed initData → backend validates signature
                              ↓
                         trusted user id
                              ↓
                         PostgreSQL
```

Также никогда не публикуй `MAX_BOT_TOKEN` или `SECRET_KEY` в GitHub.

## Следующий шаг для хакатона

Поверх этого каркаса можно сразу добавлять доменную модель проекта:

```text
User
 ├── Profile
 ├── Tasks / Orders
 ├── Actions
 └── Notifications
```

Для каждой сущности делаем:

```text
SQLAlchemy model
      ↓
Pydantic schemas
      ↓
FastAPI router
      ↓
service/business logic
      ↓
frontend fetch()
      ↓
Svelte UI
```

Именно этот цикл стоит освоить: после него добавление новых экранов и функций превращается в повторение одной и той же понятной схемы.

## License

MIT.
