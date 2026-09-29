from __future__ import annotations

from dataclasses import dataclass

import requests
import logging

logger = logging.getLogger(__name__)


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
    name: str
    subject_type: str
    category: int
    ogrn: str
    inn: str
    main_activity_code: str
    main_activity_name: str
    region_code: str
    is_new: bool
    date_registered: str
    date_excluded: str | None
    phone: str | None
    email: str | None
    website: str | None
    employees_num: int | None
    has_licenses: bool
    is_hitech: bool
    is_partnership: bool
    is_social: bool

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
    return RmspRecord.from_api(rows[0]) if rows else None

if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(fetch_by_inn(arg))