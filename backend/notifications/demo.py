"""Демо-тур /demo: все функции бота по шагам на текущей компании (только при DEBUG=true).

Шаг — настоящие сообщения радара в чат, после них карточка «Шаг N из M»: что показали, что проверить
и кнопка «Дальше». Сроки обязанностей, документы и законы pravo.gov.ru — настоящие. События реестров —
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


@dataclass
class Ctx:
    max_user_id: int
    user: User
    business: Business
    today: date
    stamp: str                                  # уникальная часть ключей и меток этого шага
    show_profile: Callable[[], Awaitable[None]]  # карточка компании и итог онбординга (из бота)

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
    """Первый срок с документом — напоминанием с кнопкой «Подготовить документ», остальные виды
    документов (уведомление, платёжка ЕНП, памятка к отчёту, приказ о квоте) — сразу файлами."""
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
    first, *rest = by_kind.values()
    await _send(ctx, [first])
    async with SessionLocal() as db:
        for event in rest:
            await worker.send_document(db, event, ctx.max_user_id)
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


STEPS = (
    Step("Профиль и обязанности", profile,
         "Карточка: название, ИНН, ОГРН, ОКВЭД, категория и численность, регион, режим, источник и дата. "
         "Итог: список обязанностей, 5 ближайших сроков, льготы по численности со ссылками, кнопка ленты."),
    Step("Напоминания о сроках", reminders,
         "Сроки одной даты — одним сообщением: «почему вам», основание, перенос с выходного. Кнопки: "
         "«Сделано» → «Отмечено как выполненное», «Завтра» → «Напомним завтра в 9:00», «Не актуально» → "
         "«Больше не напомним», «Открыть» → экран задачи в мини-приложении."),
    Step("Документы к задачам", documents,
         "Под напоминанием — «📄 Подготовить документ»: нажмите, придёт .docx. Следом — остальные виды: "
         "уведомление КНД 1110355, реквизиты платёжки на ЕНП, памятка к отчёту (КНД, код периода), приказ о квоте."),
    Step("Проверки из ЕРКНМ", inspections,
         "Плановая выездная проверка (задача со сроком — дата начала, «Ваши права»), профилактический визит "
         "(без предписаний) и предостережение с текстом. Источник помечен «Имитация для демо»."),
    Step("ЕГРЮЛ: недостоверность", unreliable,
         "Отметка о недостоверности: дата записи, с какой даты возможно исключение (расчёт бота), задача "
         "«Недостоверные сведения в ЕГРЮЛ». Второе сообщение — как бот сообщает, что отметку сняли."),
    Step("ЕГРЮЛ: дисквалификация руководителя", disqualification,
         "Дисквалификация с датами и решением суда; второе сообщение — «срок дисквалификации истёк»."),
    Step("ЕГРЮЛ: предстоящее исключение", termination,
         "«Компания в процессе прекращения»: срок возражения (3 месяца, расчёт бота), форма Р38001, задача."),
    Step("ЕГРЮЛ: изменились сведения", egrul_changes,
         "Сменился руководитель и адрес — «было / стало» и предупреждение о захвате компании. Новый "
         "руководитель — иностранец: задача «Уведомить МВД» со сроком сегодня."),
    Step("Реестр МСП", msp,
         "Исключение из реестра МСП («Открыть» нет — у события нет срока, задачи в мини-приложении тоже), "
         "выход из микропредприятий с задачей на ЛНА (4 месяца), «компании нет в реестре»."),
    Step("Повтор и «Сделано» у состояния", repeat,
         "Исключение из МСП пришло ещё раз — так бот повторяет открытое состояние раз в 30 дней. Нажмите "
         "под ним «✅ Сделано» → «Проверим по реестру: если запись останется, напомним»."),
    Step("Новые законы (pravo.gov.ru)", pravo,
         "Настоящие акты за 30 дней: «Вышел акт, который касается вас», «Почему вам», «Может изменить ваши "
         "задачи», следом PDF. Вопрос «Да / Нет»: «Да» → «Запомнили — присылаем, что вышло» и акты по теме."),
    Step("Сообщения и команды", None,
         "Пришлите любой текст («что умеешь?») или фото — бот ответит подсказкой. /profile → «Изменить "
         "численность» → «36–100 человек»: «Профиль обновлён, появились обязанности: квота»; верните прежнюю. "
         "«Изменить режим»: у организации нет «Патента». Другой ИНН в чате — смена компании."),
    Step("Мини-приложение", None,
         "Откройте по кнопке ниже. Дашборд: колокольчик с точкой, «Сегодня / На неделе», задачи из демо "
         "(проверка, МВД, ЛНА, возражение). Задача: разделы, «Выполнено» с отменой, «Подготовить документ». "
         "Календарь: тап по дню переключает список, «Месяц / Неделя / Список». Профиль: «Обновить», "
         "«Сменить компанию». Уведомления: тихие часы, «Когда напоминать»."),
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
    return Ctx(max_user_id, user, business, date.today(), f"{datetime.now():%H%M%S%f}"[:11], show_profile)


async def intro(max_user_id: int) -> None:
    steps = "\n".join(f"{i}. {s.title}" for i, s in enumerate(STEPS, start=1))
    await send_html(max_user_id,
                    f"🎬 <b>Демо всех функций: {len(STEPS)} шагов</b>\n\n{steps}\n\n"
                    "На каждом шаге бот присылает настоящие сообщения на вашей текущей компании, затем — что "
                    "проверить. События реестров — имитация: они помечены «Имитация для демо», в конце их можно "
                    "убрать. Сроки, документы и законы — настоящие.",
                    _kb([[_callback("▶ Начать", "demo:1")]]))


async def run(max_user_id: int, arg: str, show_profile: Callable[[], Awaitable[None]]) -> None:
    """Кнопки тура: demo:<номер шага> | demo:stop | demo:clean."""
    ctx = await context(max_user_id, show_profile)
    if ctx is None:
        await send_html(max_user_id, "Сначала подключите компанию: пришлите ИНН (например, 7743212897), "
                                     "ответьте на вопросы и снова /demo.")
        return
    if arg == "clean":
        removed = await cleanup(ctx.inn)
        await send_html(max_user_id, f"🧹 Убрали демо-события: {removed}. Сроки, документы и законы остались. "
                                     "/demo — пройти ещё раз.")
        return
    if arg == "stop":
        await send_html(max_user_id, "Демо остановлено. /demo — начать заново.",
                        _kb([[_callback("🧹 Убрать демо-события", "demo:clean")]]))
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
    await send_html(max_user_id, text, _kb(rows))
