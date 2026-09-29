import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import requests

PASSPORT_URL = "https://www.nalog.gov.ru/opendata/7707329152-rsmp/meta.csv"
DATASET_URL = "https://www.nalog.gov.ru/opendata/7707329152-rsmp/"
SLICE = Path(__file__).resolve().parents[1] / "data" / "msp_slice.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadarBot/1.0)"}


@dataclass
class MspRecord:
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


def latest_url() -> str:
    text = requests.get(PASSPORT_URL, headers=HEADERS, timeout=60).text
    versions = []
    for row in csv.reader(io.StringIO(text)):
        found = re.fullmatch(r"data-(\d{2})(\d{2})(\d{4})-structure-\d{8}\.zip", row[0]) if row else None
        if found and len(row) > 1:
            versions.append((found.group(3) + found.group(2) + found.group(1), row[1]))
    if not versions:
        raise RuntimeError("no data versions in the SME registry passport")
    return max(versions)[1]


def download(url: str, target: Path) -> None:
    with requests.get(url, headers=HEADERS, stream=True, timeout=300) as response:
        response.raise_for_status()
        with open(target, "wb") as f:
            for chunk in response.iter_content(1 << 20):
                f.write(chunk)


def record(doc: ET.Element) -> MspRecord:
    org = doc.find("ОргВклМСП")
    if org is not None:
        name, inn, ogrn, subject = org.get("НаимОрг") or org.get("НаимОргСокр"), org.get("ИННЮЛ"), org.get("ОГРН"), "UL"
    else:
        ip = doc.find("ИПВклМСП")
        person = ip.find("ФИОИП")
        full = " ".join(filter(None, (person.get(k) for k in ("Фамилия", "Имя", "Отчество")))) if person is not None else ""
        name, inn, ogrn, subject = f"ИП {full}".strip(), ip.get("ИННФЛ"), ip.get("ОГРНИП"), "IP"
    okved = doc.find("СвОКВЭД/СвОКВЭДОсн")
    place = doc.find("СведМН")
    staff = (doc.get("ССЧР") or "").strip()
    return MspRecord(
        name=" ".join((name or inn).split()), subject_type=subject, category=int(doc.get("КатСубМСП") or 0), ogrn=ogrn or "", inn=inn,
        main_activity_code=okved.get("КодОКВЭД", "") if okved is not None else "",
        main_activity_name=okved.get("НаимОКВЭД", "") if okved is not None else "",
        region_code=place.get("КодРегион", "") if place is not None else "",
        is_new=doc.get("ПризНовМСП") == "1", date_registered=doc.get("ДатаВклМСП") or "", date_excluded=None,
        phone=None, email=None, website=None,
        employees_num=int(staff) if staff.isdigit() else None,
        has_licenses=doc.find("СвЛиценз") is not None,
        is_hitech=any(product.get("ПрОтнПрод") == "1" for product in doc.findall("СвПрод")),
        is_partnership=doc.find("СвПрогПарт") is not None,
        is_social=doc.get("СведСоцПред") == "1",
    )


def parse(stream) -> Iterator[tuple[str, MspRecord]]:
    for _, element in ET.iterparse(stream, events=("end",)):
        if element.tag == "Документ":
            yield element.get("ДатаСост") or "", record(element)
            element.clear()


def read_zip(path: Path) -> Iterator[tuple[str, MspRecord]]:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".xml"):
                with archive.open(name) as stream:
                    yield from parse(stream)


def read_slice(path: Path = SLICE) -> Iterator[tuple[str, MspRecord]]:
    with open(path, "rb") as stream:
        yield from parse(stream)


def make_slice(archive_path: Path, inns: list[str], target: Path) -> list[str]:
    wanted = set(inns)
    documents = []
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            if not wanted:
                break
            with archive.open(name) as stream:
                for _, element in ET.iterparse(stream, events=("end",)):
                    if element.tag != "Документ":
                        continue
                    subject = element.find("ОргВклМСП")
                    if subject is None:
                        subject = element.find("ИПВклМСП")
                    inn = subject.get("ИННЮЛ") or subject.get("ИННФЛ")
                    if inn in wanted:
                        documents.append(ET.tostring(element, encoding="unicode"))
                        wanted.discard(inn)
                    element.clear()
    body = "".join(documents)
    header = f'<?xml version="1.0" encoding="UTF-8"?><Файл ТипИнф="РЕЕСТРМСП" КолДок="{len(documents)}">'
    target.write_text(header + body + "</Файл>\n", encoding="utf-8")
    return sorted(set(inns) - wanted)
