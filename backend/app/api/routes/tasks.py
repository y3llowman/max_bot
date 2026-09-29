import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_business, get_current_user
from app.api.schemas import Counters, DashboardData, FeedItem, Link, Task, TaskDetails, TaskSection
from databases import get_db
from databases.businesses_db import Business
from databases.users_db import User
from notifications.models import Notification, RadarEvent
from notifications.planner import today_msk
from notifications.worker import handled_in_app, send_document
from radar.catalog import CATALOG
from radar.obligations import BY_CODE
from radar.render import SOURCE_URLS, build_context, cap1, company_ctx, plural, render

router = APIRouter(tags=["tasks"])


def company_tasks(inn: str) -> Select:
    return (
        select(RadarEvent)
        .where(RadarEvent.inn == inn, or_(RadarEvent.due.is_not(None), RadarEvent.in_list), RadarEvent.status != "muted")
        .order_by(RadarEvent.due.nulls_last(), RadarEvent.id)
    )


def task_status(event: RadarEvent, today: date) -> str:
    if event.status == "done":
        return "done"
    if event.due is None:
        return "planned"
    days_left = (event.due - today).days
    if days_left < 0:
        return "overdue"
    event_type = CATALOG.get(event.type)
    first_reminder = max(event_type.remind_before, default=0) if event_type else 0
    return "soon" if days_left <= first_reminder else "planned"


def to_task(event: RadarEvent, today: date) -> Task:
    event_type = CATALOG.get(event.type)
    type_title = event_type.title if event_type else event.type
    return Task(
        id=str(event.id),
        title=event.payload.get("title") or type_title,
        subtitle=event.payload.get("period") or type_title,
        status=task_status(event, today),
        due=event.due,
        periodicity=event.payload.get("periodicity"),
        listed=event.in_list,
    )


def to_sections(payload: dict) -> list[TaskSection]:
    def lines(*keys: str) -> list[str] | None:
        value = next((payload[key] for key in keys if payload.get(key)), None)
        if value is None:
            return None
        return [cap1(line) for line in (value if isinstance(value, list) else [value])]

    def link(label: str, url_key: str) -> Link | None:
        return Link(label=label, url=payload[url_key]) if payload.get(url_key) else None

    how = payload.get("how")
    steps = how or lines("actions", "what")
    sections = [
        TaskSection(id="summary", icon="info", title="Что меняется", caption="Суть изменения",
                    body=lines("summary")),
        TaskSection(id="why", icon="user", title="Почему вам", caption="По данным реестров и профиля",
                    body=lines("reasons", "why")),
        TaskSection(id="steps", icon="tasks", title="Что сделать",
                    caption=f"{len(steps)} {plural(len(steps), 'шаг', 'шага', 'шагов')}" if how else "Рекомендация бота",
                    body=lines("what") if how else None, steps=steps),
        TaskSection(id="how", icon="file", title="Куда сдавать", caption="Орган и формат",
                    body=[payload[key] for key in ("where", "format") if payload.get(key)] or None,
                    link=link("Открыть сайт", "where_url")),
        TaskSection(id="law", icon="scale", title="Правовое обоснование", caption="Норма и источник",
                    body=lines("act", "basis"), link=link("Открыть текст закона", "basis_url")),
        TaskSection(id="risks", icon="alert-triangle", title="Риски при задержке", caption="Штраф и последствия",
                    body=lines("penalty")),
    ]
    return [section for section in sections if section.body or section.steps]


TEMPLATE_SECTIONS = {
    "Что произошло": ("why", "info", "Факт из реестра"),
    "Что вышло": ("why", "info", "Акт и даты"),
    "Что это значит": ("risks", "alert-triangle", "Последствия"),
    "Чем грозит": ("risks", "alert-triangle", "Последствия"),
    "Почему вам": ("reason", "user", "По данным профиля"),
    "Что сделать": ("steps", "tasks", "Рекомендация бота"),
    "Ваши права": ("law", "scale", "Закон № 248-ФЗ"),
}


def template_sections(event: RadarEvent, company: dict, today: date) -> list[TaskSection]:
    text = render(event.type, build_context(event.type, event.payload, company, today, src=event.source))
    sections: list[TaskSection] = []
    title, body = "Что произошло", []

    def flush() -> None:
        if body:
            section_id, icon, caption = TEMPLATE_SECTIONS.get(title, (f"s{len(sections)}", "info", ""))
            sections.append(TaskSection(id=section_id, icon=icon, title=title, caption=caption, body=list(body)))

    for line in text.splitlines()[2:]:
        heading = re.fullmatch(r"<b>(.+)</b>", line.strip())
        if heading:
            flush()
            title, body = heading.group(1), []
        elif plain := re.sub(r"<[^>]+>", "", line).strip():
            body.append(plain)
    flush()
    if sections and event.source in SOURCE_URLS:
        sections[0].link = Link(label="Открыть источник", url=SOURCE_URLS[event.source])
    return sections


def heading(title: str, period: str | None) -> str:
    if not period:
        return title
    return f"{title} з{period[1:]}" if period.startswith("За ") else f"{title}. {period}"


async def find_event(db: AsyncSession, business: Business, task_id: int) -> RadarEvent:
    event = await db.scalar(select(RadarEvent).where(RadarEvent.inn == business.inn, RadarEvent.id == task_id))
    if event is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return event


@router.get("/dashboard", response_model=DashboardData, response_model_exclude_none=True)
async def dashboard(
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = today_msk()
    tasks = [to_task(event, today) for event in (await db.execute(company_tasks(business.inn))).scalars()]
    open_tasks = [task for task in tasks if task.status != "done"]
    week_end = today + timedelta(days=7)
    sent = select(Notification.id).where(Notification.user_id == user.id, Notification.status == "sent")
    if user.notifications_seen_at is not None:
        sent = sent.where(Notification.sent_at > user.notifications_seen_at)
    unread = (await db.execute(sent.limit(1))).first() is not None
    return DashboardData(
        counters=Counters(
            overdue=sum(task.status == "overdue" for task in tasks),
            soon=sum(task.status == "soon" for task in tasks),
            done=sum(task.status == "done" for task in tasks),
        ),
        tasks=open_tasks,
        next_due=next((task.due for task in open_tasks if task.due and task.due > week_end), None),
        unread=unread,
    )


@router.get("/calendar", response_model=list[Task])
async def calendar(
    from_: date = Query(alias="from"),
    to: date = Query(),
    business: Business = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    today = today_msk()
    query = company_tasks(business.inn).where(RadarEvent.due.between(from_, to))
    return [to_task(event, today) for event in (await db.execute(query)).scalars()]


@router.get("/feed", response_model=list[FeedItem], response_model_exclude_none=True)
async def feed(
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=90)
    last_sent = func.max(Notification.sent_at)
    rows = await db.execute(
        select(RadarEvent, last_sent)
        .join(Notification, Notification.event_id == RadarEvent.id)
        .where(Notification.user_id == user.id, Notification.status == "sent", Notification.sent_at >= since,
               RadarEvent.inn == business.inn)
        .group_by(RadarEvent.id).order_by(last_sent.desc()).limit(100)
    )
    today = today_msk()
    items = []
    for event, sent_at in rows.all():
        task = to_task(event, today)
        severity = CATALOG[event.type].severity.value if event.type in CATALOG else "info"
        items.append(FeedItem(id=task.id, title=task.title, subtitle=task.subtitle, sent_at=sent_at, due=event.due,
                              status=event.status if event.status in ("done", "muted") else "open",
                              listed=event.in_list, severity=severity))
    return items


@router.get("/tasks/{task_id}", response_model=TaskDetails, response_model_exclude_none=True)
async def task_details(
    task_id: int,
    business: Business = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    today = today_msk()
    event = await find_event(db, business, task_id)
    task = to_task(event, today)
    if event.type == "law.upcoming" or event.payload.get("code") in BY_CODE:
        sections = to_sections(event.payload)
    else:
        company = company_ctx(None, {"name": business.name, "ogrn": business.ogrn}, business.inn)
        sections = template_sections(event, company, today)
    next_event = None
    if event.due is not None:
        next_event = await db.scalar(
            company_tasks(business.inn)
            .where(RadarEvent.id != event.id, RadarEvent.due >= event.due, RadarEvent.status != "done")
            .limit(1)
        )
    return TaskDetails(
        **task.model_dump(),
        heading=heading(task.title, event.payload.get("period")),
        sections=sections,
        document=bool(event.payload.get("document")),
        next=to_task(next_event, today) if next_event else None,
    )


@router.post("/tasks/{task_id}/submitted", status_code=204)
async def mark_submitted(
    task_id: int,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = await find_event(db, business, task_id)
    event.status = "done"
    await db.commit()
    await handled_in_app(user.max_user_id, event.id)


@router.delete("/tasks/{task_id}/submitted", status_code=204)
async def undo_submitted(
    task_id: int,
    business: Business = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    event = await find_event(db, business, task_id)
    event.status = "open"
    await db.commit()


@router.post("/tasks/{task_id}/list", status_code=204)
async def add_to_list(
    task_id: int,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = await find_event(db, business, task_id)
    event.in_list = True
    await db.commit()
    await handled_in_app(user.max_user_id, event.id)


@router.post("/tasks/{task_id}/document", status_code=204)
async def prepare_document(
    task_id: int,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = await find_event(db, business, task_id)
    if not event.payload.get("document"):
        raise HTTPException(status_code=404, detail="No document for this task")
    try:
        await send_document(db, event, user.max_user_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not send the document to MAX chat") from exc
