"""Фоновые задачи радара. Планировщик запускается внутри процесса бота (bot/main_longpooling.py):
бот работает в одном экземпляре, поэтому задачи не задвоятся. Не запускайте его в uvicorn
с несколькими воркерами.

Расписание (Europe/Moscow):
  03:00 ежедневно      sync_egrul        выписка ЕГРЮЛ: недостоверность, дисквалификация, ликвидация, смена руководителя/адреса/участников
  04:00 11-го числа    sync_msp          реестр МСП публикуется 10-го: исключение, смена категории
  04:30 ежедневно      check_inspections ЕРКНМ: проверки и профвизиты по ИНН, предостережения
  05:00 ежедневно      materialize       сроки обязанностей на год вперёд по профилю компании
  07:00 ежедневно      ingest_laws       новые акты pravo.gov.ru → каким компаниям они касаются
  09:00 ежедневно      queue_reminders   напоминания по настройкам пользователя, после срока — каждый день
  каждую минуту        dispatch          outbox (notifications) → MAX
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import html
import json
import logging
import re
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from maxapi.exceptions.max import MaxApiError
from maxapi.types.input_media import InputMediaBuffer
from sqlalchemy import delete, distinct, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.client import bot, bot_app, send_html
from data_fetching import egrul_client, erknm_client, pravo_client, rmsp_client
from databases.businesses_db import Business, UserBusiness, current_business
from databases.engine_start import SessionLocal
from databases.users_db import User
from radar import detectors as det
from radar import documents, laws
from radar.catalog import CATALOG, Delivery, Severity
from radar.deadlines import Profile
from radar.obligations import BY_CODE, OBLIGATIONS, due_dates
from radar.render import build_context, company_ctx, flag_keyboard, keyboard, plural, render
from .models import BusinessProfile, LawRecord, Notification, RadarEvent, RegistrySnapshot
from .planner import MSK, REMIND_HOUR, NotificationSettings, reminder_label, today_msk

logger = logging.getLogger(__name__)

WINDOW_DAYS = 365  # сроки обязанностей — на год вперёд
LAW_LOOKBACK_DAYS = 10  # текст законов и постановлений появляется на портале через 1–7 дней после публикации
LAW_RECENT_DAYS = 30  # акты, которые досылаем после ответа «да» и по /demo_law; столько же загружаем при первом старте
PDF_LIMIT = 20 * 1024 * 1024  # PDF больше — только ссылкой


# ---- реестры ------------------------------------------------------------------
async def fetch_egrul(inn: str) -> dict | None:
    extract = await asyncio.to_thread(egrul_client.get_extract, inn)
    return asdict(extract) if extract is not None else None


async def fetch_msp(inn: str) -> dict | None:
    record = await asyncio.to_thread(rmsp_client.fetch_by_inn, inn)
    return asdict(record) if record is not None else None


async def save_snapshot(inn: str, source: str, data: dict | None) -> dict | None:
    """Кладёт снимок в registry_snapshots, если он изменился, и возвращает ПРЕДЫДУЩИЙ."""
    data_hash = hashlib.sha1(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    async with SessionLocal() as db:
        prev = (await db.execute(
            select(RegistrySnapshot)
            .where(RegistrySnapshot.inn == inn, RegistrySnapshot.source == source)
            .order_by(RegistrySnapshot.id.desc()).limit(1)
        )).scalar_one_or_none()
        if prev is None or prev.data_hash != data_hash:
            db.add(RegistrySnapshot(inn=inn, source=source, data=data, data_hash=data_hash))
            await db.commit()
        return prev.data if prev else None


async def upsert_events(inn: str, source: str, drafts: list[det.Draft]) -> list[RadarEvent]:
    """Записывает черновики; возвращает только реально новые. Уникальность key — индексы в models.py."""
    new = []
    async with SessionLocal() as db:
        for d in drafts:
            stmt = (insert(RadarEvent)
                    .values(inn=inn, type=d.type, kind=CATALOG[d.type].kind, key=d.key, source=source,
                            payload=d.payload, due=d.due)
                    .on_conflict_do_nothing()
                    .returning(RadarEvent))
            event = (await db.execute(stmt)).scalar_one_or_none()
            if event is not None:
                new.append(event)
        await db.commit()
    return new


async def open_condition_keys(inn: str, source: str) -> dict[str, str]:
    """{key: type} открытых состояний."""
    async with SessionLocal() as db:
        rows = await db.execute(
            select(RadarEvent.key, RadarEvent.type)
            .where(RadarEvent.inn == inn, RadarEvent.source == source, RadarEvent.kind == "condition",
                   RadarEvent.resolved_at.is_(None))
        )
        return dict(rows.all())


async def close_conditions(inn: str, keys: list[str]) -> list[RadarEvent]:
    """resolved_at=now; вернуть закрытые события."""
    if not keys:
        return []
    async with SessionLocal() as db:
        result = await db.execute(
            update(RadarEvent)
            .where(RadarEvent.inn == inn, RadarEvent.kind == "condition", RadarEvent.key.in_(keys),
                   RadarEvent.resolved_at.is_(None))
            .values(resolved_at=func.now(), status="done")
            .returning(RadarEvent)
        )
        closed = list(result.scalars())
        await db.commit()
        return closed


async def alert(events: list[RadarEvent]) -> None:
    """Срочные события — отдельным сообщением всем пользователям компании (уйдёт в ближайший dispatch)."""
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        for event in events:
            if CATALOG[event.type].delivery != Delivery.IMMEDIATE:
                continue
            for user_id in await db.scalars(select(UserBusiness.user_id).where(UserBusiness.inn == event.inn)):
                await _queue(db, user_id, event, "alert", now)
        await db.commit()


async def reopen_conditions(inn: str, source: str, drafts: list[det.Draft], today: date) -> list[RadarEvent]:
    """Состояние отметили «Сделано», а реестр его всё ещё показывает. Реестр обновляется не сразу,
    поэтому ждём обычный интервал повтора (repeat_days) от последнего сообщения, потом снова открываем
    и пишем (метка recheck:<день> — чтобы не совпасть с первым alert)."""
    keys = [d.key for d in drafts if CATALOG[d.type].kind == "condition"]
    if not keys:
        return []
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        done = await db.scalars(
            select(RadarEvent)
            .where(RadarEvent.inn == inn, RadarEvent.source == source, RadarEvent.kind == "condition",
                   RadarEvent.key.in_(keys), RadarEvent.resolved_at.is_(None), RadarEvent.status == "done")
        )
        reopened = [e for e in done
                    if (today - (e.last_notified_at or e.first_seen_at).astimezone(MSK).date()).days
                    >= (CATALOG[e.type].repeat_days or 0)]
        for event in reopened:
            event.status = "open"
            for user_id in await db.scalars(select(UserBusiness.user_id).where(UserBusiness.inn == inn)):
                await _queue(db, user_id, event, f"recheck:{today:%y%m%d}", now)
        await db.commit()
    return reopened


async def process_egrul(inn: str, today: date) -> None:
    cur = await fetch_egrul(inn)
    if cur is None:
        return
    prev = await save_snapshot(inn, "egrul", cur)
    drafts = det.egrul_conditions(inn, cur, today) + det.egrul_changes(inn, prev, cur, today)
    await reopen_conditions(inn, "egrul", drafts, today)
    new_events = await upsert_events(inn, "egrul", drafts)   # только реально новые
    gone = det.reconcile_conditions(await open_condition_keys(inn, "egrul"), drafts)
    closed = await close_conditions(inn, gone)
    new_events += await upsert_events(inn, "egrul", det.resolutions(closed, today))  # «отметка снята»
    await alert(new_events)


async def process_msp(inn: str, cur: dict | None, today: date) -> list[RadarEvent]:
    """Снимок реестра МСП → исключение, отсутствие в реестре, смена категории."""
    prev = await save_snapshot(inn, "msp", cur)
    drafts = det.msp_changes(inn, prev, cur, today)
    reopened = await reopen_conditions(inn, "msp", drafts, today)
    new_events = await upsert_events(inn, "msp", drafts)
    await close_conditions(inn, det.reconcile_conditions(await open_condition_keys(inn, "msp"), drafts))
    await alert(new_events)
    return new_events + reopened


async def process_inspections(inns: set[str], today: date) -> None:
    """ЕРКНМ: месячные выгрузки скачиваем один раз на все ИНН (4 архива по несколько МБ)."""
    knms: dict[str, list[dict]] = defaultdict(list)
    for year, month in erknm_client.months_around(today):
        try:
            for knm in await asyncio.to_thread(erknm_client.fetch_month, year, month, inns):
                knms[knm.inn].append(asdict(knm))
        except Exception:  # без одного месяца остальные всё равно проверим
            logger.exception("erknm %s-%s failed", year, month)
    for inn in inns:
        drafts, cancelled = det.inspection_events(inn, knms[inn], today)
        await alert(await upsert_events(inn, "erknm", drafts))
        if cancelled:  # отменённое мероприятие — не напоминаем и не показываем в задачах
            async with SessionLocal() as db:
                await db.execute(update(RadarEvent).where(RadarEvent.inn == inn, RadarEvent.key.in_(cancelled))
                                 .values(status="muted"))
                await db.commit()


async def check_inspections() -> None:
    inns = set(await active_inns())
    if inns:
        await process_inspections(inns, today_msk())


_scanning: set[str] = set()              # ИНН, по которым сейчас идёт фоновая проверка
_erknm_checked: dict[str, date] = {}     # ИНН → день, когда по нему уже качали ЕРКНМ


async def scan_in_background(inn: str) -> None:
    """ЕГРЮЛ и ЕРКНМ после подключения, «Обновить» и «Просканировать сейчас». По одному ИНН —
    одна проверка за раз: повторное нажатие, пока идёт прошлая, ничего не запускает. ЕРКНМ
    (4 архива, около двух минут) — не чаще раза в день: ночью её всё равно проверяет check_inspections."""
    if inn in _scanning:
        return
    _scanning.add(inn)
    today = today_msk()
    try:
        try:
            await process_egrul(inn, today)
        except Exception:  # капча ЕГРЮЛ не должна отменять проверку ЕРКНМ
            logger.exception("egrul scan failed for %s", inn)
        if _erknm_checked.get(inn) != today:
            await process_inspections({inn}, today)
            _erknm_checked[inn] = today
    except Exception:
        logger.exception("erknm scan failed for %s", inn)
    finally:
        _scanning.discard(inn)


async def active_inns() -> list[str]:
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(distinct(UserBusiness.inn)).join(User, User.id == UserBusiness.user_id).where(User.is_active)
        )
        return list(rows)


EGRUL_PAUSE = 60           # с, между выписками: капча появляется уже после 4–5 выписок подряд
EGRUL_CAPTCHA_PAUSE = 900  # с, после капчи


async def sync_egrul() -> None:
    """Ночью по всем компаниям, растянуто: минута между выписками (сотня компаний — меньше двух часов),
    после капчи — 15 минут и повтор той же компании один раз."""
    today = today_msk()
    for inn in await active_inns():
        for attempt in (1, 2):
            try:
                await process_egrul(inn, today)
            except egrul_client.CaptchaRequiredError:
                logger.warning("egrul captcha for %s, attempt %s", inn, attempt)
                await asyncio.sleep(EGRUL_CAPTCHA_PAUSE)
                continue
            except Exception:  # один сбой не должен ронять весь прогон
                logger.exception("egrul sync failed for %s", inn)
            break
        await asyncio.sleep(EGRUL_PAUSE)


async def sync_msp() -> None:
    today = today_msk()
    for inn in await active_inns():
        try:
            record = await asyncio.to_thread(rmsp_client.fetch_by_inn, inn)
            await process_msp(inn, asdict(record) if record else None, today)
            if record is not None:
                async with SessionLocal() as db:
                    business = await db.get(Business, inn)
                    for field, value in asdict(record).items():
                        setattr(business, field, value)
                    business.updated_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            logger.exception("msp sync failed for %s", inn)
        await asyncio.sleep(1)


# ---- обязанности ----------------------------------------------------------------
async def load_profile(db: AsyncSession, inn: str) -> Profile | None:
    """Профиль для правил, бота и мини-приложения. Поправки пользователя (численность, ОКВЭД, регион,
    лицензии — экран «Данные компании») важнее реестра МСП, который отстаёт; нет ни того, ни другого —
    бот спросит."""
    business = await db.get(Business, inn)
    if business is None:
        return None
    answers = await db.get(BusinessProfile, inn) or BusinessProfile(inn=inn, flags={})
    answered = answers.headcount
    headcount = answered if answered is not None else business.employees_num
    return Profile(
        inn=inn, is_legal_entity=business.subject_type == "UL",
        region_code=answers.region_code or business.region_code,
        okved_main=answers.okved_main or business.main_activity_code, msp_category=business.category,
        tax_regime=answers.tax_regime,
        has_employees=headcount > 0 if headcount is not None else None,
        headcount=headcount, headcount_exact=answered is None and headcount is not None,
        has_licenses=business.has_licenses if answers.has_licenses is None else answers.has_licenses,
        flags=dict(answers.flags or {}), patent_from=answers.patent_from, patent_to=answers.patent_to,
    )


async def materialize_for(inn: str, today: date | None = None) -> tuple[list[str], list[str]]:
    """Сроки обязанностей компании на год вперёд → radar_events (type=deadline).

    Повторный запуск обновляет тексты и сроки. Будущие открытые сроки обязанностей, которые
    перестали касаться компании (сменился режим или численность), удаляются.
    Возвращает (названия новых обязанностей, названия исчезнувших).
    """
    today = today or today_msk()
    code = RadarEvent.payload["code"].astext
    ours = (RadarEvent.inn == inn, RadarEvent.key.like(f"obl:{inn}:%"))
    async with SessionLocal() as db:
        profile = await load_profile(db, inn)
        if profile is None:
            return [], []
        before = set(await db.scalars(
            select(distinct(code)).where(*ours, RadarEvent.due >= today, RadarEvent.status != "muted")
        ))
        applicable = {}
        for obligation in OBLIGATIONS:
            why = obligation.applies(profile)
            if why is None:
                continue
            applicable[obligation.code] = obligation
            for due, nominal, period in due_dates(obligation, profile, today, today + timedelta(days=WINDOW_DAYS)):
                # shifted/original — для строки «срок перенесён с …» в шаблоне deadline.group
                payload = obligation.payload(why, period) | {"shifted": due != nominal, "original": nominal.isoformat()}
                stmt = insert(RadarEvent).values(
                    inn=inn, type="deadline", kind="once", key=f"obl:{inn}:{obligation.code}:{nominal}",
                    source="profile", payload=payload, due=due,
                )
                await db.execute(stmt.on_conflict_do_update(
                    index_elements=[RadarEvent.key], index_where=text("kind = 'once'"),
                    set_={"payload": stmt.excluded.payload, "due": stmt.excluded.due, "last_seen_at": func.now()},
                ))
        gone = select(RadarEvent.id).where(*ours, RadarEvent.due >= today, RadarEvent.status == "open",
                                           code.not_in(list(applicable)))
        await db.execute(delete(Notification).where(Notification.event_id.in_(gone)))
        await db.execute(delete(RadarEvent).where(RadarEvent.id.in_(gone)))
        await db.commit()
    added = [o.title for c, o in applicable.items() if c not in before]
    removed = [BY_CODE[c].title for c in before - applicable.keys() if c in BY_CODE]
    return added, removed


async def registry_loaded(inn: str, msp_record: dict) -> None:
    """После ввода ИНН или «Обновить» (бот и мини-приложение): снимок МСП — точка отсчёта для
    sync_msp (и сразу проверка изменений), затем сроки обязанностей."""
    await process_msp(inn, msp_record, today_msk())
    await materialize_for(inn)


async def materialize() -> None:
    for inn in await active_inns():
        try:
            await materialize_for(inn)
        except Exception:
            logger.exception("materialize failed for %s", inn)


# ---- новые законы (pravo.gov.ru, radar/laws.py) ---------------------------------
async def classify_act(meta: dict) -> laws.Law | None:
    """Акт с портала → Law. Сначала по названию; не про бизнес — дальше не смотрим. Иначе берём
    текст из «Актуальных редакций» (дата вступления в силу, изменяемые акты), а если из названия
    не понять, что меняется, — ещё и ищем изменяемый акт по номеру. None — ждём текст до завтра."""
    law = laws.classify(meta, [], None)
    if law is not None and not law.topics:
        return law
    resolved = []
    if law is None:
        for block, number, signed in laws.act_refs(laws.split_meta(meta)[1]):
            found = await asyncio.to_thread(pravo_client.find_act, block, number, signed)
            if found:
                resolved.append(laws.split_meta(found)[1])
    text = await asyncio.to_thread(pravo_client.text, meta["eoNumber"])
    return laws.classify(meta, resolved, text) if text or resolved else law


async def ingest_laws(today: date | None = None, days: int = LAW_LOOKBACK_DAYS, notify: bool = True) -> int:
    """Акты за последние days дней → таблица laws → события компаниям, которых они касаются.
    Уже разобранные пропускаем; «О внесении изменений…» без текста перепроверяем на следующий день.
    Возвращает число новых актов про бизнес."""
    today = today or today_msk()
    since = today - timedelta(days=days)
    async with SessionLocal() as db:
        known = set(await db.scalars(select(LawRecord.eo_number).where(LawRecord.published >= since)))
    fresh: list[laws.Law] = []
    for offset in range(days + 1):
        day = since + timedelta(days=offset)
        try:
            metas = await asyncio.to_thread(pravo_client.published, day)
        except Exception:  # портал не ответил — этот день перепроверим завтра
            logger.exception("pravo.gov.ru list for %s failed", day)
            continue
        for meta in metas:
            if meta["eoNumber"] in known:
                continue
            try:
                law = await classify_act(meta)
            except Exception:
                logger.exception("pravo.gov.ru act %s failed", meta["eoNumber"])
                continue
            if law is None:
                continue
            known.add(law.eo_number)
            async with SessionLocal() as db:
                await db.execute(insert(LawRecord).values(
                    eo_number=law.eo_number, header=law.header[:500], name=law.name, published=law.published,
                    topics=law.topics, region=law.region, amended=law.amended,
                    effective=[d.isoformat() for d in law.effective], pages=law.pages, pdf_size=law.pdf_size,
                ).on_conflict_do_nothing())
                await db.commit()
            if law.topics:
                fresh.append(law)
    logger.info("pravo.gov.ru: %s new acts about business since %s", len(fresh), since)
    if fresh and notify:
        await fan_out_laws(await active_inns(), fresh, today)
    return len(fresh)


async def laws_report(days: int = 7) -> str:
    """/laws (при DEBUG): что лента отобрала за неделю и по какой теме — чтобы проверить глазами."""
    since = today_msk() - timedelta(days=days)
    async with SessionLocal() as db:
        total = await db.scalar(select(func.count()).select_from(LawRecord).where(LawRecord.published >= since))
        rows = list(await db.scalars(select(LawRecord).where(LawRecord.published >= since, LawRecord.topics != [])
                                     .order_by(LawRecord.published.desc())))
    if not total:
        return "За неделю актов с pravo.gov.ru ещё нет: загрузка идёт после запуска бота и каждый день в 07:00."
    lines = [f"📚 <b>Законы за {days} дней</b>", f"Разобрано актов: {total}, про бизнес: {len(rows)}.", ""]
    for law in rows[:20]:
        topics = ", ".join(laws.TOPIC_RU.get(t, t) for t in law.topics) + (f"; регион {law.region}" if law.region else "")
        lines.append(f"• {law.published:%d.%m} — {html.escape(law.name[:140])} <i>({topics})</i>")
    if len(rows) > 20:
        lines.append(f"…и ещё {len(rows) - 20}.")
    lines += ["", "Акт явно не про бизнес или не той темы — пришлите его название разработчику: "
                  "поправим словарь в radar/laws.py."]
    return "\n".join(lines)


async def recent_laws(today: date) -> list[laws.Law]:
    async with SessionLocal() as db:
        rows = await db.scalars(select(LawRecord).where(
            LawRecord.published >= today - timedelta(days=LAW_RECENT_DAYS), LawRecord.topics != []))
        return [laws.Law(r.eo_number, r.header, r.name, r.published, r.topics, r.region, r.amended,
                         [date.fromisoformat(d) for d in r.effective], r.pages, r.pdf_size) for r in rows]


async def fan_out_laws(inns: list[str], items: list[laws.Law], today: date) -> list[RadarEvent]:
    """Акты × компании → «вышел акт» или вопрос о признаке; новые — сразу в очередь (alert)."""
    created = []
    for inn in inns:
        async with SessionLocal() as db:
            profile = await load_profile(db, inn)
        if profile is None:
            continue
        new = await upsert_events(inn, "pravo", [d for law in items for d in laws.drafts(law, profile, today)])
        await alert(new)
        created += new
    return created


async def start_laws() -> None:
    """При старте бота. Пустая таблица — загрузить акты за LAW_RECENT_DAYS дней без рассылки
    (иначе после первого деплоя всем пришёл бы месяц законов разом); иначе — догнать 07:00."""
    async with SessionLocal() as db:
        empty = (await db.execute(select(LawRecord.eo_number).limit(1))).first() is None
    if empty:
        await ingest_laws(days=LAW_RECENT_DAYS, notify=False)
    else:
        await ingest_laws()


async def answer_flag(max_user_id: int, flag: str, yes: bool) -> str:
    """Ответ на вопрос о признаке (касса, маркировка…): запоминаем его для компании и, если «да»,
    присылаем акты за LAW_RECENT_DAYS дней, которые ждали этого ответа."""
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.max_user_id == max_user_id))).scalar_one_or_none()
        business = await current_business(db, user.id) if user else None
        if business is None or flag not in laws.FLAGS:
            return "Сначала пришлите ИНН"
        profile = await db.get(BusinessProfile, business.inn) or BusinessProfile(inn=business.inn, flags={}, bank_biks=[])
        profile.flags = {**(profile.flags or {}), flag: yes}  # новый dict — иначе JSONB не сохранится
        db.add(profile)
        await db.execute(update(RadarEvent).where(RadarEvent.inn == business.inn, RadarEvent.key == f"q:{business.inn}:{flag}")
                         .values(status="done"))
        await db.commit()
        inn = business.inn
    if not yes:
        return "Запомнили: такие акты присылать не будем"
    today = today_msk()
    sent = await fan_out_laws([inn], await recent_laws(today), today)
    await dispatch()
    return "Запомнили — присылаем, что вышло" if sent else "Запомнили — пришлём, когда выйдет"


@functools.lru_cache(maxsize=4)  # один акт обычно уходит нескольким пользователям подряд
def _law_pdf(eo_number: str) -> bytes:
    return pravo_client.pdf(eo_number)


async def send_law_pdf(max_user_id: int, payload: dict) -> None:
    """Официальный текст акта — файлом вслед за сообщением. Большой скан — только ссылкой «Источник»."""
    if (payload.get("pdf_size") or 0) > PDF_LIMIT:
        return
    content = await asyncio.to_thread(_law_pdf, payload["eo"])
    filename = re.sub(r"[^\w.\- ]+", "", payload["act"].replace("№", "N")).strip() + ".pdf"
    await bot.send_message(user_id=max_user_id, text=f"📄 Официальный текст: {payload['act']}",
                           attachments=[InputMediaBuffer(content, filename=filename)])


# ---- напоминания ----------------------------------------------------------------
def template_of(event: RadarEvent) -> str:
    return "deadline.group" if event.type == "deadline" else event.type


async def _queue(db: AsyncSession, user_id: int, event: RadarEvent, label: str, at: datetime) -> None:
    await db.execute(
        insert(Notification)
        .values(user_id=user_id, event_id=event.id, template=template_of(event), label=label,
                dedup_key=f"{event.id}:{user_id}:{label}", scheduled_at=at)
        .on_conflict_do_nothing(index_elements=[Notification.dedup_key])
    )


async def queue_reminders(now: datetime | None = None) -> None:
    """Раз в день: для каждого открытого срока и каждого пользователя компании — напоминание,
    если сегодня день из его настройки remind или срок уже прошёл."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(MSK).date()
    async with SessionLocal() as db:
        rows = await db.execute(
            select(RadarEvent, User)
            .join(UserBusiness, UserBusiness.inn == RadarEvent.inn)
            .join(User, User.id == UserBusiness.user_id)
            .where(RadarEvent.due.is_not(None), RadarEvent.status == "open", User.is_active,
                   # о новом событии реестра сегодня уже ушёл alert — напоминания начинаются с завтра
                   or_(RadarEvent.type == "deadline", RadarEvent.first_seen_at < datetime.combine(today, time(), MSK)))
        )
        for event, user in rows.all():
            label = reminder_label(event.due, today, NotificationSettings.of(user.notification_settings))
            if label:
                await _queue(db, user.id, event, label, now)
        # состояния без срока (исключение из МСП, ликвидация, дисквалификация) — раз в repeat_days, пока открыты
        rows = await db.execute(
            select(RadarEvent, User)
            .join(UserBusiness, UserBusiness.inn == RadarEvent.inn)
            .join(User, User.id == UserBusiness.user_id)
            .where(RadarEvent.kind == "condition", RadarEvent.due.is_(None), RadarEvent.status == "open",
                   RadarEvent.resolved_at.is_(None), User.is_active)
        )
        for event, user in rows.all():
            every = CATALOG[event.type].repeat_days
            last = (event.last_notified_at or event.first_seen_at).astimezone(MSK).date()
            if every and (today - last).days >= every:
                await _queue(db, user.id, event, f"repeat:{today:%y%m%d}", now)
        await db.commit()


AWAIT_HOURS = 24  # сутки без ответа — присылаем следующее: иначе важное навсегда застрянет за неотвеченным

_dispatching = asyncio.Lock()  # dispatch зовут планировщик, кнопки и демо-команды — не отправлять дважды


async def dispatch() -> None:
    """Outbox → MAX, по одному сообщению на пользователя: следующее — после ответа на предыдущее
    (кнопка под ним, см. answered) или через AWAIT_HOURS. Сроки одной компании на одну дату — одним
    сообщением (шаблон deadline.group); из нескольких напоминаний об одной задаче — только новое."""
    async with _dispatching:
        await _dispatch(datetime.now(timezone.utc))


async def _dispatch(now: datetime) -> None:
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(Notification, User, RadarEvent)
            .join(User, User.id == Notification.user_id)
            .outerjoin(RadarEvent, RadarEvent.id == Notification.event_id)
            .where(Notification.status == "pending", Notification.scheduled_at <= now)
            .order_by(Notification.id)
        )).all()
        newest = {(n.user_id, e.id): n.id for n, _, e in rows if e is not None}
        queues: dict[int, dict[tuple, list]] = defaultdict(dict)  # пользователь → группы по порядку
        for notification, user, event in rows:
            settings = NotificationSettings.of(user.notification_settings)
            stale = event is not None and (event.status != "open" or newest[(user.id, event.id)] != notification.id)
            if stale or not settings.chat:
                notification.status = "cancelled"  # задача закрыта, есть напоминание новее или чат выключен
            elif notification.label.startswith("demo") or not settings.is_quiet(now):
                key = ((event.inn, event.due) if notification.template == "deadline.group"
                       else (notification.id,))
                queues[user.id].setdefault(key, []).append((notification, user, event))
        await db.commit()
        for groups in queues.values():
            user = next(iter(groups.values()))[0][1]
            if user.awaiting_mid and user.awaiting_since and now - user.awaiting_since < timedelta(hours=AWAIT_HOURS):
                continue  # ждём ответа на прошлое сообщение
            # сначала критичное (🔴), дальше — по очереди
            ordered = sorted(groups.values(), key=lambda items: (not _critical(items[0][2]), items[0][0].id))
            await _send(db, ordered[0], now, waiting=len(ordered) - 1)
            await db.commit()


def _critical(event: RadarEvent | None) -> bool:
    return event is not None and event.type in CATALOG and CATALOG[event.type].severity == Severity.CRITICAL


async def _send(db: AsyncSession, items: list[tuple[Notification, User, RadarEvent | None]], now: datetime,
                waiting: int = 0) -> None:
    first, user, event = items[0]
    try:
        if event is None:  # готовый текст: карточка тура /demo
            text, kb = first.text, first.keyboard
        else:
            text, kb = await _render(db, items, now)
        if waiting:
            text += (f"\n\n<i>Ещё {waiting} {plural(waiting, 'сообщение', 'сообщения', 'сообщений')} — пришлю "
                     "по одному, когда ответите на это.</i>")
        message_id = await send_html(user.max_user_id, text, kb)
    except Exception as exc:
        logger.exception("dispatch failed for user %s", user.id)
        unreachable = isinstance(exc, MaxApiError) and exc.code in (403, 404)
        for notification, _, _ in items:
            notification.attempts += 1
            notification.error = str(exc)[:500]
            notification.status = "failed" if notification.attempts >= 3 or unreachable else "pending"
        if unreachable:  # заблокировал бота или удалил чат: не пишем, пока сам не вернётся (/start, мини-приложение)
            user.is_active = False
            await db.execute(update(Notification).where(Notification.user_id == user.id, Notification.status == "pending")
                             .values(status="cancelled"))
        return
    for notification, _, e in items:
        notification.status, notification.sent_at, notification.max_message_id = "sent", now, message_id
        if e is not None:
            e.last_notified_at = now
    user.awaiting_mid, user.awaiting_since = message_id, now
    # PDF — с первым сообщением об акте; в напоминаниях о вступлении в силу его уже не повторяем
    if event is not None and event.type == "law.upcoming" and (first.label == "alert" or first.label.startswith("demo")):
        try:
            await send_law_pdf(user.max_user_id, event.payload)
        except Exception:
            logger.exception("law pdf %s failed for user %s", event.payload.get("eo"), user.id)


async def _render(db: AsyncSession, items: list[tuple[Notification, User, RadarEvent]],
                  now: datetime) -> tuple[str, dict]:
    first, _, event = items[0]
    events = list({e.id: e for _, _, e in items}.values())
    today = now.astimezone(MSK).date()
    business = await db.get(Business, event.inn)
    company = company_ctx(None, {"name": business.name, "ogrn": business.ogrn}, event.inn)
    if first.template == "deadline.group":
        payloads = [{"shifted": False, "period": "", "basis": "", "why": "", **e.payload} for e in events]
        ctx = build_context("deadline", {}, company, today, items=payloads, due=event.due)
    else:
        ctx = build_context(event.type, event.payload, company, today, src=event.source)
    text = render("push." + first.template, ctx)  # коротко; подробности — на экране события в приложении
    if event.type == "profile.question":
        return text, flag_keyboard(event.payload["flag"])
    return text, keyboard([e.id for e in events], app=await bot_app())


async def queue_text(user_id: int, text: str, kb: dict, label: str) -> None:
    """Сообщение без события — в общую очередь, за уже стоящими (карточка шага /demo идёт после его сообщений)."""
    async with SessionLocal() as db:
        db.add(Notification(user_id=user_id, template="text", label=label, text=text, keyboard=kb,
                            dedup_key=f"text:{user_id}:{label}", scheduled_at=datetime.now(timezone.utc)))
        await db.commit()
    await dispatch()


async def hold(max_user_id: int, message_id: str | None) -> None:
    """Бот сам (не из очереди) задал вопрос с кнопками — очередь ждёт ответа на него."""
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.max_user_id == max_user_id)
                         .values(awaiting_mid=message_id, awaiting_since=datetime.now(timezone.utc)))
        await db.commit()


async def answered(max_user_id: int, message_id: str | None, release: bool = True) -> None:
    """Нажата кнопка под сообщением: убрать его из чата и, если его ждала очередь, прислать следующее.
    release=False — бот сразу задаст следующий вопрос сам (онбординг, шаг /demo)."""
    if message_id:
        try:
            await bot.delete_message(message_id)
        except Exception:  # удалить не вышло (старое или уже удалено) — очередь всё равно освобождаем
            logger.warning("could not delete message %s", message_id, exc_info=True)
        async with SessionLocal() as db:
            await db.execute(update(User).where(User.max_user_id == max_user_id, User.awaiting_mid == message_id)
                             .values(awaiting_mid=None, awaiting_since=None))
            await db.commit()
    if release:
        await dispatch()


# ---- кнопки и документы (вызывает бот и API) -------------------------------------
async def user_events(db: AsyncSession, max_user_id: int, ids: list[int]) -> tuple[User | None, list[RadarEvent]]:
    """События, к компаниям которых у пользователя есть доступ."""
    user = (await db.execute(select(User).where(User.max_user_id == max_user_id))).scalar_one_or_none()
    if user is None:
        return None, []
    events = await db.scalars(
        select(RadarEvent).join(UserBusiness, UserBusiness.inn == RadarEvent.inn)
        .where(UserBusiness.user_id == user.id, RadarEvent.id.in_(ids))
    )
    return user, list(events)


async def apply_action(max_user_id: int, ids: list[int], action: str) -> str:
    """Кнопки под пушем: list | done | mute (и snooze1d у старых сообщений с «Завтра»). Возвращает
    текст всплывающего ответа."""
    async with SessionLocal() as db:
        user, events = await user_events(db, max_user_id, ids)
        if not events:
            return "Задача не найдена"
        if action == "snooze1d":
            tomorrow = datetime.now(MSK).date() + timedelta(days=1)
            at = datetime.combine(tomorrow, time(REMIND_HOUR), MSK)
            for event in events:
                await _queue(db, user.id, event, f"snooze:{tomorrow:%y%m%d}", at)
            answer = "Напомним завтра в 9:00"
        elif action == "list":
            for event in events:
                event.in_list = True
            answer = "Добавили в список дел — он в мини-приложении"
        else:
            for event in events:
                event.status = "done" if action == "done" else "muted"
            if action != "done":
                answer = "Больше не напомним"
            elif all(event.kind == "condition" for event in events):
                # состояние закрывает только реестр: при следующей сверке проверим, что записи нет
                answer = "Проверим по реестру: если запись останется, напомним"
            else:
                answer = "Отмечено как выполненное"
        await db.commit()
    return answer


async def handled_in_app(max_user_id: int, event_id: int) -> None:
    """Задачу закрыли или взяли в список дел в мини-приложении — убрать пуш о ней из чата и прислать
    следующее. Пуш о нескольких сроках одной даты остаётся, пока открыт хоть один из них."""
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.max_user_id == max_user_id))).scalar_one_or_none()
        if user is None:
            return
        mids = set(await db.scalars(select(Notification.max_message_id).where(
            Notification.user_id == user.id, Notification.event_id == event_id, Notification.status == "sent",
            Notification.max_message_id.is_not(None))))
        shown = []
        for mid in mids:
            others = await db.scalar(
                select(func.count()).select_from(Notification).join(RadarEvent, RadarEvent.id == Notification.event_id)
                .where(Notification.max_message_id == mid, RadarEvent.id != event_id, RadarEvent.status == "open",
                       RadarEvent.in_list.is_(False)))
            if not others:
                shown.append(mid)
    for mid in shown:
        await answered(max_user_id, mid, release=False)
    await dispatch()


async def send_document(db: AsyncSession, event: RadarEvent, max_user_id: int) -> None:
    """Черновик документа к сроку — файлом в чат с ботом."""
    filename, content = documents.build(event.payload, event.due, await documents.requisites(db, event.inn))
    await bot.send_message(
        user_id=max_user_id,
        text=documents.caption(event.payload),
        attachments=[InputMediaBuffer(content, filename=filename)],
    )


# ---- демо-триггеры (/demo_remind, /demo_event в боте, только при DEBUG) ----------------
# Открытого API ЕРКНМ по ИНН нет — на защите проверку показываем имитацией
DEMO_INSPECTION = {
    "classification": "КНМ", "type_name": "Плановое КНМ", "authority": "Роспотребнадзор",
    "kind": "выездную проверку", "control": "Федеральный государственный санитарно-эпидемиологический контроль (надзор)",
    "title": "Плановая проверка Роспотребнадзора", "period": "Имитация записи ЕРКНМ",
    "why": "проверка внесена в единый реестр контрольных мероприятий по вашему ИНН",
    "what": "Изучите проверочные листы по вашему виду контроля и подготовьте документы до начала проверки.",
    "basis": "закон № 248-ФЗ «О государственном контроле»",
}

async def demo_remind(max_user_id: int) -> int:
    """Три ближайших открытых срока текущей компании — напоминанием прямо сейчас."""
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.max_user_id == max_user_id))).scalar_one_or_none()
        business = await current_business(db, user.id) if user else None
        if business is None:
            return 0
        events = list(await db.scalars(
            select(RadarEvent).where(RadarEvent.inn == business.inn, RadarEvent.due.is_not(None),
                                     RadarEvent.status == "open")
            .order_by(RadarEvent.due).limit(3)
        ))
        for event in events:
            await _queue(db, user.id, event, f"demo:{now:%H%M%S}", now)
        await db.commit()
    await dispatch()
    return len(events)


async def demo_event(max_user_id: int, kind: str) -> str:
    """Имитация внешнего события: knm — проверка в ЕРКНМ, msp_excluded — исключение из реестра МСП."""
    today = today_msk()
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.max_user_id == max_user_id))).scalar_one_or_none()
        business = await current_business(db, user.id) if user else None
    if business is None:
        return "Сначала подключите компанию: пришлите ИНН."
    inn = business.inn
    if kind == "knm":
        start = today + timedelta(days=30)
        key = f"demo:knm:{inn}:{datetime.now():%y%m%d%H%M%S}"
        new = await upsert_events(inn, "demo", [det.Draft("inspection.planned", key, DEMO_INSPECTION | {"start": start.isoformat()}, start)])
        await alert(new)
    elif kind == "msp_excluded":
        async with SessionLocal() as db:
            prev = (await db.execute(
                select(RegistrySnapshot.data).where(RegistrySnapshot.inn == inn, RegistrySnapshot.source == "msp")
                .order_by(RegistrySnapshot.id.desc()).limit(1)
            )).scalar_one_or_none()
        new = await process_msp(inn, (prev or {}) | {"category": business.category,
                                                    "date_excluded": f"{today:%d.%m.%Y}"}, today)
    else:
        return "Доступно: /demo_event knm, /demo_event msp_excluded"
    if not new:
        return ("Такое событие уже открыто. Оно закроется само, когда реестр перестанет его показывать: "
                "«Просканировать сейчас» в мини-приложении. «Сделано» не закрывает его, а откладывает до сверки.")
    await dispatch()
    return "Готово: событие создано, сообщение отправлено."


async def demo_law(max_user_id: int) -> str:
    """Акты за LAW_RECENT_DAYS дней, которые касаются текущей компании, — сразу в чат. Настоящие
    данные портала, не имитация; уже присланный акт второй раз не придёт (ключ law:<номер>:<ИНН>)."""
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.max_user_id == max_user_id))).scalar_one_or_none()
        business = await current_business(db, user.id) if user else None
    if business is None:
        return "Сначала подключите компанию: пришлите ИНН."
    today = today_msk()
    items = await recent_laws(today)
    if not items:
        return "Акты с pravo.gov.ru ещё загружаются после запуска бота — попробуйте через несколько минут."
    new = await fan_out_laws([business.inn], items, today)
    if not new:
        return (f"За {LAW_RECENT_DAYS} дней на pravo.gov.ru {len(items)} актов про бизнес, "
                "новых для вашей компании среди них нет: не касаются или уже присланы.")
    await dispatch()
    return f"Готово: отправили {len(new)} (акты и вопросы) из {len(items)} актов про бизнес за {LAW_RECENT_DAYS} дней."


def build_scheduler() -> AsyncIOScheduler:
    s = AsyncIOScheduler(timezone=MSK)
    s.add_job(sync_egrul, CronTrigger(hour=3, minute=0, jitter=600), id="egrul", max_instances=1)
    s.add_job(sync_msp, CronTrigger(day=11, hour=4), id="msp", max_instances=1)
    s.add_job(materialize, CronTrigger(hour=5), id="deadlines", max_instances=1)
    s.add_job(queue_reminders, CronTrigger(hour=REMIND_HOUR), id="reminders", max_instances=1)
    s.add_job(dispatch, IntervalTrigger(minutes=1), id="dispatch", max_instances=1, coalesce=True)
    s.add_job(ingest_laws, CronTrigger(hour=7), id="laws", max_instances=1)
    s.add_job(check_inspections, CronTrigger(hour=4, minute=30), id="knm", max_instances=1)
    return s
