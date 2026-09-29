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

POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 30.0

STATE_SECTION = "Сведения о состоянии"
DISQUALIFICATION_SECTION = (
    "Сведения о дисквалификации лица, имеющего право без доверенности "
    "действовать от имени юридического лица"
)


class CaptchaRequiredError(RuntimeError):
    pass


class EgrulTimeoutError(RuntimeError):
    pass


@dataclass
class EgrulSearchRecord:
    full_name: str
    short_name: str | None
    address: str | None
    ogrn: str | None
    ogrn_date: str | None
    inn: str
    kpp: str | None
    liquidation_date: str | None
    invalidation_date: str | None
    entity_type: str | None
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
    session = requests.Session()
    token = _search_token(session, query, region)
    rows = _search_rows(session, token)
    return [EgrulSearchRecord.from_api(row) for row in rows if row.get("i")]


def  fetch_by_inn(inn: str) -> EgrulSearchRecord | None:
    results = search(inn)
    return next((r for r in results if r.inn == inn), None)


@dataclass
class Person:
    surname: str | None = None
    name: str | None = None
    patronymic: str | None = None
    full_name: str | None = None
    inn: str | None = None
    ogrn: str | None = None
    position: str | None = None
    gender: str | None = None
    citizenship: str | None = None
    share_value_rub: int | None = None
    share_percent: float | None = None


@dataclass
class OkvedCode:
    code: str
    name: str


@dataclass
class Note:
    section: str
    text: str
    date: str | None = None


@dataclass
class EgrulExtract:
    full_name: str | None = None
    short_name: str | None = None
    location: str | None = None
    address: str | None = None
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
    notes: list[Note] = field(default_factory=list)
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
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    extract = EgrulExtract()
    section = ""
    current_founder: Person | None = None

    for row in _table_rows(doc):
        num, label, value = row
        if label is None and value is None:
            if num:
                section = _clean(num) or ""
            continue
        if not num and value in (None, "") and label:
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
    pdf_bytes = download_extract_pdf(inn)
    return parse_extract_pdf(pdf_bytes) if pdf_bytes is not None else None


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(fetch_by_inn(arg))
        print(get_extract(arg))
