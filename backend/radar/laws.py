from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from radar.deadlines import REGIME_RU, REGIONS, Profile
from radar.detectors import Draft, add_months
from radar.obligations import BY_CODE, OBLIGATIONS
from radar.obligations import quota as quota_applies


def norm(text: str | None) -> str:
    t = " ".join((text or "").replace("ё", "е").replace("Ё", "Е").split()).lower()
    return re.sub(r"автоматизированн\w* упрощенн\w*(?: систем\w* налогообложени\w*)?", "аусн", t)


NOT_BUSINESS = re.compile(
    r"государственн\w* (?:гражданск\w* )?служб|гражданск\w* служащ|муниципальн\w* служб|должност\w* федеральн|"
    r"замещ\w* (?:отдельн\w* )?должност|претендующ|создаваем\w* для выполнения задач|перечн\w* должност|"
    r"сведени\w* о (?:своих )?доходах|территориальн\w* орган|подведомственн|казенн\w* учрежден|"
    r"бюджетн\w* учрежден|административн\w* регламент|положени\w* о (?:министерств|федеральн\w* (?:служб|агентств)|департамент|комитет|управлени)|"
    r"о награждении|о присвоении|о назначении|об освобождении|почетн\w* грамот|о поощрении|благодарност|"
    r"\bбюджет\w* (?:на \d{4}|субъект|российской федерации|фонда|территориальн)|об исполнении бюджета|"
    r"межбюджетн|ратификаци|о подписании|международн\w* договор|соглашени\w* между|о составе|о структуре|"
    r"в состав|служебн\w* (?:информаци|поведени)|форменн\w* одежд|квалификационн\w* требовани|"
    r"аттестационн\w* комисси|профессиональн\w* стандарт|образовательн\w* программ|спорт|"
    r"объект\w* культурного наследия|военн|воинск|уголовно-исполнительн|судебн\w* пристав|судей|"
    r"избирательн|депутат|ветеран|юбилейн|медицинск\w* помощ|донорск|"
    r"оплат\w* труда работников (?:федеральн|государственн|муниципальн)|"
    r"о межведомственн|о комиссии|о совете\b|о рабочей группе|классн\w* чин")

AMENDMENT = re.compile(r"^\W*(?:о внесении изменени|о признании утратившим|о приостановлении|об изменении)")

MONTHS = {m: i for i, m in enumerate(("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
                                      "сентября", "октября", "ноября", "декабря"), start=1)}
ACT_REF = re.compile(r"(постановлени|приказ)\w*[^«\"]{0,160}? от (?:(\d{1,2}) (" + "|".join(MONTHS)
                     + r") (\d{4}) г\.?|(\d{2})\.(\d{2})\.(\d{4})) № ([\w\-/]+)")


def act_refs(name: str) -> list[tuple[str, str, date]]:
    out = []
    for kind, d, m, y, d2, m2, y2, number in ACT_REF.findall(norm(name)):
        signed = date(int(y), MONTHS[m], int(d)) if d else date(int(y2), int(m2), int(d2))
        out.append(("government" if kind == "постановлени" else "federal_authorities", number, signed))
    return out


def needs_more(name: str) -> bool:
    t = norm(name)
    return bool(AMENDMENT.search(t)) and (not re.search(r"[«\"]", t) or bool(NK.search(t) or KOAP.search(t)))


@dataclass(frozen=True)
class Flag:
    question: str
    reason: str
    label: str


FLAGS = {
    "cash_register": Flag("Вы принимаете оплату через кассу (ККТ)?", "вы принимаете оплату через кассу",
                          "Принимаем оплату через кассу (ККТ)"),
    "marked_goods": Flag("Вы продаёте или производите товары с обязательной маркировкой "
                         "(одежда, обувь, молочная продукция, вода, пиво и другие)?",
                         "вы работаете с маркированными товарами", "Продаём или производим маркированные товары"),
    "marketplace_seller": Flag("Вы продаёте через маркетплейсы (Wildberries, Ozon и другие)?",
                               "вы продаёте через маркетплейсы", "Продаём через маркетплейсы"),
    "works_with_selfemployed": Flag("Вы работаете с самозанятыми?", "вы работаете с самозанятыми",
                                    "Работаем с самозанятыми"),
    "gov_procurement": Flag("Вы участвуете в госзакупках (44-ФЗ или 223-ФЗ)?", "вы участвуете в госзакупках",
                            "Участвуем в госзакупках"),
    "foreign_workers": Flag("У вас работают иностранные граждане?", "у вас работают иностранцы",
                            "Есть работники-иностранцы"),
}


@dataclass(frozen=True)
class Topic:
    code: str
    pattern: str | None
    applies: Callable[[Profile], str | None]
    action: str
    flag: str | None = None
    obligations: tuple[str, ...] = ()


def regime(*regimes: str) -> Callable[[Profile], str | None]:
    return lambda p: f"вы на {REGIME_RU[p.tax_regime]}" if p.tax_regime in regimes else None


def okved(label: str, *prefixes: str) -> Callable[[Profile], str | None]:
    def applies(p: Profile) -> str | None:
        if p.okved_main and p.okved_main.startswith(prefixes):
            return f"ваш основной вид деятельности — {label} (ОКВЭД {p.okved_main})"
        return None
    return applies


def everyone(p: Profile) -> str | None:
    return "общие правила для всех организаций и ИП"


def vat(p: Profile) -> str | None:
    if p.tax_regime == "osno":
        return "вы на ОСНО и платите НДС"
    if p.tax_regime in ("usn_income", "usn_ie"):
        return "вы на УСН, а с 2025 года упрощенцы — плательщики НДС (до порога дохода — с освобождением)"
    return None


def ndfl(p: Profile) -> str | None:
    if p.has_employees:
        return "у вас есть сотрудники — вы налоговый агент по НДФЛ"
    if not p.is_legal_entity and p.tax_regime == "osno":
        return "вы ИП на ОСНО и платите НДФЛ"
    return None


def insurance(p: Profile) -> str | None:
    if p.has_employees:
        return "у вас есть сотрудники — вы платите за них страховые взносы и сдаёте отчёты в ФНС и Соцфонд"
    if not p.is_legal_entity and p.tax_regime != "ausn":
        return "вы ИП и платите страховые взносы «за себя»"
    return None


def employer(p: Profile) -> str | None:
    return "у вас есть сотрудники" if p.has_employees else None


def legal_entity(p: Profile) -> str | None:
    return "вы организация — ведёте бухгалтерский учёт" if p.is_legal_entity else None


B2C = ("45.2", "47", "49.3", "55", "56", "79", "86", "93", "95", "96")

TOPICS: tuple[Topic, ...] = (
    Topic("usn", r"упрощенн\w* систем\w* налогообложени", regime("usn_income", "usn_ie"),
          "Проверьте, меняются ли для вас ставка, лимиты или сроки по УСН.", obligations=("usn_decl", "usn_notice", "usn_pay")),
    Topic("ausn", r"\bаусн\b", regime("ausn"), "Проверьте, меняются ли для вас условия АУСН."),
    Topic("psn", r"патентн\w* систем\w* налогообложени", regime("psn"),
          "Проверьте, меняются ли виды деятельности, стоимость или сроки оплаты патента."),
    Topic("vat", r"налог\w* на добавленную стоимость", vat,
          "Проверьте, как изменение отразится на ставке, освобождении и декларации по НДС.", obligations=("vat_decl",)),
    Topic("profit", r"налог\w* на прибыль организаций",
          lambda p: "вы организация на ОСНО и платите налог на прибыль" if p.is_legal_entity and p.tax_regime == "osno" else None,
          "Проверьте расчёт налога на прибыль и авансов.", obligations=("profit_decl",)),
    Topic("ndfl", r"налог\w* на доходы физических лиц|\b6-ндфл", ndfl,
          "Проверьте, как изменение отразится на удержании НДФЛ и отчётности.", obligations=("ndfl6", "ndfl_notice", "ip_3ndfl")),
    Topic("insurance", r"страхов\w* взнос|обязательн\w* (?:социальн|пенсионн)\w* страховани|персонифицированн\w* учет|"
                       r"единой формы сведений", insurance,
          "Проверьте тарифы взносов и формы отчётов за сотрудников.",
          obligations=("rsv", "psfl", "efs1", "ndfl_notice", "enp", "ip_contrib")),
    Topic("labor", r"трудов\w* кодекс|охран\w* труда|специальн\w* оценк\w* условий труда|трудов\w* книжк|"
                   r"минимальн\w* размер\w* оплаты труда|кадров\w* электронн\w* документооборот", employer,
          "Проверьте трудовые договоры, локальные акты и кадровые документы."),
    Topic("quota", r"квот\w*[^.;]{0,60}инвалид|инвалид[^.;]{0,60}квот", quota_applies,
          "Проверьте размер квоты и отчёт о её выполнении.", obligations=("quota",)),
    Topic("accounting", r"бухгалтерск\w* (?:учет|\(финансов\w*\) отчетност|отчетност)", legal_entity,
          "Проверьте учётную политику и формы бухгалтерской отчётности.", obligations=("buh",)),
    Topic("general", r"государственн\w* регистрац\w* юридических лиц и индивидуальных предпринимателей|"
                     r"о развитии малого и среднего предпринимательства|об электронной подписи|о персональных данных|"
                     r"о государственном контроле \(надзоре\) и муниципальном контроле", everyone,
          "Проверьте, меняются ли для вас порядок, сроки или ответственность."),
    Topic("kkt", r"контрольно-кассов\w* техник", lambda p: None,
          "Проверьте, нужно ли обновить кассу, фискальный накопитель или порядок расчётов.", flag="cash_register"),
    Topic("marking", r"маркировк\w*|средствами идентификации", lambda p: None,
          "Проверьте, попадают ли ваши товары под новые требования и сроки маркировки.", flag="marked_goods"),
    Topic("marketplace", r"платформенн\w* экономик|посредническ\w* цифров\w* платформ|маркетплейс",
          okved("торговля через интернет", "47.91"),
          "Проверьте договор с площадкой и новые требования к продавцам.", flag="marketplace_seller"),
    Topic("selfemployed", r"налог\w* на профессиональн\w* доход|самозанят", lambda p: None,
          "Проверьте договоры с самозанятыми и чеки от них.", flag="works_with_selfemployed"),
    Topic("procurement", r"контрактн\w* систем\w* в сфере закупок|закупках товаров, работ, услуг отдельными видами",
          lambda p: None, "Проверьте условия текущих контрактов и заявок.", flag="gov_procurement"),
    Topic("foreign", r"правовом положении иностранных граждан|иностранн\w* работник|трудов\w* мигрант",
          lambda p: None, "Проверьте документы и уведомления по работникам-иностранцам.", flag="foreign_workers"),
    Topic("alcohol", r"алкогольн\w* продукц|этилового спирта|\bпив\w*|винодел",
          okved("производство или продажа алкоголя", "11.0", "46.34", "47.11", "47.25", "56.3"),
          "Проверьте лицензию, ЕГАИС и ограничения продажи."),
    Topic("tobacco", r"табачн\w*|никотинсодержащ|доставки никотина",
          okved("табак и никотинсодержащая продукция", "12", "46.35", "47.11", "47.26"),
          "Проверьте ограничения продажи и требования к точкам."),
    Topic("licenses", r"о лицензировании отдельных видов деятельности",
          lambda p: "у вас есть лицензии (реестр МСП)" if p.has_licenses else None,
          "Проверьте, меняются ли лицензионные требования для вашей деятельности."),
    Topic("retail", r"розничн\w* торговл|(?<!внешне)торговой деятельности|нестационарн\w* торгов|торгов\w* сбор",
          okved("торговля", "46", "47"), "Проверьте требования к торговле и точкам продаж."),
    Topic("catering", r"общественн\w* питани", okved("общепит", "56"), "Проверьте требования к заведению."),
    Topic("hotels", r"гостиничн\w* (?:услуг|деятельност)|средств\w* размещени|туристическ\w* налог|туристск\w* налог",
          okved("гостиницы и средства размещения", "55"), "Проверьте требования к средству размещения и туристический налог."),
    Topic("passengers", r"легков\w* такси|перевозок пассажиров и багажа",
          okved("перевозка пассажиров", "49.3"), "Проверьте требования к перевозкам и водителям."),
    Topic("cargo", r"перевозк\w* груз|тяжеловесн|крупногабаритн",
          okved("грузоперевозки", "49.4"), "Проверьте требования к перевозкам и транспорту."),
    Topic("tourism", r"туроператор|турагент|туристск\w* деятельност|туристск\w* продукт",
          okved("туризм", "79"), "Проверьте требования к турпродукту и реестру."),
    Topic("pharma", r"лекарственн\w* (?:средств|препарат)|аптечн|фармацевтическ",
          okved("лекарства", "21", "46.46", "47.73"), "Проверьте лицензию и требования к обороту лекарств."),
    Topic("consumers", r"защите прав потребителей", okved("работа с потребителями", *B2C),
          "Проверьте договоры, чеки и информацию для покупателей."),
)
BY_TOPIC = {t.code: t for t in TOPICS}
TOPIC_RU = {
    "usn": "УСН", "ausn": "АУСН", "psn": "патент", "vat": "НДС", "profit": "налог на прибыль", "ndfl": "НДФЛ",
    "insurance": "страховые взносы", "labor": "трудовое право", "quota": "квота для инвалидов",
    "accounting": "бухучёт", "general": "для всех", "kkt": "касса", "marking": "маркировка",
    "marketplace": "маркетплейсы", "selfemployed": "самозанятые", "procurement": "госзакупки",
    "foreign": "иностранные работники", "alcohol": "алкоголь", "tobacco": "табак", "licenses": "лицензии",
    "retail": "торговля", "catering": "общепит", "hotels": "гостиницы", "passengers": "пассажиры",
    "cargo": "грузоперевозки", "tourism": "туризм", "pharma": "лекарства", "consumers": "потребители",
}

NK_ARTICLES = (
    ((11, 3), (11, 3), "general"), ((23, 0), (24, 99), "general"), ((45, 0), (48, 99), "general"),
    ((52, 0), (58, 99), "general"), ((69, 0), (71, 99), "general"), ((75, 0), (81, 99), "general"),
    ((88, 0), (101, 99), "general"), ((119, 0), (129, 99), "general"),
    ((143, 0), (178, 99), "vat"),
    ((227, 1), (227, 1), "foreign"),
    ((207, 0), (233, 99), "ndfl"),
    ((246, 0), (333, 0), "profit"),
    ((346, 11), (346, 25), "usn"),
    ((346, 43), (346, 53), "psn"),
    ((410, 0), (418, 99), "retail"),
    ((419, 0), (432, 99), "insurance"),
)
KOAP_ARTICLES = {
    (5, 27): "labor", (14, 5): "kkt", (14, 15): "retail", (14, 16): "alcohol", (14, 17): "alcohol",
    (14, 46): "marking", (14, 53): "tobacco", (14, 69): "marketplace", (14, 70): "marketplace",
    (14, 71): "marketplace", (15, 5): "general", (15, 6): "general", (15, 11): "general",
    (15, 33): "insurance", (18, 15): "foreign", (18, 16): "foreign", (18, 17): "foreign",
}

ARTICLES = re.compile(r"стать\w*\s+((?:\d{1,3}(?:[.\-]\d{1,3})*(?:\s\d{1,2}(?=[\s,;:.)]|$))?(?:\s*(?:,|и|-|–)\s*)?)+)")
ARTICLE = re.compile(r"(\d{1,3})(?:[.\-](\d{1,3})|\s(\d{1,2})(?=[\s,;:.)]|$))?")
OTHER_ACT = re.compile(r"\s*(?:федеральн\w* закон|закон|указ|постановлени|приказ|кодекс\w* российской федерации об|"
                       r"трудов\w* кодекс|гражданск\w* кодекс|бюджетн\w* кодекс)")


def article_refs(fragment: str) -> list[tuple[int, int]]:
    out = []
    for m in ARTICLES.finditer(fragment):
        if OTHER_ACT.match(fragment, m.end()):
            continue
        for main, sub_dot, sub_space in ARTICLE.findall(m.group(1)):
            out.append((int(main), int(sub_dot or sub_space or 0)))
    return out


def nk_topics(refs: list[tuple[int, int]]) -> set[str]:
    return {next((code for lo, hi, code in NK_ARTICLES if lo <= ref <= hi), None) for ref in refs} - {None}


def koap_topics(refs: list[tuple[int, int]]) -> set[str]:
    return {KOAP_ARTICLES[ref] for ref in refs if ref in KOAP_ARTICLES}


NK = re.compile(r"налогов\w* кодекс")
KOAP = re.compile(r"кодекс\w* российской федерации об административных правонарушениях")


def topics_in(name: str) -> set[str]:
    t = norm(name)
    if NOT_BUSINESS.search(t):
        return set()
    found = {topic.code for topic in TOPICS if topic.pattern and re.search(topic.pattern, t)}
    if NK.search(t):
        found |= nk_topics(article_refs(t))
    if KOAP.search(t):
        found |= koap_topics(article_refs(t))
    return found


HEADER_LINE = re.compile(r"^(?:\d+\.\s*)?(?:внести в|в [^\n\"«]{0,300}(?:закон|кодекс|постановлени|приказ)|"
                         r"утвердить прилагаемые изменения|изменения, которые вносятся)")
QUOTED_ACT = re.compile(r"№\s?[\w\-/]+\s*[\"«]([^\"«»\n]{8,400}?)[\"»]")
LAW_ARTICLE = re.compile(r"^статья \d+(?:\s*\d+)?\.?$", re.M)


@dataclass
class TextFacts:
    amended: list[str] = field(default_factory=list)
    topics: set[str] = field(default_factory=set)


def text_facts(text: str) -> TextFacts:
    facts = TextFacts()
    lines = [(norm(raw), " ".join(raw.split())) for raw in text.splitlines()]
    for line, original in lines:
        if not HEADER_LINE.match(line):
            continue
        facts.topics |= topics_in(re.split(r"[\"«]", line)[0])
        for name in QUOTED_ACT.findall(original):
            facts.topics |= topics_in(name)
            if name not in facts.amended and not NOT_BUSINESS.search(norm(name)):
                facts.amended.append(name)
    t = "\n".join(line for line, _ in lines)
    parts = LAW_ARTICLE.split(t)
    for part in parts[1:] if len(parts) > 1 else parts:
        head = re.split(r"[\"«]", part.strip()[:400])[0]
        if not re.match(r"(?:внести|в )", head):
            continue
        if NK.search(head):
            facts.topics |= nk_topics(article_refs(part))
        elif KOAP.search(head):
            facts.topics |= koap_topics(article_refs(part))
    return facts


WORD_NUM = {"одного": 1, "двух": 2, "трех": 3, "четырех": 4, "пяти": 5, "шести": 6, "семи": 7, "десяти": 10,
            "четырнадцати": 14, "тридцати": 30, "шестидесяти": 60, "девяноста": 90, "ста восьмидесяти": 180}
IN_FORCE = re.compile(r"настоящ\w* (?:федеральн\w* закон\w*|закон\w*|постановлени\w*|приказ\w*)[^.]{0,120}?"
                      r"вступа\w* в силу[^.]{0,200}")
EXACT = re.compile(r"с (\d{1,2}) (" + "|".join(MONTHS) + r") (\d{4})")
AFTER = re.compile(r"по истечении (\d+|" + "|".join(WORD_NUM) + r") (дн\w*|месяц\w*) после дня (?:его |ее |их )?официального")


def effective_dates(text: str, published: date) -> list[date]:
    out: list[date] = []
    for phrase in IN_FORCE.findall(norm(text)):
        found = [date(int(y), MONTHS[m], int(d)) for d, m, y in EXACT.findall(phrase)]
        if "со дня его официального опубликования" in phrase or "со дня официального опубликования" in phrase:
            found.append(published)
        for n, unit in AFTER.findall(phrase):
            n = int(n) if n.isdigit() else WORD_NUM[n]
            found.append(published + timedelta(days=n + 1) if unit.startswith("дн") else add_months(published, n) + timedelta(days=1))
        out += [d for d in found if d not in out]
    return out


_SKIP_WORDS = {"республика", "область", "край", "автономный", "автономная", "округ", "народная", "—", "-"}
_REGION_OVERRIDES = {"11": r"\bкоми\b", "12": r"\bмарий эл\b", "14": r"\bсаха\b", "17": r"\bтыв[аы]\b",
                     "77": r"\bмоскв[аы]\b", "83": r"(?<!ямало-)\bненецк", "91": r"\bкрым\b"}


def _region_pattern(code: str, name: str) -> str:
    if code in _REGION_OVERRIDES:
        return _REGION_OVERRIDES[code]
    word = next(w for w in name.lower().replace("(", " ").split() if w not in _SKIP_WORDS)
    stem = word[:-2] if word.endswith(("ая", "ий", "ой", "ый")) else word.rstrip("аяоеиыь")
    return r"\b" + re.escape(stem)


REGION_PATTERNS = sorted(((code, re.compile(_region_pattern(code, name))) for code, name in REGIONS.items()),
                         key=lambda item: -len(item[1].pattern))


def region_of(header: str) -> str | None:
    authority = norm(header).split(" от ")[0]
    return next((code for code, rx in REGION_PATTERNS if rx.search(authority)), None)


@dataclass
class Law:
    eo_number: str
    header: str
    name: str
    published: date
    topics: list[str]
    region: str | None = None
    amended: list[str] = field(default_factory=list)
    effective: list[date] = field(default_factory=list)
    pages: int | None = None
    pdf_size: int | None = None


def split_meta(meta: dict) -> tuple[str, str]:
    header, _, rest = (meta.get("complexName") or "").partition("\n")
    name = " ".join((meta.get("name") or rest).split()).strip().strip('"«»').strip()
    return " ".join(header.split()), name


def classify(meta: dict, resolved: list[str], text: str | None, final: bool = False) -> Law | None:
    header, name = split_meta(meta)
    published = datetime.fromisoformat(meta["publishDateShort"]).date()
    law = Law(meta["eoNumber"], header, name, published, [], pages=meta.get("pagesCount"),
              pdf_size=meta.get("pdfFileLength"))
    if NOT_BUSINESS.search(norm(name)):
        return law
    topics = topics_in(name)
    law.amended = list(resolved)
    for amended in resolved:
        topics |= topics_in(amended)
    if text:
        facts = text_facts(text)
        topics |= facts.topics
        law.amended += [a for a in facts.amended if a not in law.amended]
        law.effective = effective_dates(text, published)
    elif not topics and needs_more(name) and not resolved and not final:
        return None
    law.topics = [t.code for t in TOPICS if t.code in topics]
    if meta.get("block") == "subjects":
        law.region = region_of(header)
        if law.region is None:
            law.topics = []
    return law


def drafts(law: Law, p: Profile, today: date) -> list[Draft]:
    if not law.topics or (law.region and law.region != (p.region_code or "").zfill(2)):
        return []
    reasons, actions, touched, unknown = [], [], [], []
    applicable = {o.code for o in OBLIGATIONS if o.applies(p)}
    for topic in (BY_TOPIC[code] for code in law.topics):
        why = topic.applies(p) or (FLAGS[topic.flag].reason if topic.flag and p.flags.get(topic.flag) else None)
        if why is None:
            if topic.flag and p.flags.get(topic.flag) is None:
                unknown.append(topic.flag)
            continue
        reasons.append(why)
        actions.append(topic.action)
        touched += [BY_CODE[code].title for code in topic.obligations if code in applicable]
    if not reasons:
        return [Draft("profile.question", f"q:{p.inn}:{flag}",
                      {"flag": flag, "question": FLAGS[flag].question, "act": law.header, "because": law.name})
                for flag in dict.fromkeys(unknown)]
    effective = law.effective[0] if law.effective else None
    payload = {
        "eo": law.eo_number, "act": law.header, "title": law.name, "period": law.header,
        "published": law.published.isoformat(), "amended": law.amended[:5],
        "effective_from": effective.isoformat() if effective else None,
        "effective_other": [d.isoformat() for d in law.effective[1:]],
        "reasons": list(dict.fromkeys(reasons)), "obligations": list(dict.fromkeys(touched)),
        "actions": ["Прочитайте официальный текст акта на pravo.gov.ru: ссылка — под сообщением в чате и в разделе «Правовое обоснование».", *dict.fromkeys(actions)],
        "summary": [f"Изменяет: {a}" for a in law.amended[:5]] or [law.name],
        "source_url": f"http://publication.pravo.gov.ru/document/{law.eo_number}",
        "basis_url": f"http://publication.pravo.gov.ru/document/{law.eo_number}",
        "pages": law.pages, "pdf_size": law.pdf_size,
    }
    return [Draft("law.upcoming", f"law:{law.eo_number}:{p.inn}", payload,
                  due=effective if effective and effective > today else None)]
