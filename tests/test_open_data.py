import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

os.environ.setdefault("MAX_TOKEN", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://max@localhost:5544/maxtest")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from data_fetching import erknm_client, msp_open_data

XML = """<?xml version="1.0" encoding="UTF-8"?><Файл ИдФайл="t" ВерсФорм="4.06" ТипИнф="РЕЕСТРМСП" КолДок="2">\
<ИдОтпр><ФИООтв Фамилия="-" Имя="-"/></ИдОтпр>\
<Документ ИдДок="1" ДатаСост="10.09.2026" ДатаВклМСП="01.08.2016" ВидСубМСП="1" КатСубМСП="2" ПризНовМСП="2" \
СведСоцПред="1" ССЧР="8"><ОргВклМСП НаимОрг="ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ &quot;КАМА&quot;" \
НаимОргСокр="ООО &quot;КАМА&quot;" ИННЮЛ="1650273744" ОГРН="1131650000001"/><СведМН КодРегион="16">\
<Регион Тип="Респ" Наим="Татарстан"/></СведМН><СвОКВЭД><СвОКВЭДОсн КодОКВЭД="41.20" \
НаимОКВЭД="Строительство жилых и нежилых зданий" ВерсОКВЭД="2014"/></СвОКВЭД><СвЛиценз НомЛиценз="1"/>\
<СвПрод КодПрод="1" НаимПрод="Изделие" ПрОтнПрод="1"/></Документ>\
<Документ ИдДок="2" ДатаСост="10.09.2026" ДатаВклМСП="10.12.2025" ВидСубМСП="2" КатСубМСП="1" ПризНовМСП="1" \
СведСоцПред="2"><ИПВклМСП ИННФЛ="422373249076" ОГРНИП="325420500122717"><ФИОИП Фамилия="БЕСЕДИНА" Имя="АЛЬБИНА" \
Отчество="ВЛАДИМИРОВНА"/></ИПВклМСП><СведМН КодРегион="42"/><СвОКВЭД><СвОКВЭДОсн КодОКВЭД="56.10.1" \
НаимОКВЭД="Рестораны"/></СвОКВЭД></Документ></Файл>"""

META = """property,value
standardversion,http://opendata.gosmonitor.ru/standard/3.0
identifier,7707329152-rsmp
data-10072026-structure-12052026.zip,https://file.nalog.ru/opendata/7707329152-rsmp/data-10072026-structure-12052026.zip
data-10082026-structure-12052026.zip,https://file.nalog.ru/opendata/7707329152-rsmp/data-10082026-structure-12052026.zip
data-10122025-structure-10062025.zip,https://file.nalog.ru/opendata/7707329152-rsmp/data-10122025-structure-10062025.zip
structure-12052026.xsd,https://file.nalog.ru/opendata/7707329152-rsmp/structure-12052026.xsd
"""

PASSPORT = b"""<?xml version="1.0" encoding="UTF-8"?><meta><identifier>7710146102-inspection-2026-9</identifier><data>
<dataversion><source>https://proverki.gov.ru/blob/erknm-opendata/2026/9/data-20260901-structure-20220125.zip</source>\
<created>20260901</created></dataversion>
<dataversion><source>https://proverki.gov.ru/blob/erknm-opendata/2026/9/data-20260928-structure-20220125.zip</source>\
<created>20260928</created></dataversion></data></meta>"""


def response(status=200, text="", content=b""):
    mock = MagicMock(status_code=status, text=text, content=content)
    mock.raise_for_status = MagicMock()
    return mock


class MspOpenDataTest(unittest.TestCase):
    def test_parses_company_and_entrepreneur(self):
        (date_ul, ul), (_, ip) = list(msp_open_data.parse(io.BytesIO(XML.encode("utf-8"))))
        self.assertEqual(date_ul, "10.09.2026")
        self.assertEqual((ul.inn, ul.name, ul.subject_type, ul.category, ul.ogrn), ("1650273744", 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КАМА"', "UL", 2, "1131650000001"))
        self.assertEqual((ul.main_activity_code, ul.region_code, ul.employees_num), ("41.20", "16", 8))
        self.assertEqual((ul.has_licenses, ul.is_hitech, ul.is_social, ul.is_new), (True, True, True, False))
        self.assertEqual((ip.inn, ip.name, ip.subject_type, ip.employees_num, ip.is_new), (
            "422373249076", "ИП БЕСЕДИНА АЛЬБИНА ВЛАДИМИРОВНА", "IP", None, True))

    def test_full_archive_is_read_member_by_member(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "rsmp.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("VO_RRMSPSV_1.xml", XML)
                z.writestr("VO_RRMSPSV_2.xml", XML.replace("1650273744", "7743212897"))
            inns = [r.inn for _, r in msp_open_data.read_zip(archive)]
            self.assertEqual(sorted(inns), ["1650273744", "422373249076", "422373249076", "7743212897"])
            target = Path(folder) / "slice.xml"
            self.assertEqual(msp_open_data.make_slice(archive, ["7743212897", "7707083893"], target), ["7743212897"])
            self.assertEqual([r.inn for _, r in msp_open_data.read_slice(target)], ["7743212897"])

    def test_latest_version_comes_from_page_or_passport(self):
        page = '<a href="https://file.nalog.ru/opendata/7707329152-rsmp/data-10092026-structure-12052026.zip">data</a>'
        pages = {msp_open_data.DATASET_URL: page, msp_open_data.PASSPORT_URL: META}
        with patch.object(msp_open_data.requests, "get", lambda url, **kw: response(text=pages[url])):
            self.assertTrue(msp_open_data.latest_url().endswith("data-10092026-structure-12052026.zip"),
                            "паспорт отстаёт на выпуск — берём то, что новее")
        pages[msp_open_data.DATASET_URL] = "нет ссылок"
        with patch.object(msp_open_data.requests, "get", lambda url, **kw: response(text=pages[url])):
            self.assertTrue(msp_open_data.latest_url().endswith("data-10082026-structure-12052026.zip"))
        with patch.object(msp_open_data.requests, "get", lambda url, **kw: response(text="")):
            with self.assertRaisesRegex(RuntimeError, "не найдена ссылка"):
                msp_open_data.latest_url()

    def test_bundled_slice_is_official_format(self):
        records = {r.inn: r for _, r in msp_open_data.read_slice()}
        self.assertIn("7743212897", records)
        self.assertIn("1650273744", records)
        self.assertIn("3666155612", records)
        self.assertNotIn("7707083893", records)


class Flaky:
    def __init__(self, data: bytes, fail_after: int):
        self.data, self.fail_after, self.calls = data, fail_after, []

    def __call__(self, url, headers=None, stream=False, timeout=None):
        start = int(headers["Range"].split("=")[1].rstrip("-")) if headers and "Range" in headers else 0
        self.calls.append(start)
        body = self.data[start:]
        first = not start and len(self.calls) == 1
        response = MagicMock(status_code=206 if start else 200, headers={"Content-Length": str(len(body))})
        response.raise_for_status = MagicMock()

        def chunks(size):
            yield body[: self.fail_after] if first else body
            if first:
                raise requests.ConnectionError("Read timed out")

        response.iter_content = chunks
        response.__enter__ = lambda self_: self_
        response.__exit__ = lambda *args: False
        return response


class DownloadTest(unittest.TestCase):
    def test_download_resumes_after_connection_drop(self):
        data = bytes(range(256)) * 1000
        flaky = Flaky(data, fail_after=70000)
        with tempfile.TemporaryDirectory() as folder, patch.object(msp_open_data.requests, "get", flaky),                 patch.object(msp_open_data.time, "sleep"):
            target = Path(folder) / "x.zip"
            msp_open_data.download("https://example.test/x.zip", target)
            self.assertEqual(target.read_bytes(), data)
        self.assertEqual(flaky.calls, [0, 70000], "вторая попытка продолжила с места обрыва")

    def test_download_gives_up_with_a_clear_error(self):
        broken = MagicMock(side_effect=requests.ConnectionError("down"))
        with tempfile.TemporaryDirectory() as folder, patch.object(msp_open_data.requests, "get", broken),                 patch.object(msp_open_data.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "не удалось скачать"):
                msp_open_data.download("https://example.test/x.zip", Path(folder) / "x.zip", attempts=3)
        self.assertEqual(broken.call_count, 3)


class ErknmPassportTest(unittest.TestCase):
    def test_latest_data_file_from_passport(self):
        with patch.object(erknm_client.requests, "get", return_value=response(content=PASSPORT)) as get:
            url = erknm_client.month_zip_url(2026, 9)
        self.assertEqual(url, "https://proverki.gov.ru/blob/erknm-opendata/2026/9/data-20260928-structure-20220125.zip")
        self.assertEqual(get.call_args.args[0], "https://proverki.gov.ru/blob/erknm-opendata/7710146102-inspection-2026-9.xml")

    def test_month_without_passport(self):
        with patch.object(erknm_client.requests, "get", return_value=response(status=404)):
            self.assertIsNone(erknm_client.month_zip_url(2026, 12))


if __name__ == "__main__":
    unittest.main()
