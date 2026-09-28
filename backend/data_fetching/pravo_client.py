"""Официальный интернет-портал правовой информации: новые акты, их текст и PDF.

Ключей и капчи нет. Эндпоинты проверены вживую 28.09.2026 (Swagger:
http://publication.pravo.gov.ru/swagger/v1/swagger.json):

    GET publication.pravo.gov.ru/api/Documents?Block=…&DocumentTypes=…&PeriodType=day&Date=ДД.ММ.ГГГГ
        → опубликованные за день: eoNumber, complexName («Федеральный закон от … № …\\n "Название"»),
          name, publishDateShort, pagesCount, pdfFileLength. Дата — только ДД.ММ.ГГГГ, ISO молча игнорируется.
    GET …/api/Documents?Number=819&DocumentDateFrom=31.05.2025&DocumentDateTo=31.05.2025
        → акт по номеру и дате: так узнаём название акта, в который «вносятся изменения».
    GET …/file/pdf?eoNumber=…   → PDF. Это скан: текстового слоя нет.

Текст без OCR есть в «Актуальных редакциях» (actual.pravo.gov.ru), но не у всех актов:
у федеральных законов и постановлений Правительства он появляется через 1–7 дней после
публикации, у приказов министерств его нет совсем. Есть ли — отвечает
GET …/api/DocumentText?eonumber=… (true/false). Сам текст — три запроса к API сайта:
card → redactions (по pnum = eoNumber) → redtext (по redid), HTML.
"""
from __future__ import annotations

import html
import json
import re
from datetime import date

import requests

PUBLICATION = "http://publication.pravo.gov.ru"
ACTUAL = "http://actual.pravo.gov.ru:8000/api/ebpi/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# Какие акты смотрим: блок портала → виды документов (id из /api/DocumentTypes).
# Указы и распоряжения — почти всегда кадровые и организационные; региональные постановления
# и приказы — тарифы, субсидии, госзакупки учреждений. Для бизнеса важны законы (в том числе
# региональные: ставки УСН и патента, ограничения продажи алкоголя), постановления Правительства
# и приказы ведомств (формы отчётов).
FEDERAL_LAW = "82a8bf1c-3bc7-47ed-827f-7affd43a7f27"
SOURCES = {
    "president": (FEDERAL_LAW,),
    "government": ("fd5a8766-f6fd-4ac2-8fd9-66f414d314ac",),             # Постановление
    "federal_authorities": ("2dddb344-d3e2-4785-a899-7aa12bd47b6f",),    # Приказ
    "subjects": ("8910e61f-371d-490c-a1b8-aa7b8a5a48be",                 # Закон
                 "e880fa45-e4f4-4db9-bba0-847666adebab"),                # Областной закон
}


def _get(url: str, **params) -> requests.Response:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp


def published(day: date) -> list[dict]:
    """Акты, опубликованные за день, из всех SOURCES; к каждому добавлен block."""
    out = []
    for block, types in SOURCES.items():
        for doc_type in types:
            page = 1
            while True:
                data = _get(f"{PUBLICATION}/api/Documents", Block=block, DocumentTypes=doc_type,
                            PeriodType="day", Date=f"{day:%d.%m.%Y}", PageSize=200, Index=page).json()
                out += [{**item, "block": block} for item in data.get("items") or []]
                if page >= (data.get("pagesTotalCount") or 1):
                    break
                page += 1
    return out


def find_act(block: str, number: str, signed: date) -> dict | None:
    """Акт по номеру и дате подписания — например, постановление, в которое вносятся изменения."""
    items = _get(f"{PUBLICATION}/api/Documents", Block=block, Number=number, DocumentDateFrom=f"{signed:%d.%m.%Y}",
                 DocumentDateTo=f"{signed:%d.%m.%Y}", PageSize=10, Index=1).json().get("items") or []
    return items[0] if len(items) == 1 else None


def text(eo_number: str) -> str | None:
    """Текст акта в первоначальной редакции или None, если его ещё нет в «Актуальных редакциях»."""
    # на акты субъектов (номер 87…) портал отвечает 400 — текстов региональных актов там нет
    has_text = requests.get(f"{PUBLICATION}/api/DocumentText", params={"eonumber": eo_number},
                            headers=HEADERS, timeout=60)
    if has_text.status_code != 200 or has_text.text.strip() != "true":
        return None
    reds = _get(ACTUAL + "redactions/", bpa="ebpi", t=json.dumps({"pnum": eo_number, "ttl": 2})).json()
    redactions = reds.get("redactions") or []
    if not redactions:
        return None
    red = next((r for r in redactions if r.get("redinitial")), redactions[0])
    raw = _get(ACTUAL + "redtext", bpa="ebpi", t=str(red["redid"]), ttl=2).json().get("redtext")
    if not raw:
        return None
    raw = re.sub(r"(?is)<(style|script|head)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h\d>", "\n", raw)
    plain = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return "\n".join(line for line in (" ".join(ln.split()) for ln in plain.splitlines()) if line)


def pdf(eo_number: str) -> bytes:
    return _get(f"{PUBLICATION}/file/pdf", eoNumber=eo_number).content


def page_url(eo_number: str) -> str:
    return f"{PUBLICATION}/document/{eo_number}"


if __name__ == "__main__":
    import sys

    day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    for item in published(day):
        print(item["block"], item["eoNumber"], " ".join(item["complexName"].split())[:150])
