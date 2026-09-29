import asyncio
import itertools
import logging
import tempfile
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from data_fetching import msp_open_data
from data_fetching.msp_open_data import MspRecord
from databases.businesses_db import MspRegistryEntry, MspRegistryLoad
from databases.engine_start import SessionLocal, engine

logger = logging.getLogger(__name__)

LOAD_LOCK = 7243151
BATCH = 5000
FIELDS = [f.name for f in fields(MspRecord)]


async def find(inn: str) -> MspRecord | None:
    async with SessionLocal() as db:
        entry = await db.get(MspRegistryEntry, inn)
    return MspRecord(**{name: getattr(entry, name) for name in FIELDS}) if entry else None


async def current_load() -> MspRegistryLoad | None:
    async with SessionLocal() as db:
        return await db.scalar(select(MspRegistryLoad).order_by(MspRegistryLoad.id.desc()).limit(1))


async def is_complete() -> bool:
    load = await current_load()
    return load is not None and load.kind == "full"


async def examples(limit: int = 3) -> list[MspRecord]:
    async with SessionLocal() as db:
        entries = await db.scalars(select(MspRegistryEntry).where(MspRegistryEntry.subject_type == "UL")
                                   .order_by(MspRegistryEntry.inn).limit(limit))
        return [MspRecord(**{name: getattr(entry, name) for name in FIELDS}) for entry in entries]


def source_note(load: MspRegistryLoad | None) -> str:
    if load is None:
        return "реестр МСП (открытые данные ФНС)"
    when = f"{load.data_date:%d.%m.%Y}" if load.data_date else f"{load.loaded_at:%d.%m.%Y}"
    return (f"реестр МСП, открытые данные ФНС на {when}" if load.kind == "full"
            else f"реестр МСП, срез открытых данных ФНС на {when}")


async def load(records, kind: str, source: str) -> MspRegistryLoad:
    count, data_date = 0, None
    async with engine.begin() as conn:
        await conn.execute(text(f"SELECT pg_advisory_xact_lock({LOAD_LOCK})"))
        await conn.execute(delete(MspRegistryEntry))
        while True:
            chunk = await asyncio.to_thread(lambda: list(itertools.islice(records, BATCH)))
            if not chunk:
                break
            data_date = data_date or chunk[0][0]
            await conn.execute(insert(MspRegistryEntry).on_conflict_do_nothing(),
                               [asdict(record) for _, record in chunk])
            count += len(chunk)
        parsed = datetime.strptime(data_date, "%d.%m.%Y").date() if data_date else None
        await conn.execute(insert(MspRegistryLoad).values(kind=kind, source=source[:500], data_date=parsed,
                                                          records=count))
    logger.info("msp registry: %s records loaded (%s, %s)", count, kind, source)
    return await current_load()


async def ensure_loaded() -> None:
    async with SessionLocal() as db:
        loaded = await db.scalar(select(func.count()).select_from(MspRegistryLoad))
    if not loaded:
        await load(msp_open_data.read_slice(), "slice", msp_open_data.SLICE.name)


async def refresh_full() -> MspRegistryLoad:
    url = await asyncio.to_thread(msp_open_data.latest_url)
    with tempfile.TemporaryDirectory() as folder:
        archive = Path(folder) / "rsmp.zip"
        await asyncio.to_thread(msp_open_data.download, url, archive)
        return await load(msp_open_data.read_zip(archive), "full", url)
