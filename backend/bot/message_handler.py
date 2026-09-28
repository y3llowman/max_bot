import asyncio
import html
import logging
import re
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select

from maxapi import Dispatcher, F
from maxapi.enums.parse_mode import ParseMode
from maxapi.filters.command import Command, CommandStart
from maxapi.types import BotStarted, ButtonsPayload, CallbackButton, MessageCallback, MessageCreated, OpenAppButton
from maxapi.context import BaseContext, State, StatesGroup

from bot.client import bot, bot_app
from core.config import DEBUG
from data_fetching import rmsp_client
from databases.businesses_db import Business, CompanyTaken, current_business, save_business
from databases.engine_start import SessionLocal
from databases.users_db import User
from notifications import demo as demo_tour
from notifications import worker
from notifications.models import BusinessProfile, RadarEvent
from notifications.planner import today_msk
from radar.deadlines import CATEGORY_RU, HEADCOUNT_RU, REGIME_RU, Profile, headcount_ru, region_name
from radar.render import company_name, date_ru, date_short, decap, plural

logger = logging.getLogger(__name__)

dp = Dispatcher()


class OrderState(StatesGroup):
    waiting_for_inn = State()


def is_valid_inn(inn: str) -> bool:
    """Проверяет формат и контрольные суммы ИНН (10 цифр — юрлицо, 12 — физлицо/ИП)."""
    if not re.fullmatch(r"\d{10}|\d{12}", inn):
        return False

    digits = [int(d) for d in inn]

    def checksum(coefficients: tuple[int, ...]) -> int:
        return sum(c * d for c, d in zip(coefficients, digits)) % 11 % 10

    if len(inn) == 10:
        return checksum((2, 4, 10, 3, 5, 9, 4, 6, 8)) == digits[9]

    return (
        checksum((7, 2, 4, 10, 3, 5, 9, 4, 6, 8)) == digits[10]
        and checksum((3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)) == digits[11]
    )


ASK_INN = "Пришлите ИНН компании или ИП — 10 или 12 цифр. Профиль соберём сами из реестров ФНС."

# Режима нет в открытых реестрах, численность есть не у всех — спрашиваем одним тапом
QUESTIONS = {
    "regime": ("Какой у вас режим налогообложения? От него зависят декларации и сроки уплаты.", REGIME_RU),
    "staff": ("Сколько у вас сотрудников? От этого зависят отчёты за работников и квота для инвалидов.",
              HEADCOUNT_RU),
}


MSP_SIGNS = {"is_social": "социальное предприятие", "is_hitech": "инновационная деятельность",
             "is_partnership": "участник программы партнёрства"}


def company_card(business: Business, profile: Profile) -> str:
    """Всё, что нашли о компании: реестр МСП и поправки пользователя. Выписка ЕГРЮЛ (адрес, КПП,
    руководитель) догружается в фоне и видна в профиле мини-приложения."""
    okved = (f"{business.main_activity_code} — {html.escape(business.main_activity_name)}"
             if profile.okved_main == business.main_activity_code else f"{profile.okved_main} (указан вами)")
    contacts = " · ".join(html.escape(c) for c in (business.phone, business.email, business.website) if c)
    signs = ", ".join(label for field, label in MSP_SIGNS.items() if getattr(business, field))
    lines = [
        f"<b>{html.escape(company_name(business.name))}</b>",
        f"ИНН {business.inn} · ОГРН {business.ogrn}",
        f"ОКВЭД: {okved}",
        " · ".join(filter(None, [CATEGORY_RU.get(business.category), headcount_ru(profile)])),
        f"Регион: {region_name(profile.region_code) or profile.region_code}",
        f"Лицензии: {'есть' if profile.has_licenses else 'нет'}",
        f"Контакты: {contacts}" if contacts else "",
        f"Признаки МСП: {signs}" if signs else "",
        f"Режим: {REGIME_RU[profile.tax_regime]}" if profile.tax_regime
        else "Режим налогообложения: в открытых реестрах его нет — спросим",
        f"<i>Источник: реестр МСП (ФНС), данные на {date_ru(business.updated_at.date())}</i>",
    ]
    return "\n".join(line for line in lines if line)


def app_keyboard(app: dict):
    return ButtonsPayload(buttons=[[OpenAppButton(text="Открыть приложение", **app)]]).pack()


def edit_button(app: dict) -> OpenAppButton:
    """Экран «Данные компании» в мини-приложении (диплинк profile_edit)."""
    return OpenAppButton(text="✏️ Исправить в приложении", **app, payload="profile_edit")


def question_keyboard(question: str, legal_entity: bool):
    _, options = QUESTIONS[question]
    return ButtonsPayload(buttons=[
        [CallbackButton(text=label[:1].upper() + label[1:], payload=f"q:{question}:{value}")]
        for value, label in options.items()
        if not (legal_entity and value == "psn")  # патент — только для ИП (ст. 346.43 НК РФ)
    ]).pack()


async def say(max_user_id: int, text: str, *attachments) -> str | None:
    """Сообщение в чат; возвращает его id (для вопроса — чтобы удалить после ответа)."""
    sent = await bot.send_message(user_id=max_user_id, text=text, format=ParseMode.HTML,
                                  attachments=list(attachments) or None)
    return sent.message.body.mid if sent else None


async def ask(max_user_id: int, question: str, legal_entity: bool) -> None:
    """Вопрос профиля кнопками. Пока на него не ответили, очередь радара молчит (worker.hold)."""
    await worker.hold(max_user_id, await say(max_user_id, QUESTIONS[question][0], question_keyboard(question, legal_entity)))


def message_id(event: MessageCallback) -> str | None:
    """Сообщение, под которым нажали кнопку."""
    return event.message.body.mid if event.message else None


async def find_user(db, max_user_id: int) -> User | None:
    return (await db.execute(select(User).where(User.max_user_id == max_user_id))).scalar_one_or_none()


async def obligations_summary(inn: str) -> str:
    """Итог онбординга — коротко: сколько обязанностей и ближайший срок. Список, календарь, документы
    и льготы — в мини-приложении."""
    today = today_msk()
    async with SessionLocal() as db:
        profile = await worker.load_profile(db, inn)
        events = list(await db.scalars(
            select(RadarEvent)
            .where(RadarEvent.inn == inn, RadarEvent.key.like(f"obl:{inn}:%"),
                   RadarEvent.status == "open", RadarEvent.due >= today)
            .order_by(RadarEvent.due)
        ))
    count = len({event.payload["code"] for event in events})
    lines = [f"📡 <b>Радар настроен: {count} {plural(count, 'обязанность', 'обязанности', 'обязанностей')}</b>"]
    if events:
        first = events[0]
        lines.append(f"Ближайший срок — {date_short(first.due)}: {first.payload['title']} ({decap(first.payload['period'])}).")
    if profile.tax_regime == "psn" and not (profile.patent_from and profile.patent_to):
        lines.append("Укажите срок патента в «Данных компании» — посчитаю даты оплаты.")
    lines += ["", "Список, календарь и документы — в приложении. Когда выйдет закон, подойдёт срок или "
                  "изменится запись в реестре — пришлю сюда коротко."]
    return "\n".join(lines)


async def next_step(max_user_id: int) -> bool:
    """После ИНН и после каждого ответа: следующий вопрос профиля или итог — список обязанностей.
    True — задан вопрос (очередь радара ждёт ответа на него)."""
    async with SessionLocal() as db:
        user = await find_user(db, max_user_id)
        business = await current_business(db, user.id) if user else None
        profile = await worker.load_profile(db, business.inn) if business else None
    if business is None:
        await say(max_user_id, ASK_INN)
    elif profile.tax_regime is None:
        await ask(max_user_id, "regime", profile.is_legal_entity)
        return True
    elif profile.headcount is None:
        await ask(max_user_id, "staff", profile.is_legal_entity)
        return True
    else:
        await say(max_user_id, await obligations_summary(business.inn), app_keyboard(await bot_app()))
    return False


async def _save_business(max_user_id: int, sender, record: rmsp_client.RmspRecord) -> Business:
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.max_user_id == max_user_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(max_user_id=max_user_id)
            db.add(user)
        user.username = sender.username
        user.first_name = sender.first_name
        user.last_name = sender.last_name

        # user_businesses ссылается на users.id — пользователь должен попасть в БД раньше связи
        await db.flush()
        return await save_business(db, user.id, record)


_background: set[asyncio.Task] = set()  # ссылки на фоновые задачи: без них задачу может собрать сборщик мусора


def _start_radar(inn: str) -> None:
    """Медленные источники — в фоне: выписка ЕГРЮЛ и выгрузки ЕРКНМ (ошибки логирует сам scan_in_background)."""
    task = asyncio.create_task(worker.scan_in_background(inn))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def start(max_user_id: int, context: BaseContext) -> None:
    """Нет компании — ждём ИНН; есть — продолжаем с того места, где остановились."""
    async with SessionLocal() as db:
        user = await find_user(db, max_user_id)
        connected = user is not None and await current_business(db, user.id) is not None
        if user is not None and not user.is_active:  # снова запустил бота после блокировки — пишем снова
            user.is_active = True
            await db.commit()
    if not connected:
        await context.set_state(OrderState.waiting_for_inn)
    await next_step(max_user_id)


# /start
@dp.message_created(CommandStart())
async def hello(event: MessageCreated, context: BaseContext):
    await start(event.message.sender.user_id, context)


# первый запуск бота 
@dp.bot_started()
async def on_bot_started(event: BotStarted, context: BaseContext):
    await start(event.user.user_id, context)


@dp.message_created(Command("profile"))
async def on_profile(event: MessageCreated):
    max_user_id = event.message.sender.user_id
    async with SessionLocal() as db:
        user = await find_user(db, max_user_id)
        business = await current_business(db, user.id) if user else None
        profile = await worker.load_profile(db, business.inn) if business else None
    if business is None:
        await say(max_user_id, ASK_INN)
        return
    app = await bot_app()
    await say(max_user_id, company_card(business, profile), ButtonsPayload(buttons=[
        [OpenAppButton(text="✏️ Изменить данные", **app, payload="profile_edit")],
        [OpenAppButton(text="Открыть приложение", **app)],
    ]).pack())

# @dp.message_created(Command("demo_mode"))
#     async def on_demo_remind(event: MessageCreated):
#         sent = await worker.demo_remind(event.message.sender.user_id)
#         if not sent:
#             await event.message.answer("Открытых сроков нет — сначала подключите компанию: пришлите ИНН.")

if DEBUG:
    # триггеры для демо
    @dp.message_created(Command("demo_remind"))
    async def on_demo_remind(event: MessageCreated):
        sent = await worker.demo_remind(event.message.sender.user_id)
        if not sent:
            await event.message.answer("Открытых сроков нет — сначала подключите компанию: пришлите ИНН.")

    @dp.message_created(Command("demo_event"))
    async def on_demo_event(event: MessageCreated):
        args = event.message.body.text.split()[1:]
        await event.message.answer(await worker.demo_event(event.message.sender.user_id, args[0] if args else ""))

    @dp.message_created(Command("demo_law"))
    async def on_demo_law(event: MessageCreated):
        await event.message.answer(await worker.demo_law(event.message.sender.user_id))

    async def show_profile(max_user_id: int) -> None:
        """Шаг тура «Регистрация»: та же карточка «Всё верно?», что после ИНН."""
        async with SessionLocal() as db:
            user = await find_user(db, max_user_id)
            business = await current_business(db, user.id)
        await show_found(max_user_id, business)

    @dp.message_created(Command("laws"))
    async def on_laws(event: MessageCreated):
        """Проверка ленты законов: что бот отобрал за неделю и почему."""
        await say(event.message.sender.user_id, await worker.laws_report())

    # полный демо-сценарий по шагам (notifications/demo.py)
    @dp.message_created(Command("demo"))
    async def on_demo(event: MessageCreated):
        max_user_id = event.message.sender.user_id
        await worker.hold(max_user_id, await demo_tour.intro(max_user_id))

    @dp.message_callback(F.callback.payload.startswith("demo:"))
    async def on_demo_step(event: MessageCallback):
        await event.answer()
        max_user_id = event.callback.user.user_id
        await worker.answered(max_user_id, message_id(event), release=False)  # карточка шага отработала
        await demo_tour.run(max_user_id, event.callback.payload.removeprefix("demo:"), lambda: show_profile(max_user_id))

@dp.message_created(states=OrderState.waiting_for_inn)
async def on_inn(event: MessageCreated, context: BaseContext):
    inn = (event.message.body.text or "").strip()  # фото и стикеры приходят без текста
    logger.info("Пользователь %s ввёл ИНН: %s", 'тип:' + str(type(inn)), 'ИНН:' + inn)

    if not is_valid_inn(inn):
        # пришел некорректный ИНН
        await event.message.answer(
            "Некорректный ИНН. Введите 10 цифр (для организации) "
            "или 12 цифр (для ИП/физлица) без пробелов:"
        )
        return

    if event.message.sender is None:
        return

    try:
        record = await asyncio.to_thread(rmsp_client.fetch_by_inn, inn)
    except Exception:
        logger.exception("rmsp lookup failed for %s", inn)
        await event.message.answer("Реестр МСП (ФНС) сейчас не отвечает. Пришлите ИНН ещё раз через пару минут.")
        return
    if record is None:
        await event.message.answer(
            f"Компанию с ИНН {inn} не нашли в реестре МСП. "
            "Проверьте номер и отправьте его ещё раз:"
        )
        return

    # пришел корректный ИНН
    max_user_id = event.message.sender.user_id
    try:
        business = await _save_business(max_user_id, event.message.sender, record)
    except CompanyTaken:
        await event.message.answer(
            "Эту компанию уже подключил другой пользователь MAX. Одну компанию ведёт один аккаунт — иначе "
            "посторонний мог бы менять её профиль и задачи. В рабочей версии владелец будет подтверждаться "
            "через Госуслуги. Пришлите другой ИНН:")
        return
    await worker.registry_loaded(inn, asdict(record))
    _start_radar(str(inn))

    await context.set_state(None)
    await show_found(max_user_id, business)


async def show_found(max_user_id: int, business: Business) -> None:
    """Всё, что нашли о компании, и «Всё верно?»: «Да» — вопросы профиля в чате, «Исправить» — экран
    «Данные компании» в приложении (оттуда можно поправить и позже). Очередь ждёт ответа на карточку."""
    async with SessionLocal() as db:
        profile = await worker.load_profile(db, business.inn)
    app = await bot_app()
    keyboard = ButtonsPayload(buttons=[[CallbackButton(text="✅ Да, всё верно", payload="reg:ok")],
                                       [edit_button(app)]]).pack()
    mid = await say(max_user_id, "Нашли вашу компанию:\n" + company_card(business, profile) + "\n\nВсё верно?", keyboard)
    await worker.hold(max_user_id, mid)


@dp.message_callback(F.callback.payload == "reg:ok")
async def on_registration_ok(event: MessageCallback):
    """Данные верны: карточку убираем, дальше — вопросы профиля или итог."""
    await event.answer(notification="Отлично")
    max_user_id = event.callback.user.user_id
    await worker.answered(max_user_id, message_id(event), release=False)
    if not await next_step(max_user_id):
        await worker.dispatch()


# ИНН без /start: состояние бота живёт в памяти и сбрасывается при перезапуске
@dp.message_created(F.message.body.text.regexp(r"^\s*(\d{10}|\d{12})\s*$"))
async def on_inn_any_state(event: MessageCreated, context: BaseContext):
    await on_inn(event, context)


@dp.message_callback(F.callback.payload.startswith("ask:"))
async def on_ask(event: MessageCallback):
    await event.answer()
    question = event.callback.payload.removeprefix("ask:")
    async with SessionLocal() as db:
        user = await find_user(db, event.callback.user.user_id)
        business = await current_business(db, user.id) if user else None
    await ask(event.callback.user.user_id, question, business is not None and business.subject_type == "UL")

@dp.message_callback(F.callback.payload.startswith("q:"))
async def on_answer(event: MessageCallback):
    """Ответ на вопрос профиля: сохранить, пересчитать обязанности, задать следующий вопрос."""
    _, question, value = event.callback.payload.split(":")
    max_user_id = event.callback.user.user_id
    async with SessionLocal() as db:
        user = await find_user(db, max_user_id)
        business = await current_business(db, user.id) if user else None
        if business is None:
            await event.answer(notification="Сначала пришлите ИНН")
            return
        current = await worker.load_profile(db, business.inn)
        was_complete = current.tax_regime is not None and current.headcount is not None
        profile = await db.get(BusinessProfile, business.inn) or BusinessProfile(inn=business.inn, flags={}, bank_biks=[])
        if question == "regime":
            profile.tax_regime = value
            label = REGIME_RU[value]
        else:
            profile.headcount = int(value)
            profile.has_employees = profile.headcount > 0
            label = HEADCOUNT_RU[profile.headcount]
        profile.answered_at = datetime.now(timezone.utc)
        db.add(profile)
        await db.commit()
        inn = business.inn
    added, removed = await worker.materialize_for(inn)
    await event.answer(notification=f"Сохранили: {label}")
    # вопрос отвечен — убираем его; очередь радара отпускаем, только если следующего вопроса нет
    await worker.answered(max_user_id, message_id(event), release=False)
    if not was_complete:
        if not await next_step(max_user_id):
            await worker.dispatch()
        return
    # профиль уже был заполнен — сообщаем, как изменился список обязанностей
    lines = ["Профиль обновлён."]
    if added:
        lines += ["", "<b>Появились обязанности</b>", *[f"• {title}" for title in added]]
    if removed:
        lines += ["", "<b>Больше не касаются</b>", *[f"• {title}" for title in removed]]
    if not added and not removed:
        lines.append("Список обязанностей не изменился.")
    await say(max_user_id, "\n".join(lines), app_keyboard(await bot_app()))
    await worker.dispatch()


@dp.message_callback(F.callback.payload.startswith("flag:"))
async def on_flag(event: MessageCallback):
    """Вопрос о признаке компании перед рассылкой акта: flag:<признак>:yes|no (radar.render.flag_keyboard)."""
    _, flag, value = event.callback.payload.split(":")
    await event.answer(notification=await worker.answer_flag(event.callback.user.user_id, flag, value == "yes"))
    await worker.answered(event.callback.user.user_id, message_id(event))


@dp.message_callback(F.callback.payload.startswith("ev:"))
async def on_event_action(event: MessageCallback):
    """Кнопки под пушем: ev:<ids>:list|done|mute (radar.render.keyboard; snooze1d — у старых сообщений)."""
    _, ids, action = event.callback.payload.split(":")
    answer = await worker.apply_action(event.callback.user.user_id, [int(i) for i in ids.split(",")], action)
    await event.answer(notification=answer)
    await worker.answered(event.callback.user.user_id, message_id(event))  # ответили — убрать и прислать следующее


@dp.message_callback(F.callback.payload.startswith("doc:"))
async def on_document(event: MessageCallback):
    """«Подготовить документ» под напоминанием: doc:<event_id>:<код документа>."""
    max_user_id = event.callback.user.user_id
    async with SessionLocal() as db:
        _, events = await worker.user_events(db, max_user_id, [int(event.callback.payload.split(":")[1])])
        if not events or not events[0].payload.get("document"):
            await event.answer(notification="Задача не найдена")
            return
        await event.answer(notification="Готовим документ…")
        await worker.send_document(db, events[0], max_user_id)


# Последним: всё, что не ИНН, не команда и не кнопка. Без него бот молчал бы.
@dp.message_created()
async def on_other(event: MessageCreated):
    await event.message.answer(
        "Я слежу за вашей компанией сам и пишу, когда появляется то, что касается именно её: "
        "новый закон, срок, запись в реестре.\n\n"
        "Пришлите ИНН — подключу компанию или сменю её. /profile — профиль компании, /start — продолжить настройку."
    )
