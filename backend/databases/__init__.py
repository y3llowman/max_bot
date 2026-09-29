from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from databases.engine_start import engine, SessionLocal, get_db
from databases.users_db import Base, User
from databases.businesses_db import Business
import notifications.models

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
BASELINE = "0001"
BASELINE_TABLES = ("users", "businesses", "user_businesses", "business_profiles", "registry_snapshots",
                   "radar_events", "notifications", "laws")
MIGRATION_LOCK = 7243150

LEGACY_COLUMNS = (
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
    "DROP TABLE IF EXISTS feed_items",
)


def migrate(connection) -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.attributes["connection"] = connection
    tables = inspect(connection).get_table_names()
    if "users" in tables and "alembic_version" not in tables:
        Base.metadata.create_all(connection, tables=[Base.metadata.tables[name] for name in BASELINE_TABLES])
        for statement in LEGACY_COLUMNS:
            connection.execute(text(statement))
        command.stamp(config, BASELINE)
    command.upgrade(config, "head")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"SELECT pg_advisory_xact_lock({MIGRATION_LOCK})"))
        await conn.run_sync(migrate)
