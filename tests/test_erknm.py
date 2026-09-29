import io
import sys
import unittest
from dataclasses import asdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from data_fetching import erknm_client
from radar import detectors as det
from radar.render import build_context, company_ctx, render

TODAY = date(2026, 9, 27)
INN = "7701234567"

XML = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<ns2:INSPECTIONS YEAR="2026" MONTH="10" xmlns="https://proverki.gov.ru/opendata/3.0/20220115" xmlns:ns2="https://proverki.gov.ru/opendata/3.0/20220125">
  <INSPECTION CLASSIFICATION="КНМ" STATUS="Ожидает проведения" STATUS_KEY="TYPE_WAITING_CARRY_OUT" ERPID="1001" TYPE_NAME="Внеплановое КНМ" START_DATE="2026-10-19" STOP_DATE="2026-10-21">
    <KIND_CONTROL VALUE="Федеральный государственный пожарный надзор"/>
    <KIND_KNM VALUE="Выездная проверка"/>
    <SUBJECT INN="{INN}" NAME="ООО МОСТАР" TYPE="ЮЛ"><OKVEDS CODE="74.10" NAME="Дизайн"/></SUBJECT>
    <KNO_ORGANIZATION VALUE="ГУ МЧС РОССИИ ПО Г. МОСКВЕ"/>
  </INSPECTION>
  <INSPECTION CLASSIFICATION="ПМ" STATUS="Предостережение объявлено" STATUS_KEY="REMARK" ERPID="1002" START_DATE="2026-09-20">
    <KIND_CONTROL VALUE="Муниципальный земельный контроль"/>
    <KIND_KNM VALUE="Объявление предостережения"/>
    <SUBJECT INN="{INN}" TYPE="ЮЛ"/>
    <KNO_ORGANIZATION VALUE="АДМИНИСТРАЦИЯ ГОРОДА"/>
    <WARNING_INFO><CAPTION>Земельный   участок
      не используется.</CAPTION></WARNING_INFO>
  </INSPECTION>
  <INSPECTION CLASSIFICATION="ПМ" STATUS="Ожидает проведения" STATUS_KEY="TYPE_WAITING_CARRY_OUT" ERPID="1003" START_DATE="2026-10-18" STOP_DATE="2026-10-28">
    <KIND_CONTROL VALUE="Контроль в области защиты прав потребителей"/>
    <KIND_KNM VALUE="Профилактический визит"/>
    <SUBJECT INN="******760***" TYPE="ФЛ"/>
    <KNO_ORGANIZATION VALUE="РОСПОТРЕБНАДЗОР"/>
  </INSPECTION>
</ns2:INSPECTIONS>""".encode()


def knm(**fields) -> dict:
    return {"erpid": "1", "inn": INN, "classification": "ПМ", "status": "Ожидает проведения",
            "status_key": "TYPE_WAITING_CARRY_OUT", "kind": "Профилактический визит",
            "control": "Контроль в области защиты прав потребителей", "authority": "РОСПОТРЕБНАДЗОР",
            "type_name": None, "start": "2026-10-18", "stop": "2026-10-28", "warning": None} | fields


def text_of(draft: det.Draft) -> str:
    ctx = build_context(draft.type, draft.payload, company_ctx(None, {"name": 'ООО "МОСТАР"'}, INN), TODAY, src="erknm")
    return render(draft.type, ctx)


class ErknmTest(unittest.TestCase):
    def test_parse_keeps_only_our_inns(self):
        found = erknm_client.parse(io.BytesIO(XML), {INN})
        self.assertEqual([k.erpid for k in found], ["1001", "1002"])
        check, warning = found
        self.assertEqual((check.kind, check.control, check.authority, check.type_name, check.start),
                         ("Выездная проверка", "Федеральный государственный пожарный надзор",
                          "ГУ МЧС РОССИИ ПО Г. МОСКВЕ", "Внеплановое КНМ", "2026-10-19"))
        self.assertEqual(warning.warning, "Земельный участок не используется.")

    def test_months_around(self):
        self.assertEqual(erknm_client.months_around(date(2026, 12, 5)), [(2026, 11), (2026, 12), (2027, 1), (2027, 2)])

    def test_inspection_becomes_task_with_start_date(self):
        found = [asdict(k) for k in erknm_client.parse(io.BytesIO(XML), {INN})]
        (check, warning), cancelled = det.inspection_events(INN, found, TODAY)
        self.assertEqual(cancelled, [])
        self.assertEqual((check.type, check.key, check.due), ("inspection.planned", "knm:1001", date(2026, 10, 19)))
        text = text_of(check)
        self.assertIn("ГУ МЧС РОССИИ ПО Г. МОСКВЕ планирует выездную проверку с 19 октября 2026", text)
        self.assertIn("Внеплановое КНМ. Вид контроля: Федеральный государственный пожарный надзор.", text)
        self.assertEqual(warning.type, "inspection.warning")
        self.assertIn("«Земельный участок не используется.»", text_of(warning))

    def test_preventive_visit_is_not_called_inspection(self):
        [visit], _ = det.inspection_events(INN, [knm()], TODAY)
        self.assertEqual(visit.payload["title"], "Профилактический визит")
        text = text_of(visit)
        self.assertIn("Запланирован профилактический визит", text)
        self.assertIn("предписания не выдаются", text)

    def test_past_and_cancelled(self):
        drafts, cancelled = det.inspection_events(
            INN, [knm(erpid="2", start="2026-09-01"), knm(erpid="3", status="Отменено", status_key="TYPE_CANCELED")], TODAY)
        self.assertEqual((drafts, cancelled), ([], ["knm:3"]))


if __name__ == "__main__":
    unittest.main()
