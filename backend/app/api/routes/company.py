import logging
import re
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_business, get_current_user
from core.inn import is_valid_inn
from app.api.schemas import Benefit, Company, Option, ProfileForm, ProfileOptions, ProfileUpdate, Source
from databases import msp_registry
from databases import get_db
from databases.businesses_db import Business, CompanyTaken, save_business
from databases.users_db import User
from notifications.models import BusinessProfile, Notification
from notifications.worker import (answered, dispatch, load_profile, materialize_for, registry_loaded,
                                  scan_in_background)
from radar.deadlines import CATEGORY_RU, HEADCOUNT_RU, REGIME_RU, REGIONS, headcount_ru, region_name
from radar.laws import FLAGS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["company"])

OKVED = re.compile(r"\d{2}(?:\.\d{1,2}){0,2}")


class ConnectRequest(BaseModel):
    inn: str = Field(pattern=r"^(\d{10}|\d{12})$")

    @field_validator("inn")
    @classmethod
    def checksum(cls, inn: str) -> str:
        if not is_valid_inn(inn):
            raise ValueError("INN checksum is invalid")
        return inn


def registry_okved(business: Business) -> str:
    return f"{business.main_activity_code} — {business.main_activity_name}"


async def to_company(db: AsyncSession, business: Business) -> Company:
    full_name = re.sub(r'"([^"]*)"', r"«\1»", business.name)
    quoted = re.search(r"«[^»]*»", full_name)
    name = quoted.group(0) if quoted else full_name
    profile = await load_profile(db, business.inn)
    regime = REGIME_RU.get(profile.tax_regime)
    answers = await db.get(BusinessProfile, business.inn)
    source = msp_registry.source_note(await msp_registry.current_load())
    okved = (registry_okved(business) if profile.okved_main == business.main_activity_code
             else f"{profile.okved_main} — указан вами")
    return Company(
        name=name,
        full_name=full_name,
        initials="".join(word[0] for word in re.findall(r"\w+", name)[:2]).upper(),
        regime=regime or "Режим налогообложения не указан",
        inn=business.inn,
        kpp=answers.kpp if answers else None,
        ogrn=business.ogrn,
        okved=okved,
        category=CATEGORY_RU.get(business.category),
        headcount=headcount_ru(profile),
        region=region_name(profile.region_code),
        needs_answers=regime is None or profile.headcount is None,
        source=Source(name=source[:1].upper() + source[1:], demo=False, updated_at=business.updated_at.replace(microsecond=0)),
        benefits=[Benefit(title=b.title, basis=b.basis, url=b.url) for b in profile.headcount_benefits()],
    )


async def load_from_registry(db: AsyncSession, user: User, inn: str) -> Business:
    record = await msp_registry.find(inn)
    if record is None:
        detail = ("INN not found in the SME registry" if await msp_registry.is_complete()
                  else "INN not found in the SME registry slice loaded in this MVP")
        raise HTTPException(status_code=404, detail=detail)
    try:
        business = await save_business(db, user.id, record)
    except CompanyTaken as exc:
        raise HTTPException(status_code=409, detail="Company is already connected by another MAX user") from exc
    await registry_loaded(inn, asdict(record))
    return business


async def continue_in_chat(max_user_id: int, card: str | None = None) -> None:
    from bot.message_handler import next_step
    try:
        if card:
            await answered(max_user_id, card, release=False)
        if not await next_step(max_user_id):
            await dispatch()
    except Exception:
        logger.exception("could not continue onboarding in chat for %s", max_user_id)


@router.get("/session", response_model=Company, response_model_exclude_none=True,
            summary="Подключённая компания; 404 — компания ещё не подключена")
@router.get("/company", response_model=Company, response_model_exclude_none=True,
            summary="Карточка подключённой компании")
async def current_company(
    business: Business = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    return await to_company(db, business)


@router.post("/session", response_model=Company, response_model_exclude_none=True,
             summary="Подключить компанию по ИНН: профиль из реестра МСП, сроки обязанностей; "
                     "422 — неверный ИНН, 404 — нет в реестре МСП (в MVP — в загруженном срезе), "
                     "409 — ведёт другой пользователь")
async def connect_company(
    payload: ConnectRequest,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business = await load_from_registry(db, user, payload.inn)
    background.add_task(continue_in_chat, user.max_user_id)
    background.add_task(scan_in_background, business.inn)
    return await to_company(db, business)


@router.post("/company/refresh", response_model=Company, response_model_exclude_none=True,
             summary="Перепроверить компанию по загруженному реестру МСП; ЕРКНМ — в фоне")
async def refresh_company(
    background: BackgroundTasks,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await msp_registry.find(business.inn)
    if record is None:
        if await msp_registry.is_complete():
            await registry_loaded(business.inn, None)
    else:
        business = await save_business(db, user.id, record)
        await registry_loaded(business.inn, asdict(record))
    background.add_task(scan_in_background, business.inn)
    return await to_company(db, business)


@router.get("/company/profile", response_model=ProfileForm, response_model_exclude_none=True,
            summary="Экран «Данные компании»: профиль, данные реестра и варианты ответов")
async def profile_form(
    business: Business = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    profile = await load_profile(db, business.inn)
    answers = await db.get(BusinessProfile, business.inn)
    return ProfileForm(
        is_legal_entity=profile.is_legal_entity,
        regime=profile.tax_regime,
        headcount=str(answers.headcount) if answers and answers.headcount is not None else None,
        registry_headcount=business.employees_num,
        okved=profile.okved_main, registry_okved=registry_okved(business),
        region=(profile.region_code or "").zfill(2), registry_region=region_name(business.region_code) or business.region_code,
        has_licenses=profile.has_licenses,
        flags={flag: profile.flags.get(flag) for flag in FLAGS},
        patent_from=profile.patent_from, patent_to=profile.patent_to,
        kpp=answers.kpp if answers else None, address=answers.address if answers else None,
        director_position=answers.director_position if answers else None,
        director_name=answers.director_name if answers else None,
        options=ProfileOptions(
            regimes=[Option(value=code, label=label[:1].upper() + label[1:]) for code, label in REGIME_RU.items()
                     if not (profile.is_legal_entity and code == "psn")],
            headcounts=[Option(value=str(low), label=label[:1].upper() + label[1:]) for low, label in HEADCOUNT_RU.items()],
            regions=[Option(value=code, label=name) for code, name in sorted(REGIONS.items(), key=lambda item: item[1])],
            flags=[Option(value=code, label=flag.label) for code, flag in FLAGS.items()],
        ),
    )


def invalid(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


@router.put("/company/profile", response_model=Company, response_model_exclude_none=True,
            summary="Сохранить режим, численность и поправки к реестру; обязанности пересчитываются")
async def save_profile(
    payload: ProfileUpdate,
    background: BackgroundTasks,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    legal_entity = business.subject_type == "UL"
    if payload.regime is not None and (payload.regime not in REGIME_RU or (legal_entity and payload.regime == "psn")):
        raise invalid("Unknown tax regime")
    headcount = int(payload.headcount) if payload.headcount not in (None, "") else None
    if headcount is not None and headcount not in HEADCOUNT_RU:
        raise invalid("Unknown headcount range")
    okved, region = payload.okved.strip(), payload.region.zfill(2)
    if not OKVED.fullmatch(okved):
        raise invalid("OKVED must look like 56.10")
    if region not in REGIONS:
        raise invalid("Unknown region")
    if set(payload.flags) - set(FLAGS):
        raise invalid("Unknown flag")
    kpp = (payload.kpp or "").strip() or None
    if kpp is not None and not re.fullmatch(r"\d{9}", kpp):
        raise invalid("KPP must be 9 digits")
    patent = payload.regime == "psn" and payload.patent_from and payload.patent_to
    if patent and not payload.patent_from <= payload.patent_to <= payload.patent_from + timedelta(days=366):
        raise invalid("Patent term must be from 1 day to 12 months")

    before = await load_profile(db, business.inn)
    was_complete = before.tax_regime is not None and before.headcount is not None
    answers = await db.get(BusinessProfile, business.inn) or BusinessProfile(inn=business.inn, flags={}, bank_biks=[])
    answers.tax_regime = payload.regime
    answers.headcount = headcount
    answers.has_employees = headcount > 0 if headcount is not None else None
    answers.okved_main = okved if okved != business.main_activity_code else None
    answers.region_code = region if region != (business.region_code or "").zfill(2) else None
    answers.has_licenses = payload.has_licenses if payload.has_licenses != business.has_licenses else None
    answers.flags = {code: value for code, value in payload.flags.items() if value is not None}
    answers.patent_from, answers.patent_to = (payload.patent_from, payload.patent_to) if patent else (None, None)
    answers.kpp = kpp
    answers.address = (payload.address or "").strip() or None
    answers.director_position = (payload.director_position or "").strip()[:100] or None
    answers.director_name = (payload.director_name or "").strip()[:200] or None
    answers.answered_at = datetime.now(timezone.utc)
    db.add(answers)
    await db.commit()
    await materialize_for(business.inn)
    card = user.awaiting_mid if user.awaiting_mid and not await db.scalar(
        select(Notification.id).where(Notification.max_message_id == user.awaiting_mid).limit(1)) else None
    if card or not was_complete:
        background.add_task(continue_in_chat, user.max_user_id, card)
    return await to_company(db, business)
