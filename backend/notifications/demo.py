"""Демо-тур /demo: все функции бота по шагам на текущей компании (только при DEBUG=true).

Шаг — настоящие сообщения радара, после них карточка «Шаг N из M»: что показали, что проверить и
кнопка «Дальше». Всё идёт через общую очередь (worker.dispatch): по одному сообщению, следующее — после
ответа на предыдущее, отвеченное удаляется. Сроки обязанностей, документы и законы pravo.gov.ru — настоящие. События реестров —
имитация: черновики строят те же детекторы (radar/detectors.py), что и ночные сверки, но из подставных
выписок и без записи в registry_snapshots — иначе следующая сверка приняла бы подставу за изменение
в реестре. У имитаций source="demo" и ключ demo:…, последний шаг удаляет их.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select

from bot.client import bot_app, send_html
from databases.businesses_db import Business, current_business
from databases.engine_start import SessionLocal
from databases.users_db import User
from radar import detectors as det
from radar import laws
from radar.detectors import Draft
from . import worker
from .models import Notification, RadarEvent
from .planner import today_msk


@dataclass
class Ctx:
    max_user_id: int
    user: User
    business: Business
    today: date
    stamp: str                                  # уникальная часть ключей и меток этого шага
    show_profile: Callable[[], Awaitable[None]]  # карточка «Нашли вашу компанию. Всё верно?» (из бота)

    @property
    def inn(self) -> str:
        return self.business.inn


async def _send(ctx: Ctx, events: list[RadarEvent]) -> int:
    """События — сразу этому пользователю, в обход тихих часов (метка demo:…, как у /demo_remind)."""
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        for event in events:
            await worker._queue(db, ctx.user.id, event, f"demo:{ctx.stamp}", now)
        await db.commit()
    await worker.dispatch()
    return len(events)


async def _imitate(ctx: Ctx, drafts: list[Draft]) -> None:
    drafts = [replace(d, key=f"demo:{ctx.stamp}:{d.key}") for d in drafts]
    await _send(ctx, await worker.upsert_events(ctx.inn, "demo", drafts))


def _d(d: date) -> str:
    return f"{d:%d.%m.%Y}"


# ---------------------------------------------------------------- шаги
async def profile(ctx: Ctx) -> str | None:
    await ctx.show_profile()
    return None


async def reminders(ctx: Ctx) -> str | None:
    if not await worker.demo_remind(ctx.max_user_id):
        return "Открытых сроков нет: ответьте на вопросы профиля (/start) и повторите шаг."
    return None


async def documents(ctx: Ctx) -> str | None:
    """Ближайший срок с документом — напоминанием; документ готовят из приложения («Открыть»). Остальные
    виды документов не шлём пачкой файлов: они есть у задач в мини-приложении (перечислены в карточке)."""
    async with SessionLocal() as db:
        events = await db.scalars(
            select(RadarEvent).where(RadarEvent.inn == ctx.inn, RadarEvent.type == "deadline",
                                     RadarEvent.status == "open", RadarEvent.due >= ctx.today)
            .order_by(RadarEvent.due)
        )
        by_kind: dict[str, RadarEvent] = {}
        for event in events:
            if event.payload.get("document"):
                by_kind.setdefault(event.payload["document"], event)
    if not by_kind:
        return "У открытых сроков нет документов: ответьте на вопросы профиля (/start)."
    await _send(ctx, [next(iter(by_kind.values()))])
    return None


async def inspections(ctx: Ctx) -> str | None:
    """ЕРКНМ: плановая проверка, профилактический визит и предостережение."""
    base = {"inn": ctx.inn, "type_name": None, "warning": None, "stop": None}
    start, visit = ctx.today + timedelta(days=20), ctx.today + timedelta(days=10)
    knms = [
        base | {"erpid": "1", "classification": "КНМ", "status": "Ожидает проведения",
                "status_key": "TYPE_WAITING_CARRY_OUT", "kind": "Выездная проверка", "type_name": "Плановое КНМ",
                "control": "Федеральный государственный санитарно-эпидемиологический контроль (надзор)",
                "authority": "Управление Роспотребнадзора", "start": start.isoformat(),
                "stop": (start + timedelta(days=2)).isoformat()},
        base | {"erpid": "2", "classification": "ПМ", "status": "Ожидает проведения",
                "status_key": "TYPE_WAITING_CARRY_OUT", "kind": "Профилактический визит",
                "control": "Федеральный государственный пожарный надзор", "authority": "ГУ МЧС России",
                "start": visit.isoformat()},
        base | {"erpid": "3", "classification": "ПМ", "status": "Предостережение объявлено", "status_key": "REMARK",
                "kind": None, "control": "Федеральный государственный пожарный надзор", "authority": "ГУ МЧС России",
                "start": (ctx.today - timedelta(days=3)).isoformat(),
                "warning": "Не обеспечено содержание путей эвакуации в соответствии с требованиями пожарной безопасности."},
    ]
    drafts, _ = det.inspection_events(ctx.inn, knms, ctx.today)
    await _imitate(ctx, drafts)
    return None


async def unreliable(ctx: Ctx) -> str | None:
    mark = ctx.today - timedelta(days=40)
    extract = {"notes": [{"section": "Место нахождения и адрес юридического лица", "date": _d(mark),
                          "text": "Сведения недостоверны (результаты проверки достоверности содержащихся "
                                  "в ЕГРЮЛ сведений о юридическом лице)"}]}
    [mark_draft] = det.egrul_conditions(ctx.inn, extract, ctx.today)
    resolved = Draft("egrul.unreliable_resolved", "unreliable_resolved", mark_draft.payload)
    await _imitate(ctx, [mark_draft, resolved])
    return None


async def disqualification(ctx: Ctx) -> str | None:
    extract = {"director": {"surname": "ПЕТРОВА", "name": "АННА", "patronymic": "СЕРГЕЕВНА"},
               "director_disqualification_start": _d(ctx.today - timedelta(days=30)),
               "director_disqualification_end": _d(ctx.today + timedelta(days=335)),
               "director_disqualification_court_date": _d(ctx.today - timedelta(days=45))}
    [disqualified] = det.egrul_conditions(ctx.inn, extract, ctx.today)
    ended = Draft("egrul.disqualification_ended", "disqualification_ended",
                  disqualified.payload | {"end": _d(ctx.today - timedelta(days=1))})
    await _imitate(ctx, [disqualified, ended])
    return None


async def termination(ctx: Ctx) -> str | None:
    extract = {"status": "Регистрирующим органом принято решение о предстоящем исключении недействующего "
                         "юридического лица из ЕГРЮЛ", "status_date": _d(ctx.today - timedelta(days=10))}
    await _imitate(ctx, det.egrul_conditions(ctx.inn, extract, ctx.today))
    return None


async def egrul_changes(ctx: Ctx) -> str | None:
    """Новый руководитель-иностранец и новый адрес: два «изменились сведения» и уведомление МВД."""
    prev = {"director": {"surname": "ПЕТРОВА", "name": "АННА", "patronymic": "СЕРГЕЕВНА",
                         "citizenship": "Российская Федерация"},
            "address": "115035, г. Москва, ул. Садовническая, д. 1", "tax_authority_name": "ИФНС России № 5 по г. Москве"}
    cur = prev | {"director": {"surname": "НАЗАРОВ", "name": "АЛИШЕР", "patronymic": "ФАРХОДОВИЧ",
                               "citizenship": "Республика Узбекистан"},
                  "address": "123112, г. Москва, Пресненская наб., д. 12"}
    await _imitate(ctx, det.egrul_changes(ctx.inn, prev, cur, ctx.today))
    return None


async def msp(ctx: Ctx) -> str | None:
    """Реестр МСП: исключение, выход из микропредприятий (задача на ЛНА) и пропажа из реестра."""
    drafts = det.msp_changes(ctx.inn, None, {"category": 1, "date_excluded": _d(ctx.today)}, ctx.today)
    drafts += det.msp_changes(ctx.inn, {"category": 1}, {"category": 2}, ctx.today)
    drafts += det.msp_changes(ctx.inn, None, None, ctx.today)
    await _imitate(ctx, drafts)
    return None


async def repeat(ctx: Ctx) -> str | None:
    """Открытое состояние повторяется раз в repeat_days — показываем повтор исключения из МСП сейчас."""
    async with SessionLocal() as db:
        excluded = (await db.execute(
            select(RadarEvent).where(RadarEvent.inn == ctx.inn, RadarEvent.source == "demo",
                                     RadarEvent.type == "msp.excluded", RadarEvent.status == "open")
            .order_by(RadarEvent.id.desc()).limit(1)
        )).scalar_one_or_none()
    if excluded is None:
        return "Исключение из МСП уже закрыто — пройдите шаг «Реестр МСП» ещё раз (/demo)."
    await _send(ctx, [excluded])
    return None


async def pravo(ctx: Ctx) -> str | None:
    """Настоящие акты pravo.gov.ru за 30 дней для компании, плюс вопрос-признак по первому акту на
    тему, которой нет в реестрах (спрашиваем, даже если ответ уже есть: «Да» досылает акты)."""
    items = await worker.recent_laws(ctx.today)
    if not items:
        return "Акты pravo.gov.ru ещё загружаются после запуска бота — повторите шаг через несколько минут."
    async with SessionLocal() as db:
        company = await worker.load_profile(db, ctx.inn)
    new = await worker.upsert_events(ctx.inn, "pravo", [d for law in items for d in laws.drafts(law, company, ctx.today)])
    note = None
    if not any(e.type == "law.upcoming" for e in new):  # всё уже присылали — покажем последний акт ещё раз
        async with SessionLocal() as db:
            last = (await db.execute(
                select(RadarEvent).where(RadarEvent.inn == ctx.inn, RadarEvent.type == "law.upcoming")
                .order_by(RadarEvent.id.desc()).limit(1)
            )).scalar_one_or_none()
        if last is not None:
            new.append(last)
        else:
            note = f"За 30 дней на pravo.gov.ru {len(items)} актов про бизнес, но ни один не касается этой компании."
    flagged = next(((law, laws.BY_TOPIC[t].flag) for law in items for t in law.topics if laws.BY_TOPIC[t].flag), None)
    if flagged and not any(e.type == "profile.question" for e in new):
        law, flag = flagged
        new += await worker.upsert_events(ctx.inn, "demo", [Draft(
            "profile.question", f"demo:{ctx.stamp}:q:{flag}",
            {"flag": flag, "question": laws.FLAGS[flag].question, "act": law.header, "because": law.name})])
    await _send(ctx, new)
    return note


async def cleanup(inn: str) -> int:
    """Удалить имитации (source="demo") вместе с их сообщениями в очереди."""
    async with SessionLocal() as db:
        ids = select(RadarEvent.id).where(RadarEvent.inn == inn, RadarEvent.source == "demo")
        await db.execute(delete(Notification).where(Notification.event_id.in_(ids)))
        removed = await db.execute(delete(RadarEvent).where(RadarEvent.inn == inn, RadarEvent.source == "demo"))
        await db.commit()
    return removed.rowcount


# ---------------------------------------------------------------- тур
@dataclass(frozen=True)
class Step:
    title: str
    run: Callable[[Ctx], Awaitable[str | None]] | None  # None — шаг-инструкция без сообщений бота
    check: str                                          # что проверить


OPEN = "«Открыть» — подробности в приложении: что это значит, что сделать, источник. "
BUTTONS = ("Кнопки под пушем: «📋 В список дел» — сообщение уходит, задача остаётся в приложении; «✅ Сделано»; "
           "«🔕 Не актуально»; «Открыть» — подробности в приложении.")

STEPS = (
    Step("Регистрация", profile,
         "Карточка «Нашли вашу компанию»: всё из реестра МСП — ОКВЭД, категория, численность, регион, лицензии, "
         "контакты, режим — и «Всё верно?». «Да» — короткий итог в чате, «Исправить в приложении» — экран "
         "«Данные компании» (поправить можно и позже, из профиля)."),
    Step("Напоминания о сроках", reminders,
         "Пуши короткие и по одному: следующее — после ответа, отвеченное исчезает из чата, внизу — «Ещё N "
         "сообщений». Сроки одной даты — одним пушем. " + BUTTONS),
    Step("Документы к задачам", documents,
         "Нажмите «Открыть» под напоминанием → «Подготовить документ»: файл придёт в чат. Документы есть у "
         "всех обязанностей — уведомление КНД 1110355, реквизиты платёжки на ЕНП, памятка к отчёту, приказ о квоте."),
    Step("Проверки из ЕРКНМ", inspections,
         "Плановая проверка (задача со сроком — дата начала), профилактический визит и предостережение. " + OPEN
         + "Источник помечен «Имитация для демо»."),
    Step("ЕГРЮЛ: недостоверность", unreliable,
         "Отметка о недостоверности с датой, когда компанию могут исключить, и сообщение о её снятии. " + OPEN),
    Step("ЕГРЮЛ: дисквалификация руководителя", disqualification,
         "Дисквалификация до даты и сообщение о её окончании. " + OPEN),
    Step("ЕГРЮЛ: предстоящее исключение", termination,
         "«Компания в процессе прекращения» и срок возражения (задача). " + OPEN),
    Step("ЕГРЮЛ: изменились сведения", egrul_changes,
         "Сменились руководитель и адрес, руководитель-иностранец — задача «Уведомить МВД». «Было / стало» и "
         "предупреждение о захвате компании — в приложении («Открыть»)."),
    Step("Реестр МСП", msp,
         "Исключение из реестра, выход из микропредприятий (задача на ЛНА) и «компании нет в реестре». Событие без "
         "срока «📋 В список дел» кладёт в раздел «Без срока» на главной."),
    Step("Повтор и «Сделано» у состояния", repeat,
         "Исключение из МСП пришло ещё раз — так бот повторяет открытое состояние раз в 30 дней. «✅ Сделано» → "
         "«Проверим по реестру: если запись останется, напомним»."),
    Step("Новые законы (pravo.gov.ru)", pravo,
         "Настоящие акты за 30 дней: «Вышел акт, который вас касается» и «почему вам», следом PDF; в приложении — "
         "что меняется, что сделать, текст закона. Вопрос «Да / Нет»: «Да» → акты по теме."),
    Step("Сообщения и команды", None,
         "Пришлите любой текст или фото — бот ответит подсказкой. /profile — всё о компании и «✏️ Изменить "
         "данные». Другой ИНН в чате — смена компании; ИНН, который подключил другой пользователь, не подключится."),
    Step("Мини-приложение", None,
         "Главная: «Сегодня», «На неделе», «Без срока» (всё, что вы взяли «В список дел»). Колокольчик — лента: "
         "всё, о чём писал бот, даже удалённое из чата. Экран события — подробности, «Выполнено» (пуш в чате "
         "исчезнет), «Подготовить документ». Профиль → «Данные компании»: режим, численность, ОКВЭД, регион, "
         "признаки, срок патента; «Сохранить» ведёт на главную."),
)


def _kb(rows: list[list[dict]]) -> dict:
    return {"type": "inline_keyboard", "payload": {"buttons": rows}}


def _callback(text: str, payload: str) -> dict:
    return {"type": "callback", "text": text, "payload": payload}


async def context(max_user_id: int, show_profile: Callable[[], Awaitable[None]]) -> Ctx | None:
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.max_user_id == max_user_id))).scalar_one_or_none()
        business = await current_business(db, user.id) if user else None
    if business is None:
        return None
    # метка demo:<stamp> — в notifications.label (16 символов): время до сотых долей миллисекунды,
    # чтобы повтор того же события на следующем шаге не совпал с прошлой меткой
    return Ctx(max_user_id, user, business, today_msk(), f"{datetime.now():%H%M%S%f}"[:11], show_profile)


async def intro(max_user_id: int) -> str | None:
    """Ответ на /demo: список шагов и «Начать». Возвращает id сообщения — очередь ждёт ответа на него."""
    steps = "\n".join(f"{i}. {s.title}" for i, s in enumerate(STEPS, start=1))
    return await send_html(max_user_id,
                    f"🎬 <b>Демо всех функций: {len(STEPS)} шагов</b>\n\n{steps}\n\n"
                    "На каждом шаге бот присылает настоящие сообщения на вашей текущей компании, затем — что "
                    "проверить. Сообщения идут по одному: следующее — после ответа на предыдущее, отвеченное "
                    "удаляется. События реестров — имитация (в приложении помечены «Имитация для демо»), в конце их можно "
                    "убрать. Сроки, документы и законы — настоящие.",
                    _kb([[_callback("▶ Начать", "demo:1")]]))


async def run(max_user_id: int, arg: str, show_profile: Callable[[], Awaitable[None]]) -> None:
    """Кнопки тура: demo:<номер шага> | demo:stop | demo:clean."""
    ctx = await context(max_user_id, show_profile)
    if ctx is None:
        await send_html(max_user_id, "Сначала подключите компанию: пришлите ИНН (например, 7743212897), "
                                     "ответьте на вопросы и снова /demo.")
        return
    if arg in ("clean", "stop"):
        if arg == "clean":
            removed = await cleanup(ctx.inn)
            await send_html(max_user_id, f"🧹 Убрали демо-события: {removed}. Сроки, документы и законы остались. "
                                         "/demo — пройти ещё раз.")
        else:  # кнопку «Убрать» очередь не ждёт: она необязательная
            await send_html(max_user_id, "Демо остановлено. /demo — начать заново.",
                            _kb([[_callback("🧹 Убрать демо-события", "demo:clean")]]))
        await worker.dispatch()  # тур закончился — отпускаем очередь радара
        return
    n = int(arg)
    step = STEPS[n - 1]
    note = await step.run(ctx) if step.run else None
    text = f"☝️ <b>Шаг {n} из {len(STEPS)} · {step.title}</b>\n\n<b>Что проверить.</b> {step.check}"
    if note:
        text += f"\n\n⚠️ {note}"
    rows = []
    if step.title == "Мини-приложение":
        rows.append([{"type": "open_app", "text": "Открыть мини-приложение", **await bot_app()}])
    if n < len(STEPS):
        rows.append([_callback(f"▶ Дальше: {STEPS[n].title}"[:64], f"demo:{n + 1}"), _callback("⏹ Стоп", "demo:stop")])
    else:
        text += "\n\n✅ Демо пройдено. Имитации реестров остались в ленте и мини-приложении — уберите их кнопкой."
        rows.append([_callback("🧹 Убрать демо-события", "demo:clean")])
    # карточка — в общую очередь за сообщениями шага: придёт, когда на них ответят
    await worker.queue_text(ctx.user.id, text, _kb(rows), f"demo:{ctx.stamp}")
