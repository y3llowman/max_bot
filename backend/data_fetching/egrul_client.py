"""Client for the Unified State Register of Legal Entities (egrul.nalog.ru).

egrul.nalog.ru has no free structured (JSON/XML) API for full company data.
The only two free ways to get data out of it are:

1. The search step of its own UI, reverse-engineered below (search() /
   fetch_by_inn()). It already returns a decent chunk of structured JSON -
   full/short name, address, OGRN(+date), INN, KPP, director post+name,
   liquidation/invalidation dates - with no PDF involved at all. Good enough
   for a quick "does this company exist / is it alive" check.
2. The official "выписка" PDF (download_extract_pdf() / get_extract()),
   which is the only free source for OKVED codes, founders/participants,
   capital and a few other fields. It has to be parsed (parse_extract_pdf(),
   using PyMuPDF's table extraction) since nalog.ru does not offer it as
   structured data for free - a paid SMEV/API access exists (tens of
   thousands of rubles/year) but isn't worth it for this project.

The request flow below (POST / -> GET search-result/<token> -> GET
vyp-request/<token> -> GET vyp-status/<token> -> GET vyp-download/<token>)
is reverse-engineered from egrul.nalog.ru's own frontend JS, not documented
anywhere. No cookies/session token/captcha are required for a single
lookup done at a human pace, but the site starts requiring a captcha if
requests come in too fast or in bulk (see CaptchaRequiredError) - there is
no way around that short of solving the captcha, which is out of scope
here.
"""

from __future__ import annotations

import time
import asyncio
from dataclasses import dataclass, field

import pymupdf
import requests
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BASE_URL = "https://egrul.nalog.ru/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://egrul.nalog.ru/index.html",
}

# Pause between polling requests, and how long to keep polling before giving up.
POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 30.0

STATE_SECTION = "Сведения о состоянии"  # prefix of "Сведения о состоянии юридического лица"
DISQUALIFICATION_SECTION = (
    "Сведения о дисквалификации лица, имеющего право без доверенности "
    "действовать от имени юридического лица"
)


class CaptchaRequiredError(RuntimeError):
    """egrul.nalog.ru is asking for a captcha - back off and slow down."""


class EgrulTimeoutError(RuntimeError):
    """Search or PDF generation didn't finish within POLL_TIMEOUT_SECONDS."""


# --------------------------------------------------------------------------
# Quick structured metadata - no PDF needed.
# --------------------------------------------------------------------------


@dataclass
class EgrulSearchRecord:
    full_name: str  # "Полное наименование"
    short_name: str | None
    address: str | None
    ogrn: str | None
    ogrn_date: str | None  # "Дата присвоения ОГРН"
    inn: str
    kpp: str | None
    liquidation_date: str | None
    invalidation_date: str | None  # дата признания регистрации недействительной
    entity_type: str | None  # raw nalog.ru type code
    director_position: str | None
    director_name: str | None

    @classmethod
    def  from_api(cls, row: dict) -> "EgrulSearchRecord":
        position, _, name = (row.get("g") or "").partition(": ")
        return cls(
            full_name=row["n"],
            short_name=row.get("c"),
            address=row.get("a"),
            ogrn=row.get("o"),
            ogrn_date=row.get("r"),
            inn=row["i"],
            kpp=row.get("p"),
            liquidation_date=row.get("e"),
            invalidation_date=row.get("v"),
            entity_type=row.get("k"),
            director_position=position or None,
            director_name=name or None,
        )


def  _request_json(session: requests.Session, method: str, url: str, **kwargs) -> dict:
    resp = session.request(method, url, timeout=15, **kwargs)
    logger.info(f"Requesting {url}: {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()
    if data.get("captchaRequired") or data.get("ERRORS"):
        raise CaptchaRequiredError(f"egrul.nalog.ru requires a captcha for {url}")
    return data


def  _search_token(session: requests.Session, query: str, region: str = "", page: str = "") -> str:
    data = _request_json(
        session,
        "POST",
        BASE_URL,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        data={
            "vyp3CaptchaToken": "",
            "page": page,
            "query": query,
            "region": region,
            "PreventChromeAutocomplete": "",
        },
    )
    return data["t"]


def  _search_rows(session: requests.Session, token: str) -> list[dict]:
    url = f"{BASE_URL}search-result/{token}"
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        data = _request_json(
            session, "GET", url, headers=HEADERS, params={"r": int(time.time() * 1000)}
        )
        if data.get("status") != "wait":
            return data.get("rows", [])
        if time.monotonic() > deadline:
            raise EgrulTimeoutError("egrul.nalog.ru search did not finish in time")
        time.sleep(POLL_INTERVAL_SECONDS)


def  search(query: str, region: str = "") -> list[EgrulSearchRecord]:
    """Search egrul.nalog.ru by INN, OGRN or company name.

    Returns lightweight metadata straight from the search JSON - no PDF is
    downloaded. Use download_extract_pdf()/get_extract() for OKVED,
    founders/participants, capital and other fields that only exist in the
    full PDF извлечение.
    """
    session = requests.Session()
    token = _search_token(session, query, region)
    rows = _search_rows(session, token)
    return [EgrulSearchRecord.from_api(row) for row in rows if row.get("i")]


def  fetch_by_inn(inn: str) -> EgrulSearchRecord | None:
    """Look up a single organization by INN. Returns None if not found."""
    results = search(inn)
    return next((r for r in results if r.inn == inn), None)


# --------------------------------------------------------------------------
# Full "выписка" PDF: download + parse.
# --------------------------------------------------------------------------


@dataclass
class Person:
    surname: str | None = None
    name: str | None = None
    patronymic: str | None = None
    full_name: str | None = None  # set instead of surname/name/patronymic for a legal-entity founder
    inn: str | None = None
    ogrn: str | None = None  # legal-entity founders only
    position: str | None = None  # director/head only
    gender: str | None = None
    citizenship: str | None = None
    share_value_rub: int | None = None  # founders only
    share_percent: float | None = None  # founders only


@dataclass
class OkvedCode:
    code: str
    name: str


@dataclass
class Note:
    """A "Дополнительные сведения" row, e.g. "сведения недостоверны (...)"."""
    section: str  # the section it belongs to: address, director, founders...
    text: str
    date: str | None = None  # date of the ЕГРЮЛ entry (from the ГРН row right below)


@dataclass
class EgrulExtract:
    full_name: str | None = None
    short_name: str | None = None
    location: str | None = None  # "Место нахождения" (city/region only)
    address: str | None = None  # "Адрес юридического лица" (full postal address)
    email: str | None = None
    ogrn: str | None = None
    registration_date: str | None = None
    formation_method: str | None = None
    registering_authority_name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    tax_registration_date: str | None = None
    tax_authority_name: str | None = None
    sfr_registration_number: str | None = None
    sfr_registration_date: str | None = None
    sfr_authority_name: str | None = None
    director: Person | None = None
    director_disqualification_start: str | None = None
    director_disqualification_end: str | None = None
    director_disqualification_court_date: str | None = None
    capital_type: str | None = None
    capital_amount_rub: int | None = None
    founders: list[Person] = field(default_factory=list)
    okved_main: OkvedCode | None = None
    okved_additional: list[OkvedCode] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)  # any "Дополнительные сведения" rows, e.g. reliability flags
    # "Сведения о состоянии юридического лица": only present when the company is being
    # liquidated/reorganized or ФНС decided to strike it off, e.g. "Находится в стадии ликвидации"
    status: str | None = None
    status_date: str | None = None


def  _request_pdf_token(session: requests.Session, row_token: str) -> str:
    data = _request_json(
        session, "GET", f"{BASE_URL}vyp-request/{row_token}", headers=HEADERS, params={"r": ""}
    )
    return data["t"]


def  _wait_pdf_ready(session: requests.Session, token: str) -> None:
    url = f"{BASE_URL}vyp-status/{token}"
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        data = _request_json(
            session, "GET", url, headers=HEADERS, params={"r": int(time.time() * 1000)}
        )
        if data.get("status") == "ready":
            return
        if time.monotonic() > deadline:
            raise EgrulTimeoutError("egrul.nalog.ru PDF generation did not finish in time")
        time.sleep(POLL_INTERVAL_SECONDS)


def  _download_pdf(session: requests.Session, token: str) -> bytes:
    resp = session.get(f"{BASE_URL}vyp-download/{token}", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content


def  download_extract_pdf(inn: str) -> bytes | None:
    """Download the official ЕГРЮЛ extract PDF for a company by INN.

    Returns None if the INN is not found. Reproduces the request flow the
    egrul.nalog.ru search page itself makes to generate and download a
    "выписка" (search -> vyp-request -> vyp-status -> vyp-download).
    """
    session = requests.Session()
    token = _search_token(session, inn)
    rows = _search_rows(session, token)
    row = next((r for r in rows if r.get("i") == inn), None)
    if row is None:
        return None
    pdf_token = _request_pdf_token(session, row["t"])
    _wait_pdf_ready(session, pdf_token)
    return _download_pdf(session, pdf_token)


def  _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


def  _lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.split("\n") if line.strip()]


def  _to_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = value.replace(" ", "").replace("\xa0", "")
    return int(digits) if digits.isdigit() else None


def  _to_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(" ", "").replace("\xa0", "").replace(",", "."))
    except ValueError:
        return None


def  _table_rows(doc: pymupdf.Document):
    """Yields [number, label, value] rows from every 3-column table in the PDF.

    The two single-row "boxed digit" tables at the top of page 1 (ОГРН and
    ИНН spelled one digit per cell) have a different column count and are
    skipped - their values are picked up again, in normal form, from the
    "Сведения о регистрации" / "Сведения об учете в налоговом органе"
    sections further down.
    """
    for page in doc:
        for table in page.find_tables().tables:
            if table.col_count == 3:
                yield from table.extract()


def  _fill_person(person: Person, label: str, raw_value: str | None) -> None:
    if label == "Фамилия Имя Отчество":
        lines = _lines(raw_value)
        person.surname = lines[0] if len(lines) > 0 else None
        person.name = lines[1] if len(lines) > 1 else None
        person.patronymic = lines[2] if len(lines) > 2 else None
    elif label.startswith("Полное наименование"):
        person.full_name = _clean(raw_value)
    elif label == "ИНН":
        person.inn = _clean(raw_value)
    elif label == "ОГРН":
        person.ogrn = _clean(raw_value)
    elif label == "Должность":
        person.position = _clean(raw_value)
    elif label == "Пол":
        person.gender = _clean(raw_value)
    elif label == "Гражданство":
        person.citizenship = ", ".join(_lines(raw_value))
    elif label == "Номинальная стоимость доли (в рублях)":
        person.share_value_rub = _to_int(raw_value)
    elif label == "Размер доли (в процентах)":
        person.share_percent = _to_float(raw_value)


def  parse_extract_pdf(pdf_bytes: bytes) -> EgrulExtract:
    """Parse a ЕГРЮЛ extract PDF (as returned by download_extract_pdf) into
    structured data, using PyMuPDF's table extraction on the underlying
    "№ п/п | Наименование показателя | Значение показателя" table.

    Out of scope: the audit trail at the end of the document ("Сведения о
    записях, внесенных в ЕГРЮЛ" - the numbered history of registry entries
    and the documents submitted for each) is skipped entirely. It's an
    event log, not an entity attribute, and only one sample PDF was
    available to reverse-engineer this against, so its layout (variable
    number of entries, nested "Сведения о документах" sub-rows) wasn't
    worth guessing at. The company's current state (liquidation, upcoming
    strike-off) is read from "Сведения о состоянии юридического лица"
    instead (checked on a real extract of a company in liquidation; the
    section may have no ГРН row, then status_date stays None).

    Legal-entity founders (as opposed to individual people) are only
    best-effort supported (full_name/ogrn/inn on Person) since no real
    sample with one was available either.
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    extract = EgrulExtract()
    section = ""
    current_founder: Person | None = None

    for row in _table_rows(doc):
        num, label, value = row
        if label is None and value is None:
            # merged section-header row (spans all 3 columns)
            if num:
                section = _clean(num) or ""
            continue
        if not num and value in (None, "") and label:
            # "Сведения о дисквалификации..." is the one section header
            # that, unlike the others, lands in the label column instead
            # of the merged column.
            header = _clean(label)
            if header == DISQUALIFICATION_SECTION:
                section = header
            continue
        if not (num and num.strip().isdigit()):
            continue

        label_c = _clean(label) or ""
        value_c = _clean(value)

        if label_c == "Дополнительные сведения":
            if value_c:
                extract.notes.append(Note(section=section, text=value_c))
            continue
        if "ГРН и дата" in label_c:
            # the entry date matters for a note or a status: deadlines are counted from it
            entry_date = (_lines(value) or [None])[-1]
            last_note = extract.notes[-1] if extract.notes else None
            if last_note and last_note.section == section and last_note.date is None:
                last_note.date = entry_date
            elif section.startswith(STATE_SECTION) and extract.status_date is None:
                extract.status_date = entry_date
            continue
        if section == "Сведения о записях, внесенных в Единый государственный реестр юридических лиц":
            break

        if section == "Наименование":
            if label_c.startswith("Полное наименование"):
                extract.full_name = value_c
            elif label_c.startswith("Сокращенное наименование"):
                extract.short_name = value_c
        elif section.startswith(STATE_SECTION):
            if label_c == "Состояние":
                extract.status = value_c
        elif section == "Место нахождения и адрес юридического лица":
            if label_c == "Место нахождения юридического лица":
                extract.location = value_c
            elif label_c == "Адрес юридического лица":
                extract.address = " ".join(_lines(value))
        elif section == "Адрес электронной почты":
            if label_c == "E-mail":
                extract.email = value_c
        elif section == "Сведения о регистрации":
            if label_c == "Способ образования":
                extract.formation_method = value_c
            elif label_c == "ОГРН":
                extract.ogrn = value_c
            elif label_c == "Дата регистрации":
                extract.registration_date = value_c
        elif section == "Сведения о регистрирующем органе по месту нахождения юридического лица":
            if label_c == "Наименование регистрирующего органа":
                extract.registering_authority_name = value_c
        elif section == "Сведения о лице, имеющем право без доверенности действовать от имени юридического лица":
            if extract.director is None:
                extract.director = Person()
            _fill_person(extract.director, label_c, value)
        elif section == DISQUALIFICATION_SECTION:
            if label_c.startswith("Дата начала дисквалификации"):
                dates = _lines(value)
                extract.director_disqualification_start = dates[0] if len(dates) > 0 else None
                extract.director_disqualification_end = dates[1] if len(dates) > 1 else None
                extract.director_disqualification_court_date = dates[2] if len(dates) > 2 else None
        elif section == "Сведения об уставном капитале / складочном капитале / уставном фонде / паевом фонде":
            if label_c == "Вид":
                extract.capital_type = value_c
            elif label_c.startswith("Размер"):
                extract.capital_amount_rub = _to_int(value_c)
        elif section == "Сведения об участниках / учредителях юридического лица":
            if label_c == "Фамилия Имя Отчество" or label_c.startswith("Полное наименование"):
                current_founder = Person()
                extract.founders.append(current_founder)
            if current_founder is not None:
                _fill_person(current_founder, label_c, value)
        elif section == "Сведения об учете в налоговом органе":
            if label_c == "ИНН юридического лица":
                extract.inn = value_c
            elif label_c == "КПП юридического лица":
                extract.kpp = value_c
            elif label_c.startswith("Дата постановки на учет"):
                extract.tax_registration_date = value_c
            elif label_c.startswith("Сведения о налоговом органе"):
                extract.tax_authority_name = value_c
        elif section == (
            "Сведения о регистрации в качестве страхователя в территориальном органе "
            "Социального фонда России"
        ):
            if label_c == "Регистрационный номер страхователя":
                extract.sfr_registration_number = value_c
            elif label_c == "Дата постановки на учет":
                extract.sfr_registration_date = value_c
            elif label_c.startswith("Наименование территориального органа"):
                extract.sfr_authority_name = value_c
        elif section == "Сведения об основном виде деятельности":
            if label_c == "Код и наименование вида деятельности":
                code, _, name = value_c.partition(" ")
                extract.okved_main = OkvedCode(code=code, name=name)
        elif section == "Сведения о дополнительных видах деятельности":
            if label_c == "Код и наименование вида деятельности":
                code, _, name = value_c.partition(" ")
                extract.okved_additional.append(OkvedCode(code=code, name=name))

    return extract


def  get_extract(inn: str) -> EgrulExtract | None:
    """Download and parse the full ЕГРЮЛ extract for a company by INN.

    Returns None if the INN is not found.
    """
    pdf_bytes = download_extract_pdf(inn)
    return parse_extract_pdf(pdf_bytes) if pdf_bytes is not None else None


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(fetch_by_inn(arg))
        print(get_extract(arg))
