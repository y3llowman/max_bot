import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from core.env import ENV
from databases import Base


def run(connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async() -> None:
    engine = create_async_engine(ENV.DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(run)
    await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    asyncio.run(run_async())
