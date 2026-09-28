from sqlalchemy import text

from databases.engine_start import engine, SessionLocal, get_db
from databases.users_db import Base, User
from databases.businesses_db import Business
import notifications.models  # noqa: F401 — таблицы радара (radar_events и др.) на том же Base

# create_all не добавляет колонки в уже существующие таблицы — досоздаём их сами, пока нет Alembic
NEW_COLUMNS = (
    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "ALTER TABLE user_businesses ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS headcount INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_settings JSONB",
    "ALTER TABLE businesses ADD COLUMN IF NOT EXISTS employees_num INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notifications_seen_at TIMESTAMPTZ",
    "ALTER TABLE businesses ALTER COLUMN employees_num DROP NOT NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS awaiting_mid VARCHAR(64)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS awaiting_since TIMESTAMPTZ",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS text TEXT",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS keyboard JSONB",
    "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS okved_main VARCHAR(20)",
    "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS region_code VARCHAR(2)",
    "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS has_licenses BOOLEAN",
    "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS patent_from DATE",
    "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS patent_to DATE",
    "ALTER TABLE radar_events ADD COLUMN IF NOT EXISTS in_list BOOLEAN NOT NULL DEFAULT false",
    "DROP TABLE IF EXISTS feed_items",  # прежняя лента законов, код её больше не использует
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for statement in NEW_COLUMNS:
            await conn.execute(text(statement))
