import asyncio
import logging
import re
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_business, get_current_user
from app.api.schemas import Benefit, Company, Source
from data_fetching import rmsp_client
from databases import get_db
from databases.businesses_db import Business, save_business
from databases.users_db import User
from notifications.models import RegistrySnapshot
from notifications.worker import load_profile, registry_loaded, scan_in_background
from radar.deadlines import CATEGORY_RU, REGIME_RU, headcount_ru, region_name

logger = logging.getLogger(__name__)

router = APIRouter(tags=["company"])


class ConnectRequest(BaseModel):
    inn: str = Field(pattern=r"^(\d{10}|\d{12})$")


async def to_company(db: AsyncSession, business: Business) -> Company:
    full_name = re.sub(r'"([^"]*)"', r"«\1»", business.name)  # ООО "МОСТАР" → ООО «МОСТАР»
    quoted = re.search(r"«[^»]*»", full_name)
    name = quoted.group(0) if quoted else full_name
    # режим — из ответов на вопросы бота, численность — из реестра МСП или ответа (worker.load_profile)
    profile = await load_profile(db, business.inn)
    regime = REGIME_RU.get(profile.tax_regime)
    # КПП — из последней выписки ЕГРЮЛ, она скачивается в фоне после подключения
    egrul = (await db.execute(
        select(RegistrySnapshot.data)
        .where(RegistrySnapshot.inn == business.inn, RegistrySnapshot.source == "egrul")
        .order_by(RegistrySnapshot.id.desc()).limit(1)
    )).scalar_one_or_none() or {}
    return Company(
        name=name,
        full_name=full_name,
        initials="".join(word[0] for word in re.findall(r"\w+", name)[:2]).upper(),
        regime=regime or "Режим налогообложения не указан",
        inn=business.inn,
        kpp=egrul.get("kpp"),
        ogrn=business.ogrn,
        okved=f"{business.main_activity_code} — {business.main_activity_name}",
        category=CATEGORY_RU.get(business.category),
        headcount=headcount_ru(profile),
        region=region_name(business.region_code),
        needs_answers=regime is None or profile.headcount is None,
        source=Source(name="Реестр МСП (ФНС)", demo=False, updated_at=business.updated_at.replace(microsecond=0)),
        benefits=[Benefit(title=b.title, basis=b.basis, url=b.url) for b in profile.headcount_benefits()],
    )


async def load_from_registry(db: AsyncSession, user: User, inn: str) -> Business:
    try:
        record = await asyncio.to_thread(rmsp_client.fetch_by_inn, inn)
    except Exception as exc:  # ФНС не ответила — 503, чтобы мини-приложение не путало это с ошибкой сервера
        raise HTTPException(status_code=503, detail="SME registry is unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="INN not found in the SME registry")
    business = await save_business(db, user.id, record)
    await registry_loaded(inn, asdict(record))
    return business


async def continue_in_chat(max_user_id: int) -> None:
    """Компанию подключили в мини-приложении — бот продолжает в чате: вопрос о режиме или численности,
    а если профиль полный — список обязанностей. Иначе дашборд просит «ответить в чате», а там пусто."""
    from bot.message_handler import next_step  # логика онбординга живёт в боте; импорт не запускает polling
    try:
        await next_step(max_user_id)
    except Exception:  # MAX не даёт писать тем, кто не запускал бота
        logger.exception("could not continue onboarding in chat for %s", max_user_id)


@router.get("/session", response_model=Company, response_model_exclude_none=True)
@router.get("/company", response_model=Company, response_model_exclude_none=True)
async def current_company(
    business: Business = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    return await to_company(db, business)


@router.post("/session", response_model=Company, response_model_exclude_none=True)
async def connect_company(
    payload: ConnectRequest,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await load_from_registry(db, user, payload.inn)
    background.add_task(continue_in_chat, user.max_user_id)  # первым: фоновые задачи идут по очереди
    # выписка ЕГРЮЛ (КПП, адрес, директор — для документов) и выгрузки ЕРКНМ скачиваются медленно — в фоне
    background.add_task(scan_in_background, business.inn)
    return await to_company(db, business)


@router.post("/company/refresh", response_model=Company, response_model_exclude_none=True)
async def refresh_company(
    background: BackgroundTasks,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """«Обновить» в профиле и «Просканировать сейчас» на дашборде: реестр МСП сразу, ЕГРЮЛ и ЕРКНМ — в фоне,
    находки придут в чат."""
    business = await load_from_registry(db, user, business.inn)
    background.add_task(scan_in_background, business.inn)  # идёт прошлая проверка — новая не запустится
    return await to_company(db, business)
