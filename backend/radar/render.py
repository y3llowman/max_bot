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
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in (s or "").split())


def fio_short(s: str | None) -> str:
    parts = fio(s).split()
    return parts[0] + " " + "".join(f"{p[0]}." for p in parts[1:]) if len(parts) > 1 else fio(s)


def company_name(s: str) -> str:
    return re.sub(r'"([^"]*)"', r"«\1»", s or "")


env = Environment(loader=DictLoader(TEMPLATES), autoescape=True, undefined=StrictUndefined,
                  trim_blocks=True, lstrip_blocks=True)
def cap1(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def decap(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


env.filters.update(cap1=cap1, decap=decap, date_ru=date_ru, date_short=date_short, rel=rel, fio=fio,
                   fio_short=fio_short, plural=plural, as_date=as_date)


def company_ctx(egrul: dict | None, msp: dict | None, inn: str) -> dict:
    name = (egrul or {}).get("short_name") or (msp or {}).get("name") or inn
    return {"name": company_name(name), "inn": inn,
            "ogrn": (egrul or {}).get("ogrn") or (msp or {}).get("ogrn")}


SOURCE_NAMES = {"egrul": "ЕГРЮЛ (ФНС)", "msp": "Единый реестр субъектов МСП (открытые данные ФНС)",
                "erknm": "Единый реестр контрольных (надзорных) мероприятий",
                "pravo": "Официальный интернет-портал правовой информации (pravo.gov.ru)",
                "demo": "Имитация для демо (/demo), не данные реестра"}


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


def keyboard(event_ids: list[int], app: dict | None = None, link: str | None = None) -> dict:
    ids = ",".join(map(str, event_ids))
    rows = [[{"type": "callback", "text": "📋 В список дел", "payload": f"ev:{ids}:list"},
             {"type": "callback", "text": "✅ Сделано", "payload": f"ev:{ids}:done"}],
            [{"type": "callback", "text": "🔕 Не актуально", "payload": f"ev:{ids}:mute"}]]
    if app:
        rows[1].append({"type": "open_app", "text": "Открыть", **app, "payload": f"task_{event_ids[0]}"})
    if link:
        rows.append([{"type": "link", "text": "📄 Официальный текст", "url": link}])
    return {"type": "inline_keyboard", "payload": {"buttons": rows}}


def flag_keyboard(flag: str) -> dict:
    row = [{"type": "callback", "text": text, "payload": f"flag:{flag}:{value}"}
           for text, value in (("Да", "yes"), ("Нет", "no"))]
    return {"type": "inline_keyboard", "payload": {"buttons": [row]}}


SOURCE_URLS = {"egrul": "https://egrul.nalog.ru/", "msp": "https://www.nalog.gov.ru/opendata/7707329152-rsmp/",
               "erknm": "https://proverki.gov.ru/portal/public-search"}
