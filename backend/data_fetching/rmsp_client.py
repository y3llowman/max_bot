"""Client for the Unified SME Registry (rmsp.nalog.ru), lookup by INN.

rmsp.nalog.ru has no documented public API (the /developers.html page only
lists SMEV 3.X access for accredited government systems and bulk open-data
dumps). The site's own search page posts to an internal endpoint instead;
this replicates that request, reverse-engineered from search.js /
search-inn-list.js and confirmed against the live endpoint:

    POST https://rmsp.nalog.ru/search-proc.json
    Content-Type: application/x-www-form-urlencoded; charset=UTF-8
    body: mode=inn-list&page=1&pageSize=<n>&sortField=&innList=<comma-separated INNs>

No cookies, session, CSRF token, or captcha are required. Being undocumented,
it can change or start requiring a captcha at any time without notice.

Field mapping below is based on live response samples, not documentation.
Average headcount ("Среднесписочная численность работников", od2_sschr) is
only present for companies that reported it to ФНС: the key is missing both
for zero and for "no data", so a missing key means "unknown".
"""

from __future__ import annotations

from dataclasses import dataclass

import requests
import logging

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)


SEARCH_URL = "https://rmsp.nalog.ru/search-proc.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://rmsp.nalog.ru/search.html?mode=inn-list",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


@dataclass
class RmspRecord:
    name: str  # "Наименование / ФИО"
    subject_type: str  # "Тип субъекта": raw API code, "UL" or "IP"
    category: int  # "Категория": 1/2/3 = микро/малое/среднее, 0 = нет данных (обычно исключен из реестра)
    ogrn: str
    inn: str
    main_activity_code: str  # "Основной вид деятельности" (ОКВЭД, код)
    main_activity_name: str  # "Основной вид деятельности" (ОКВЭД, наименование)
    region_code: str  # "Регион": числовой код региона, не название
    is_new: bool  # "Вновь созданный"
    date_registered: str  # "Дата включения в реестр"
    date_excluded: str | None  # "Дата исключения из реестра"
    phone: str | None
    email: str | None
    website: str | None  # "WWW"
    employees_num: int | None  # "Среднесписочная численность работников" за прошлый год; None — нет данных
    has_licenses: bool  # "Наличие лицензий"
    is_hitech: bool  # "Производство инновационной, высокотехнологичной продукции"
    is_partnership: bool  # "Участие в программах партнерства"
    is_social: bool  # "Является социальным предприятием"

    @classmethod
    def from_api(cls, row: dict) -> "RmspRecord":
        return cls(
            name=row["name_ex"],
            subject_type=row["nptype"],
            category=row["category"],
            ogrn=row["ogrn"],
            inn=row["inn"],
            main_activity_code=row["okved1"],
            main_activity_name=row["okved1name"],
            region_code=row["regioncode"],
            is_new=bool(row["isnew"]),
            date_registered=row["dtregistry"],
            date_excluded=row.get("dtregistryout"),
            phone=row.get("phone"),
            email=row.get("email"),
            website=row.get("www"),
            employees_num=row.get("od2_sschr"),
            has_licenses=bool(row["has_licenses"]),
            is_hitech=bool(row["is_hitech"]),
            is_partnership=bool(row["is_partnership"]),
            is_social=bool(row["pr_soc"]),
        )


def fetch_by_inn(inn: str) -> RmspRecord | None:
    """Look up a single organization/IE in the SME registry by INN.

    Returns None if the INN is not in the registry (not an SME, or the INN
    doesn't exist).
    """
    resp = requests.post(
        SEARCH_URL,
        headers=HEADERS,
        data={
            "mode": "inn-list",
            "page": "1",
            "pageSize": "100",
            "sortField": "",
            "innList": inn,
        },
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()["data"]
    # logger.info(f'Ответ rmsp.nalog.ru для ИНН {inn}: {rows}')
    return RmspRecord.from_api(rows[0]) if rows else None

def fetch_raw_inn(inn): # тестовая фунция - убрать в проде
    """Fetch raw JSON data from rmsp.nalog.ru for a given INN."""
    resp = requests.post(
        SEARCH_URL,
        headers=HEADERS,
        data={
            "mode": "inn-list",
            "page": "1",
            "pageSize": "100",
            "sortField": "",
            "innList": inn,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()['data']

if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(fetch_by_inn(arg))
        # print(fetch_raw_inn(arg))