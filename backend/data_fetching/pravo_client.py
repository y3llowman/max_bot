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

FEDERAL_LAW = "82a8bf1c-3bc7-47ed-827f-7affd43a7f27"
SOURCES = {
    "president": (FEDERAL_LAW,),
    "government": ("fd5a8766-f6fd-4ac2-8fd9-66f414d314ac",),
    "federal_authorities": ("2dddb344-d3e2-4785-a899-7aa12bd47b6f",),
    "subjects": ("8910e61f-371d-490c-a1b8-aa7b8a5a48be",
                 "e880fa45-e4f4-4db9-bba0-847666adebab"),
}


def _get(url: str, **params) -> requests.Response:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp


def published(day: date) -> list[dict]:
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
    items = _get(f"{PUBLICATION}/api/Documents", Block=block, Number=number, DocumentDateFrom=f"{signed:%d.%m.%Y}",
                 DocumentDateTo=f"{signed:%d.%m.%Y}", PageSize=10, Index=1).json().get("items") or []
    return items[0] if len(items) == 1 else None


def text(eo_number: str) -> str | None:
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
