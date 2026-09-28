"""Фоновые задачи радара. Планировщик запускается внутри процесса бота (bot/main_longpooling.py):
бот работает в одном экземпляре, поэтому задачи не задвоятся. Не запускайте его в uvicorn
с несколькими воркерами.

Расписание (Europe/Moscow):
  03:00 ежедневно      sync_egrul        выписка ЕГРЮЛ: недостоверность, дисквалификация, ликвидация, смена руководителя/адреса/участников
  04:00 11-го числа    sync_msp          реестр МСП публикуется 10-го: исключение, смена категории
  04:30 ежедневно      check_inspections ЕРКНМ: проверки и профвизиты по ИНН, предостережения
  05:00 ежедневно      materialize       сроки обязанностей на год вперёд по профилю компании
  09:00 ежедневно      queue_reminders   напоминания по настройкам пользователя, после срока — каждый день
  каждую минуту        dispatch          outbox (notifications) → MAX
Заглушки, не реализованы: weekly_digest, check_banks, ingest_laws, fan_out_feed, check_certs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from maxapi.types.input_media import InputMediaBuffer
from sqlalchemy import delete, distinct, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.client import bot, bot_app, send_html
from data_fetching import egrul_client, erknm_client, rmsp_client
from databases.businesses_db import Business, UserBusiness, current_business
from databases.engine_start import SessionLocal
from databases.users_db import User
from radar import detectors as det
from radar import documents
from radar.catalog import CATALOG, Delivery
from radar.deadlines import Profile
from radar.obligations import BY_CODE, OBLIGATIONS, due_dates
from radar.render import SOURCE_URLS, build_context, company_ctx, keyboard, render
from .models import BusinessProfile, Notification, RadarEvent, RegistrySnapshot
from .planner import MSK, REMIND_HOUR, NotificationSettings, reminder_label

logger = logging.getLogger(__name__)

WINDOW_DAYS = 365  # сроки обязанностей — на год вперёд


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


async def process_egrul(inn: str, today: date) -> None:
    cur = await fetch_egrul(inn)
    if cur is None:
        return
    prev = await save_snapshot(inn, "egrul", cur)
    drafts = det.egrul_conditions(inn, cur, today) + det.egrul_changes(inn, prev, cur, today)
    new_events = await upsert_events(inn, "egrul", drafts)   # только реально новые
    gone = det.reconcile_conditions(await open_condition_keys(inn, "egrul"), drafts)
    closed = await close_conditions(inn, gone)
    new_events += await upsert_events(inn, "egrul", det.resolutions(closed, today))  # «отметка снята»
    await alert(new_events)


async def process_msp(inn: str, cur: dict | None, today: date) -> list[RadarEvent]:
    """Снимок реестра МСП → исключение, отсутствие в реестре, смена категории."""
    prev = await save_snapshot(inn, "msp", cur)
    drafts = det.msp_changes(inn, prev, cur, today)
    new_events = await upsert_events(inn, "msp", drafts)
    await close_conditions(inn, det.reconcile_conditions(await open_condition_keys(inn, "msp"), drafts))
    await alert(new_events)
    return new_events


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
        await process_inspections(inns, date.today())


async def active_inns() -> list[str]:
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(distinct(UserBusiness.inn)).join(User, User.id == UserBusiness.user_id).where(User.is_active)
        )
        return list(rows)


async def sync_egrul() -> None:
    today = date.today()
    for inn in await active_inns():
        try:
            await process_egrul(inn, today)
        except Exception:  # один сбой не должен ронять весь прогон
            logger.exception("egrul sync failed for %s", inn)
        await asyncio.sleep(2)  # бережём источник: ~30 запросов в минуту


async def sync_msp() -> None:
    today = date.today()
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
    """Профиль для правил, бота и мини-приложения. Численность: ответ пользователя (он мог поправить
    её в /profile) важнее среднесписочной из реестра МСП; нет ни того, ни другого — бот спросит."""
    business = await db.get(Business, inn)
    if business is None:
        return None
    answers = await db.get(BusinessProfile, inn)
    answered = answers.headcount if answers else None
    headcount = answered if answered is not None else business.employees_num
    return Profile(
        inn=inn, is_legal_entity=business.subject_type == "UL", region_code=business.region_code,
        okved_main=business.main_activity_code, msp_category=business.category,
        tax_regime=answers.tax_regime if answers else None,
        has_employees=headcount > 0 if headcount is not None else None,
        headcount=headcount, headcount_exact=answered is None and headcount is not None,
    )


async def materialize_for(inn: str, today: date | None = None) -> tuple[list[str], list[str]]:
    """Сроки обязанностей компании на год вперёд → radar_events (type=deadline).

    Повторный запуск обновляет тексты и сроки. Будущие открытые сроки обязанностей, которые
    перестали касаться компании (сменился режим или численность), удаляются.
    Возвращает (названия новых обязанностей, названия исчезнувших).
    """
    today = today or date.today()
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
    await process_msp(inn, msp_record, date.today())
    await materialize_for(inn)


async def materialize() -> None:
    for inn in await active_inns():
        try:
            await materialize_for(inn)
        except Exception:
            logger.exception("materialize failed for %s", inn)


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
        await db.commit()


_dispatching = asyncio.Lock()  # dispatch зовут планировщик и демо-команды — не отправлять дважды


async def dispatch() -> None:
    """Outbox → MAX. Сроки одной компании на одну дату — одним сообщением (шаблон deadline.group)."""
    async with _dispatching:
        await _dispatch(datetime.now(timezone.utc))


async def _dispatch(now: datetime) -> None:
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(Notification, User, RadarEvent)
            .join(User, User.id == Notification.user_id)
            .join(RadarEvent, RadarEvent.id == Notification.event_id)
            .where(Notification.status == "pending", Notification.scheduled_at <= now)
            .order_by(RadarEvent.due, Notification.id)
        )).all()
        groups: dict[tuple, list] = defaultdict(list)
        for notification, user, event in rows:
            settings = NotificationSettings.of(user.notification_settings)
            if event.status != "open" or not settings.chat:
                notification.status = "cancelled"
            elif notification.label.startswith("demo") or not settings.is_quiet(now):
                key = ((user.id, event.inn, event.due) if notification.template == "deadline.group"
                       else (user.id, notification.id))
                groups[key].append((notification, user, event))
        await db.commit()
        for items in groups.values():
            await _send(db, items, now)
            await db.commit()


async def _send(db: AsyncSession, items: list[tuple[Notification, User, RadarEvent]], now: datetime) -> None:
    first, user, event = items[0]
    events = list({e.id: e for _, _, e in items}.values())
    today = now.astimezone(MSK).date()
    business = await db.get(Business, event.inn)
    company = company_ctx(None, {"name": business.name, "ogrn": business.ogrn}, event.inn)
    if first.template == "deadline.group":
        payloads = [{"shifted": False, "period": "", "basis": "", "why": "", **e.payload} for e in events]
        ctx = build_context("deadline", {}, company, today, items=payloads, due=event.due)
    else:
        ctx = build_context(event.type, event.payload, company, today, src=event.source)
    docs = ([SimpleNamespace(button="Подготовить документ", code=event.payload["document"])]
            if len(events) == 1 and event.payload.get("document") else None)
    try:
        kb = keyboard([e.id for e in events], SOURCE_URLS.get(event.source), docs, app=await bot_app())
        message_id = await send_html(user.max_user_id, render(first.template, ctx), kb)
    except Exception as exc:
        logger.exception("dispatch failed for user %s", user.id)
        for notification, _, _ in items:
            notification.attempts += 1
            notification.error = str(exc)[:500]
            notification.status = "failed" if notification.attempts >= 3 else "pending"
        return
    for notification, _, e in items:
        notification.status, notification.sent_at, notification.max_message_id = "sent", now, message_id
        e.last_notified_at = now


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
    """Кнопки под напоминанием: done | snooze1d | mute. Возвращает текст всплывающего ответа."""
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
        else:
            for event in events:
                event.status = "done" if action == "done" else "muted"
            answer = "Отмечено как выполненное" if action == "done" else "Больше не напомним"
        await db.commit()
    return answer


async def send_document(db: AsyncSession, event: RadarEvent, max_user_id: int) -> None:
    """Черновик документа к сроку — файлом в чат с ботом."""
    filename, content = documents.build(event.payload, event.due, await documents.requisites(db, event.inn))
    title = documents.TITLES[event.payload["document"]]
    await bot.send_message(
        user_id=max_user_id,
        text=f"📄 {title} — черновик к задаче «{event.payload['title']}» ({event.payload['period']}). "
             "Проверьте реквизиты, впишите суммы и отправьте.",
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
    today = date.today()
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
        return "Такое событие уже открыто — сначала закройте его кнопкой под сообщением."
    await dispatch()
    return "Готово: событие создано, сообщение отправлено."


# ---- заглушки -------------------------------------------------------------------
async def weekly_digest() -> None: ...
async def check_banks() -> None: ...        # det.bank_conditions
async def ingest_laws() -> None: ...        # law_ingest.run_daily
async def fan_out_feed(feed_id: int) -> None: ...  # вызывается из callback feed:<id>:approve
async def check_certs() -> None: ...        # det.cert_events


def build_scheduler() -> AsyncIOScheduler:
    s = AsyncIOScheduler(timezone=MSK)
    s.add_job(sync_egrul, CronTrigger(hour=3, minute=0, jitter=600), id="egrul", max_instances=1)
    s.add_job(sync_msp, CronTrigger(day=11, hour=4), id="msp", max_instances=1)
    s.add_job(materialize, CronTrigger(hour=5), id="deadlines", max_instances=1)
    s.add_job(queue_reminders, CronTrigger(hour=REMIND_HOUR), id="reminders", max_instances=1)
    s.add_job(dispatch, IntervalTrigger(minutes=1), id="dispatch", max_instances=1, coalesce=True)
    s.add_job(weekly_digest, CronTrigger(day_of_week="mon", hour=8, minute=55), id="digest")
    s.add_job(check_banks, CronTrigger(hour=6), id="banks", max_instances=1)
    s.add_job(ingest_laws, CronTrigger(hour=7), id="laws", max_instances=1)
    s.add_job(check_inspections, CronTrigger(hour=4, minute=30), id="knm", max_instances=1)
    s.add_job(check_certs, CronTrigger(day_of_week="mon", hour=5, minute=30), id="fsa")
    return s
