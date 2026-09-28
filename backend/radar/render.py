"""Заполнение шаблонов и сборка тела POST /messages для MAX.

Почему format="html", а не markdown: данные из реестров содержат `_`, `*`, кавычки
(MOSTAR.7@YANDEX.RU, ООО "…"). Jinja autoescape экранирует их для HTML автоматически,
а для markdown пришлось бы писать своё экранирование.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from jinja2 import DictLoader, Environment, StrictUndefined, pass_context

from .catalog import CATALOG, ICON
from .templates import TEMPLATES

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def as_date(d: date | str | None) -> date | None:
    """Даты в radar_events.payload лежат строками (JSONB): ISO или «ДД.ММ.ГГГГ» из реестров
    (реестр МСП добавляет время: «10.07.2017 00:00:00» — отбрасываем его)."""
    if not isinstance(d, str):
        return d
    return datetime.strptime(d[:10], "%d.%m.%Y").date() if "." in d else date.fromisoformat(d[:10])


def date_ru(d: date | str | None) -> str:
    d = as_date(d)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}" if d else "—"


def date_short(d: date | str | None) -> str:
    d = as_date(d)
    return f"{d:%d.%m}" if d else "—"


@pass_context
def rel(ctx, d: date | str) -> str:
    n = (as_date(d) - ctx["today"]).days
    if n == 0:
        return "сегодня"
    if n == 1:
        return "завтра"
    if n == -1:
        return "вчера"
    word = plural(n, "день", "дня", "дней")
    return f"через {n} {word}" if n > 0 else f"{-n} {word} назад"


def fio(s: str | None) -> str:
    """'СТРОК МАРИНА ИВАНОВНА' → 'Строк Марина Ивановна' (с дефисами тоже)."""
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in (s or "").split())


def fio_short(s: str | None) -> str:
    parts = fio(s).split()
    return parts[0] + " " + "".join(f"{p[0]}." for p in parts[1:]) if len(parts) > 1 else fio(s)


def company_name(s: str) -> str:
    """ООО "МОСТАР" → ООО «МОСТАР»"""
    return re.sub(r'"([^"]*)"', r"«\1»", s or "")


env = Environment(loader=DictLoader(TEMPLATES), autoescape=True, undefined=StrictUndefined,
                  trim_blocks=True, lstrip_blocks=True)
def cap1(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


env.filters.update(cap1=cap1, date_ru=date_ru, date_short=date_short, rel=rel, fio=fio,
                   fio_short=fio_short, plural=plural)


# ----------------------------------------------------------------- контекст
def company_ctx(egrul: dict | None, msp: dict | None, inn: str) -> dict:
    name = (egrul or {}).get("short_name") or (msp or {}).get("name") or inn
    return {"name": company_name(name), "inn": inn,
            "ogrn": (egrul or {}).get("ogrn") or (msp or {}).get("ogrn")}


SOURCE_NAMES = {"egrul": "ЕГРЮЛ (ФНС)", "msp": "Единый реестр субъектов МСП (ФНС)",
                "erknm": "Единый реестр контрольных (надзорных) мероприятий"}


def build_context(event_type: str, payload: dict, company: dict, today: date,
                  src: str | None = None, fetched_at: date | None = None,
                  related: list[str] | None = None, **extra) -> dict:
    et = CATALOG.get(event_type)
    return {
        "icon": ICON[et.severity] if et else "📡",
        "company": company,
        "ev": payload,
        "src": {"name": SOURCE_NAMES.get(src, src or ""), "fetched_at": fetched_at or today},
        "related": related or [],
        "today": today,
        **extra,
    }


def render(template: str, ctx: dict) -> str:
    text = env.get_template(template).render(**ctx)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ----------------------------------------------------------------- клавиатура и тело
def keyboard(event_ids: list[int], source_url: str | None = None, docs: list | None = None,
             app: dict | None = None) -> dict:
    ids = ",".join(map(str, event_ids))           # payload короткий: ev:<ids>:<action>
    rows = [[{"type": "callback", "text": "✅ Сделано", "payload": f"ev:{ids}:done"},
             {"type": "callback", "text": "⏰ Завтра", "payload": f"ev:{ids}:snooze1d"}],
            [{"type": "callback", "text": "🔕 Не актуально", "payload": f"ev:{ids}:mute"}]]
    # документы к шагу «Что сделать»: по кнопке генерируем .docx и присылаем файлом
    for d in docs or []:
        rows.insert(-1, [{"type": "callback", "text": f"📄 {d.button}", "payload": f"doc:{event_ids[0]}:{d.code}"}])
    link_row = []
    if app:  # app — bot.client.bot_app(): web_app и contact_id бота; диплинк task_<id> открывает экран задачи
        link_row.append({"type": "open_app", "text": "Открыть", **app,
                         "payload": f"task_{event_ids[0]}"})
    if source_url:
        link_row.append({"type": "link", "text": "Источник", "url": source_url})
    if link_row:
        rows.append(link_row)                     # link/open_app — не больше 3 в ряду
    return {"type": "inline_keyboard", "payload": {"buttons": rows}}


def message_body(text: str, event_ids: list[int] | None = None, source_url: str | None = None,
                 docs: list | None = None) -> dict:
    body: dict = {"text": text, "format": "html"}
    if event_ids:
        body["attachments"] = [keyboard(event_ids, source_url, docs)]
    return body


def question_body(text: str, flag: str) -> dict:
    """Ответ сохраняем в business_profiles.flags и перезапускаем матчинг ленты."""
    row = [{"type": "callback", "text": t, "payload": f"q:{flag}:{v}"}
           for t, v in (("Да", "yes"), ("Нет", "no"), ("Не знаю", "skip"))]
    return {"text": text, "format": "html",
            "attachments": [{"type": "inline_keyboard", "payload": {"buttons": [row]}}]}


SOURCE_URLS = {"egrul": "https://egrul.nalog.ru/", "msp": "https://rmsp.nalog.ru/",
               "erknm": "https://proverki.gov.ru/portal/public-search"}
