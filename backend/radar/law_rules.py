"""Разметка актов без LLM: формулировки закона → ключевые поля профиля бизнеса.

Идея: в НПА адресат почти всегда назван устойчивыми оборотами — «индивидуальные
предприниматели, применяющие упрощенную систему налогообложения», «работодатели»,
«осуществляющие розничную торговлю», «коды 62.01 ОКВЭД 2». Словарь правил ниже
переводит такие обороты в поля Audience, а каждое срабатывание сохраняет цитату —
она же объясняет пользователю «почему вам».

Всё детерминировано: одинаковый текст → одинаковый результат, любое решение
можно показать фрагментом текста. Словарь пополняется без переобучения чего-либо.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from .detectors import add_months
from .regulations import Audience, FeedItem

USN = ("usn_income", "usn_ie")


# ----------------------------------------------------------------- нормализация
def normalize(text: str) -> str:
    t = (text or "").replace("ё", "е").replace("Ё", "Е").replace("\u00ad", "")
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)      # переносы слов из PDF: «предпри-\nниматель»
    return re.sub(r"\s+", " ", t).strip()


# ----------------------------------------------------------------- словарь
@dataclass(frozen=True)
class Rule:
    field: str          # legal_forms | tax_regimes | okved_prefixes | flags | msp_categories | has_employees | subject
    values: tuple       # что добавить в поле
    pattern: str        # regex по нормализованному тексту в нижнем регистре
    label: str          # как назвать пользователю
    action: str = ""    # что проверить (попадает в «Что сделать»)


RULES: list[Rule] = [
    # --- кто адресат вообще (не сужает, но делает акт релевантным бизнесу)
    Rule("legal_forms", ("le",), r"\bорганизаци\w*|юридическ\w* лиц", "организации"),
    Rule("legal_forms", ("ip",), r"индивидуальн\w* предпринимател", "индивидуальные предприниматели"),
    Rule("subject", (True,), r"хозяйствующ\w* субъект|субъект\w* предпринимательск|налогоплательщик", "бизнес"),
    # --- налоговые режимы (АУСН раньше УСН: иначе «автоматизированная упрощенная» поймается как УСН)
    Rule("tax_regimes", ("ausn",), r"автоматизированн\w* упрощенн\w* систем\w* налогообложени", "АУСН",
         "Проверьте, меняются ли для вас ставки, лимиты или сроки."),
    Rule("tax_regimes", USN, r"упрощенн\w* систем\w* налогообложени",
         "УСН", "Проверьте, меняются ли для вас ставки, лимиты или сроки."),
    Rule("tax_regimes", ("psn",), r"патентн\w* систем\w* налогообложени", "патент"),
    Rule("tax_regimes", ("osno",), r"налог\w* на прибыль организаций", "налог на прибыль"),
    # --- размер
    Rule("msp_categories", (1,), r"микропредприяти", "микропредприятия"),
    Rule("msp_categories", (1, 2, 3), r"субъект\w* малого и среднего предпринимательства", "субъекты МСП"),
    # --- сотрудники
    Rule("has_employees", (True,), r"\bработодател\w*|трудов\w* договор|страхов\w* взнос", "работодатели",
         "Проверьте кадровые документы и расчёты по взносам."),
    # --- признаки деятельности (ответы пользователя в profile.flags)
    Rule("flags", ("marketplace_seller",), r"маркетплейс|посредническ\w* (?:цифров\w* )?платформ",
         "продажи через платформы", "Проверьте условия работы с площадками."),
    Rule("flags", ("works_with_selfemployed",), r"налог\w* на профессиональн\w* доход|самозанят",
         "работа с самозанятыми", "Проверьте договоры с самозанятыми исполнителями."),
    Rule("flags", ("gov_procurement",), r"контрактн\w* систем\w* в сфере закупок|государственн\w* и муниципальн\w* нужд",
         "госзакупки", "Проверьте условия текущих контрактов и заявок."),
    Rule("flags", ("cash_register",), r"контрольно-кассов\w* техник|\bккт\b", "расчёты через кассу",
         "Проверьте, нужно ли обновить кассу или порядок расчётов."),
    Rule("flags", ("marked_goods",), r"маркировк\w* товар|средств\w* идентификации", "маркировка товаров",
         "Проверьте, попадают ли ваши товары под новые требования маркировки."),
    Rule("flags", ("foreign_workers",), r"иностранн\w* граждан", "иностранные работники",
         "Проверьте документы работников-иностранцев."),
    Rule("flags", ("vat_payer",), r"налог\w* на добавленную стоимость", "НДС"),
    # --- отрасли → префиксы ОКВЭД
    Rule("okved_prefixes", ("47",), r"розничн\w* торговл", "розничная торговля"),
    Rule("okved_prefixes", ("56",), r"общественн\w* питани", "общепит"),
    Rule("okved_prefixes", ("55",), r"гостиничн\w* услуг|средств\w* размещения", "гостиницы"),
    Rule("okved_prefixes", ("49.3",), r"перевозк\w* пассажир|легков\w* такси", "перевозка пассажиров"),
    Rule("okved_prefixes", ("49.4",), r"перевозк\w* груз\w* автомобильн", "грузоперевозки"),
    Rule("okved_prefixes", ("79",), r"туроператор|турагент|туристск\w* продукт", "туризм"),
    Rule("okved_prefixes", ("85",), r"образовательн\w* деятельност", "образование"),
    Rule("okved_prefixes", ("86",), r"медицинск\w* деятельност", "медицина"),
    Rule("okved_prefixes", ("62", "63"), r"информационн\w* технологи|программ\w* для (?:эвм|электронных вычислительных машин)",
         "IT"),
    Rule("okved_prefixes", ("11.01", "11.02", "11.03", "47.25"), r"алкогольн\w* продукци", "алкоголь"),
    Rule("okved_prefixes", ("12", "47.26"), r"табачн\w* (?:продукци|издели)|никотинсодержащ", "табак"),
    Rule("okved_prefixes", ("21", "47.73"), r"лекарственн\w* (?:средств|препарат)", "лекарства"),
]

# Поправки часто не называют адресата («Внести в статью 346.21 НК изменения…») —
# адресат следует из главы Налогового кодекса, которую меняют.
NK_CHAPTERS = [
    # (с, по, поле, значения, подпись)
    ((143, 0), (178, 99), "flags", ("vat_payer",), "гл. 21 НК (НДС)"),
    ((207, 0), (233, 99), "has_employees", (True,), "гл. 23 НК (НДФЛ, налоговые агенты)"),
    ((246, 0), (333, 99), "tax_regimes", ("osno",), "гл. 25 НК (налог на прибыль)"),
    ((346, 11), (346, 25), "tax_regimes", USN, "гл. 26.2 НК (УСН)"),
    ((346, 43), (346, 53), "tax_regimes", ("psn",), "гл. 26.5 НК (патент)"),
    ((410, 0), (418, 99), "okved_prefixes", ("47",), "гл. 33 НК (торговый сбор)"),
    ((419, 0), (432, 99), "has_employees", (True,), "гл. 34 НК (страховые взносы)"),
]
RE_NK = re.compile(r"налогового кодекса")
RE_ART_NUM = re.compile(r"(?<![\d.])(\d{3})(?:\.(\d{1,2}))?(?![\d.])")


def nk_hits(t: str, src: str) -> list["Hit"]:
    out, seen = [], set()
    for m in RE_NK.finditer(t):
        window = t[max(0, m.start() - 160): m.start()]
        k = window.rfind("стать")
        if k == -1:
            continue
        for a, b in RE_ART_NUM.findall(window[k:]):
            art = (int(a), int(b or 0))
            for lo, hi, fld, vals, label in NK_CHAPTERS:
                if lo <= art <= hi and label not in seen:
                    seen.add(label)
                    out.append(Hit(fld, vals, label, _quote(src, max(0, m.start() - 160) + k, m.end()),
                                   action="Проверьте, как изменение отразится на ваших расчётах и сроках уплаты."))
    return out


NARROWING = ("tax_regimes", "okved_prefixes", "flags", "msp_categories", "has_employees", "regions")

STOP_TITLE = re.compile(r"о награждении|о присвоении|о назначении|об освобождении|почетн\w* грамот|"
                        r"об исполнении бюджета|о бюджете|о внесении изменений в состав", re.I)

EXCLUSION = re.compile(r"(?:за исключением|кроме|не распространяется на|не применяется в отношении)[^.;]{0,220}")

OKVED_CODE = re.compile(r"(?<![\d.])(\d{2}\.\d{1,2}(?:\.\d{1,2})?)(?![\d.])")
MAIN_ONLY = re.compile(r"основн\w* вид\w* (?:экономической )?деятельности")

# Регион — только по принявшему органу для блока «subjects» (в тексте федеральных актов «г. Москва» — не таргетинг)
REGION_BY_AUTHORITY = {"москв": "77", "санкт-петербург": "78", "московской област": "50", "татарстан": "16",
                       "свердловск": "66", "новосибирск": "54", "краснодарск": "23", "башкортостан": "02",
                       "нижегородск": "52", "самарск": "63"}  # TODO: дополнить до всех субъектов


# ----------------------------------------------------------------- даты вступления в силу
MONTHS = {m: i for i, m in enumerate(["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
                                      "сентября", "октября", "ноября", "декабря"], start=1)}
WORD_NUM = {"одного": 1, "двух": 2, "трех": 3, "шести": 6, "десяти": 10, "тридцати": 30, "шестидесяти": 60,
            "девяноста": 90, "ста восьмидесяти": 180}

RE_EXACT = re.compile(r"(?:вступа\w*|вводится|применя\w*) в (?:силу|действие)?\s*с (\d{1,2}) (" + "|".join(MONTHS) +
                      r") (\d{4})")
RE_EXACT2 = re.compile(r"применя\w* с (\d{1,2}) (" + "|".join(MONTHS) + r") (\d{4})")
RE_ON_PUB = re.compile(r"вступа\w* в силу (?:со дня|с даты) (?:его |ее |их )?официального опубликования")
RE_AFTER = re.compile(r"вступа\w* в силу по истечении (\d+|" + "|".join(WORD_NUM) +
                      r") (дн\w*|месяц\w*) после дня (?:его |ее |их )?официального опубликования")


def effective_dates(t: str, published: date | None) -> list[date]:
    out = {date(int(y), MONTHS[m], int(d)) for rx in (RE_EXACT, RE_EXACT2) for d, m, y in rx.findall(t)}
    if published:
        if RE_ON_PUB.search(t):
            out.add(published)
        for n, unit in RE_AFTER.findall(t):
            n = int(n) if n.isdigit() else WORD_NUM[n]
            # «по истечении N дней после дня опубликования» → действует с (N+1)-го дня
            out.add(published + timedelta(days=n + 1) if unit.startswith("дн") else add_months(published, n) + timedelta(days=1))
    return sorted(out)


# ----------------------------------------------------------------- классификация
@dataclass
class Hit:
    field: str
    values: tuple
    label: str
    quote: str
    excluded: bool = False
    action: str = ""


@dataclass
class Classification:
    relevant: bool
    reason: str
    hits: list[Hit] = field(default_factory=list)
    audience: Audience | None = None
    effective: list[date] = field(default_factory=list)
    specificity: int = 0
    auto_publish: bool = False


def _quote(t: str, start: int, end: int, width: int = 70) -> str:
    cut = t.find(" ¶ ")                          # не смешиваем текст акта и его название
    lo, hi = (0, cut) if cut == -1 or start < cut else (cut + 3, len(t))
    if cut == -1:
        hi = len(t)
    a, b = max(lo, start - width), min(hi, end + width)
    a = t.rfind(" ", lo, a) + 1 if a > lo else lo
    b = t.find(" ", b, hi) if t.find(" ", b, hi) != -1 else hi
    return t[a:b].strip()


def classify(name: str, text: str, published: date | None = None, authority: str = "",
             block: str = "") -> Classification:
    if STOP_TITLE.search(name or ""):
        return Classification(False, "служебный акт (награждение, назначение, бюджет)")
    src = normalize(f"{text} ¶ {name}")          # тело первым: цитаты берём из текста, а не из заголовка
    t = src.lower()                               # правила — по нижнему регистру, цитаты — из src
    excl_spans = [m.span() for m in EXCLUSION.finditer(t)]

    hits: list[Hit] = []
    taken: list[tuple[int, int]] = []           # чтобы АУСН не посчиталась ещё и как УСН
    for r in RULES:
        for m in re.finditer(r.pattern, t):
            if any(a <= m.start() < b for a, b in taken) and r.field == "tax_regimes":
                continue
            if r.field == "tax_regimes":
                taken.append(m.span())
            ex = any(a <= m.start() < b for a, b in excl_spans)
            hits.append(Hit(r.field, r.values, r.label, _quote(src, *m.span()), ex, r.action))
            break                                 # одной цитаты на правило достаточно
    # Явные коды ОКВЭД рядом со словом «ОКВЭД»/«классификатор»
    main_only = False
    for m in re.finditer(r"оквэд|классификатор\w* видов экономической деятельности", t):
        window = t[max(0, m.start() - 300): m.end() + 300]
        codes = tuple(dict.fromkeys(OKVED_CODE.findall(window)))
        if codes:
            main_only |= bool(MAIN_ONLY.search(window))
            hits.append(Hit("okved_prefixes", codes, "коды ОКВЭД " + ", ".join(codes), _quote(src, *m.span(), width=150)))

    hits += nk_hits(t, src)

    # Оговорка «за исключением ИП, применяющих ПСН»: исключаем конкретное (ПСН), а не всех ИП
    ex_hits = [h for h in hits if h.excluded]
    if any(h.field != "legal_forms" for h in ex_hits):
        for h in ex_hits:
            if h.field == "legal_forms":
                h.excluded = False

    region = None
    if block == "subjects":
        region = next((code for stem, code in REGION_BY_AUTHORITY.items() if stem in authority.lower()), None)

    pos = [h for h in hits if not h.excluded]
    if any(h.label.startswith("коды ОКВЭД") for h in pos):   # явные коды точнее отраслевых слов
        pos = [h for h in pos if h.field != "okved_prefixes" or h.label.startswith("коды ОКВЭД")]
        hits = [h for h in hits if h in pos or h.excluded]   # и цитаты вытесненных правил не показываем
    get = lambda f: tuple(dict.fromkeys(v for h in pos if h.field == f for v in h.values))
    exclude_regimes = frozenset(v for h in hits if h.excluded and h.field == "tax_regimes" for v in h.values)
    aud = Audience(
        legal_forms=frozenset(get("legal_forms")) or None,
        tax_regimes=frozenset(get("tax_regimes")) or None,
        okved_prefixes=get("okved_prefixes") or None,
        okved_main_only=main_only,
        regions=frozenset({region}) if region else None,
        msp_categories=frozenset(get("msp_categories")) or None,
        has_employees=True if get("has_employees") else None,
        any_flags=get("flags"),
        exclude_tax_regimes=exclude_regimes or None,
    )
    about_business = any(h.field in ("legal_forms", "subject", "has_employees", "tax_regimes", "flags") for h in pos)
    if not about_business:
        return Classification(False, "адресат-бизнес в тексте не найден", hits)
    spec = sum(bool(getattr(aud, f, None) if f != "flags" else aud.any_flags) for f in NARROWING)
    eff = effective_dates(t, published)
    return Classification(True, "ok", hits, aud, eff, spec,
                          auto_publish=spec > 0 and bool(eff))  # иначе — в очередь модерации


OBLIGATION = re.compile(r"\b(?:обязан\w*|должн\w*|представля\w*|уплачива\w*|вправе|не допуска\w*|"
                        r"запрещ\w*|распространяется|имеют право|обеспечить)\b", re.I)


def key_provision(text: str, limit: int = 320) -> str:
    """Первое предложение с обязанностью/правом — дословно, без пересказа."""
    for sent in re.split(r"(?<=[.;»])\s+(?=[А-ЯA-Z«])", normalize(text)):
        if OBLIGATION.search(sent) and "вступает в силу" not in sent.lower():
            sent = re.sub(r"^(?:Статья \d+\.\s*)?«?(?:\d+\.\s*)?", "", sent).rstrip("»").strip()
            return sent if len(sent) <= limit else sent[:limit].rsplit(" ", 1)[0] + "…"
    return ""


def to_feed_item(meta: dict, c: Classification, published: date, text: str = "") -> FeedItem:
    """meta — запись из /api/Documents (eoNumber, name, complexName)."""
    today_or_later = [d for d in c.effective if d >= published] or c.effective
    actions = tuple(dict.fromkeys(h.action for h in c.hits if h.action and not h.excluded))
    return FeedItem(
        id=f"pravo-{meta['eoNumber']}",
        kind="law" if c.specificity else "general",
        title=(meta.get("name") or "")[:200],
        summary=(f"«{key_provision(text)}»\n" if key_provision(text) else "") + f"Опубликован {published:%d.%m.%Y}." + (
            " Отдельные положения вступают позже: " + ", ".join(f"{d:%d.%m.%Y}" for d in today_or_later[1:]) + "."
            if len(today_or_later) > 1 else ""),
        actions=actions + ("Прочитайте полный текст акта по ссылке ниже.",),
        act=(meta.get("complexName") or "").split("\n")[0],
        source_url=f"http://publication.pravo.gov.ru/document/{meta['eoNumber']}",  # проверено 27.09.2026
        official_url=f"http://publication.pravo.gov.ru/document/{meta['eoNumber']}",
        effective_from=today_or_later[0] if today_or_later else None,
        audience=c.audience,
        status="approved" if c.auto_publish else "pending_review",
        evidence=tuple({"field": h.field, "values": h.values, "label": h.label, "quote": h.quote}
                       for h in c.hits if not h.excluded),
    )
