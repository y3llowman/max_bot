"""Единый реестр контрольных (надзорных) мероприятий (proverki.gov.ru) — проверки по ИНН.

Поиск на портале закрыт капчей, но открытые данные отдаются без неё. Эндпоинты взяты
из JS портала и проверены вживую 27.09.2026:

    GET https://proverki.gov.ru/public/api/opendata/<год>/<месяц>?isFederalLaw248=true
        → JSON-паспорт набора, в нём dataZipUrl — архив с одним XML
          (мероприятия с датой начала в этом месяце; обновляется ежедневно,
          ~3,5 МБ zip / 35 МБ XML / ~5 тыс. мероприятий на месяц).
        Нет набора за месяц — 500 «files not found».

XML: <INSPECTION CLASSIFICATION="КНМ|ПМ" STATUS_KEY=… ERPID=… START_DATE=… STOP_DATE=…>
с дочерними KIND_CONTROL, KIND_KNM, KNO_ORGANIZATION (@VALUE), SUBJECT (@INN)
и WARNING_INFO/CAPTION у предостережений. У физлиц ИНН замаскирован звёздочками.
"""
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

import requests

API = "https://proverki.gov.ru/public/api/opendata"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}


@dataclass
class Knm:
    erpid: str             # учётный номер мероприятия в ЕРКНМ
    inn: str
    classification: str    # «КНМ» — контрольное мероприятие, «ПМ» — профилактическое
    status: str            # «Ожидает проведения», «Предостережение объявлено», «Отменено»…
    status_key: str        # TYPE_WAITING_CARRY_OUT, REMARK…
    kind: str | None       # «Выездная проверка», «Профилактический визит»…
    control: str | None    # вид контроля: «Федеральный государственный пожарный надзор»…
    authority: str | None  # контрольный орган
    type_name: str | None  # «Плановое КНМ» / «Внеплановое КНМ»; у ПМ нет
    start: str | None      # YYYY-MM-DD
    stop: str | None
    warning: str | None    # текст предостережения


def month_zip_url(year: int, month: int) -> str | None:
    resp = requests.get(f"{API}/{year}/{month}", params={"isFederalLaw248": "true"}, headers=HEADERS, timeout=30)
    if resp.status_code == 500 and "not found" in resp.text:
        return None
    resp.raise_for_status()
    return resp.json().get("dataZipUrl")


def _value(el: ET.Element, tag: str) -> str | None:
    child = el.find(f"{{*}}{tag}")
    return child.get("VALUE") if child is not None else None


def parse(xml_stream, inns: set[str]) -> list[Knm]:
    """Мероприятия по нужным ИНН. iterparse с очисткой элементов — XML на десятки мегабайт."""
    found = []
    for _, el in ET.iterparse(xml_stream, events=("end",)):
        if el.tag.rsplit("}", 1)[-1] != "INSPECTION":
            continue
        subject = el.find("{*}SUBJECT")
        inn = subject.get("INN") if subject is not None else None
        if inn in inns:
            caption = el.find("{*}WARNING_INFO/{*}CAPTION")
            found.append(Knm(
                erpid=el.get("ERPID"), inn=inn, classification=el.get("CLASSIFICATION"),
                status=el.get("STATUS"), status_key=el.get("STATUS_KEY"),
                kind=_value(el, "KIND_KNM"), control=_value(el, "KIND_CONTROL"),
                authority=_value(el, "KNO_ORGANIZATION"), type_name=el.get("TYPE_NAME"),
                start=el.get("START_DATE"), stop=el.get("STOP_DATE"),
                warning=" ".join(caption.text.split()) if caption is not None and caption.text else None,
            ))
        el.clear()
    return found


def fetch_month(year: int, month: int, inns: set[str]) -> list[Knm]:
    url = month_zip_url(year, month)
    if url is None:
        return []
    resp = requests.get(url, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    with archive.open(archive.infolist()[0]) as xml_stream:
        return parse(xml_stream, inns)


def months_around(today: date) -> list[tuple[int, int]]:
    """Прошлый месяц (предостережения и недавние мероприятия), текущий и два следующих."""
    index = today.year * 12 + today.month - 1
    return [((i // 12), i % 12 + 1) for i in range(index - 1, index + 3)]


if __name__ == "__main__":
    import sys

    for year, month in months_around(date.today()):
        print(year, month, fetch_month(year, month, set(sys.argv[1:])))
