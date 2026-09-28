from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_business, get_current_user
from app.api.schemas import Counters, DashboardData, Link, Task, TaskDetails, TaskSection
from databases import get_db
from databases.businesses_db import Business
from databases.users_db import User
from notifications.models import Notification, RadarEvent
from notifications.worker import send_document
from radar.catalog import CATALOG
from radar.render import cap1, plural

router = APIRouter(tags=["tasks"])


def company_events(inn: str) -> Select:
    """Задачи — события радара со сроком; отмеченные «Не актуально» (muted) не показываем."""
    return (
        select(RadarEvent)
        .where(RadarEvent.inn == inn, RadarEvent.due.is_not(None), RadarEvent.status != "muted")
        .order_by(RadarEvent.due, RadarEvent.id)
    )


def task_status(event: RadarEvent, today: date) -> str:
    if event.status == "done":
        return "done"
    days_left = (event.due - today).days
    if days_left < 0:
        return "overdue"
    # «скоро» — срок ближе первого напоминания из каталога радара (для сроков — 3 дня)
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
    )


def to_sections(payload: dict) -> list[TaskSection]:
    """Разделы экрана задачи из payload события радара. Обязанности (radar/obligations.py) дают
    what, how, where, format, basis, penalty, why; новые законы (radar/laws.drafts) —
    summary, actions, reasons, act, basis_url. id разделов — как в макете: why и risks фронт раскрывает сразу."""
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


def heading(title: str, period: str | None) -> str:
    """«Декларация по УСН» + «За 2025 год» → «Декларация по УСН за 2025 год»."""
    if not period:
        return title
    return f"{title} з{period[1:]}" if period.startswith("За ") else f"{title}. {period}"


async def find_event(db: AsyncSession, business: Business, task_id: int) -> RadarEvent:
    result = await db.execute(company_events(business.inn).where(RadarEvent.id == task_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return event


@router.get("/dashboard", response_model=DashboardData, response_model_exclude_none=True)
async def dashboard(
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    tasks = [to_task(event, today) for event in (await db.execute(company_events(business.inn))).scalars()]
    open_tasks = [task for task in tasks if task.status != "done"]
    week_end = today + timedelta(days=7)
    # точка на колокольчике: бот что-то прислал в чат после последнего открытия экрана «Уведомления»
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
        # группировку «Сегодня» / «На неделе» делает фронт
        tasks=open_tasks,
        next_due=next((task.due for task in open_tasks if task.due > week_end), None),
        unread=unread,
    )


@router.get("/calendar", response_model=list[Task])
async def calendar(
    from_: date = Query(alias="from"),
    to: date = Query(),
    business: Business = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    query = company_events(business.inn).where(RadarEvent.due.between(from_, to))
    return [to_task(event, today) for event in (await db.execute(query)).scalars()]


@router.get("/tasks/{task_id}", response_model=TaskDetails, response_model_exclude_none=True)
async def task_details(
    task_id: int,
    business: Business = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    event = await find_event(db, business, task_id)
    task = to_task(event, today)
    # следующий открытый срок — карточка на экране выполненной задачи
    result = await db.execute(
        company_events(business.inn)
        .where(RadarEvent.id != event.id, RadarEvent.due >= event.due, RadarEvent.status != "done")
        .limit(1)
    )
    next_event = result.scalar_one_or_none()
    return TaskDetails(
        **task.model_dump(),
        heading=heading(task.title, event.payload.get("period")),
        sections=to_sections(event.payload),
        document=bool(event.payload.get("document")),
        next=to_task(next_event, today) if next_event else None,
    )


@router.post("/tasks/{task_id}/submitted", status_code=204)
async def mark_submitted(
    task_id: int,
    business: Business = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    event = await find_event(db, business, task_id)
    event.status = "done"
    await db.commit()


@router.delete("/tasks/{task_id}/submitted", status_code=204)
async def undo_submitted(
    task_id: int,
    business: Business = Depends(get_current_business),
    db: AsyncSession = Depends(get_db),
):
    event = await find_event(db, business, task_id)
    event.status = "open"
    await db.commit()


@router.post("/tasks/{task_id}/document", status_code=204)
async def prepare_document(
    task_id: int,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Черновик документа к сроку — бот присылает его файлом в чат."""
    event = await find_event(db, business, task_id)
    if not event.payload.get("document"):
        raise HTTPException(status_code=404, detail="No document for this task")
    try:
        await send_document(db, event, user.max_user_id)
    except Exception as exc:  # MAX не принял сообщение: пользователь не запускал бота, сбой сети
        raise HTTPException(status_code=502, detail="Could not send the document to MAX chat") from exc
