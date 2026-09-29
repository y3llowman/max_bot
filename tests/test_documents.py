import io
import os
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ.setdefault("MAX_TOKEN", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://max@localhost:5544/maxtest")

from docx import Document

from radar import documents
from radar.deadlines import Profile
from radar.obligations import BY_CODE, OBLIGATIONS, due_dates

LE = {"name": "ООО «Тест»", "inn": "7743212897", "kpp": "774301001", "ogrn": "1177746000000",
      "address": "г. Москва", "director_position": "Генеральный директор",
      "director_name": "Иванов И. И.", "region": "Москва", "tax_regime": "osno"}
IP = LE | {"name": "ИП Петров П. П.", "inn": "500100732259", "kpp": None, "ogrn": "304500116000157"}


def payload(code: str, nominal: date, period: str = "За период") -> dict:
    return BY_CODE[code].payload("тест", period) | {"original": nominal.isoformat(), "shifted": False}


def text_of(content: bytes) -> tuple[str, list[str]]:
    doc = Document(io.BytesIO(content))
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    return "\n".join(p.text for p in doc.paragraphs), cells


class EveryObligationHasDocument(unittest.TestCase):
    def test_all_obligations_have_a_builder(self):
        for o in OBLIGATIONS:
            with self.subTest(o.code):
                self.assertIn(o.document, documents.BUILDERS)
                self.assertIn(o.document, documents.TITLES)
                self.assertIn(o.document, documents.HINTS)

    def test_all_reports_are_described(self):
        for o in OBLIGATIONS:
            if o.document == "report_brief":
                self.assertIn(o.code, documents.REPORTS)

    def test_every_real_deadline_builds(self):
        profiles = [
            (Profile(inn=LE["inn"], is_legal_entity=True, tax_regime="osno", has_employees=True, headcount=40), LE),
            (Profile(inn=LE["inn"], is_legal_entity=True, tax_regime="usn_income", has_employees=True, headcount=5), LE),
            (Profile(inn=IP["inn"], is_legal_entity=False, tax_regime="osno", has_employees=False, headcount=0), IP),
            (Profile(inn=IP["inn"], is_legal_entity=False, tax_regime="usn_ie", has_employees=True, headcount=3), IP),
        ]
        today = date(2026, 9, 28)
        for profile, req in profiles:
            for o in OBLIGATIONS:
                if o.applies(profile) is None:
                    continue
                for due, nominal, period in due_dates(o, profile, today, date(2027, 9, 28)):
                    with self.subTest(o.code, inn=req["inn"], due=due):
                        p = o.payload("тест", period) | {"original": nominal.isoformat()}
                        filename, content = documents.build(p, due, req | {"tax_regime": profile.tax_regime})
                        self.assertTrue(filename.endswith(".docx"))
                        self.assertGreater(len(content), 1000)
                        self.assertTrue(documents.caption(p).startswith("📄 "))


class EnpPayment(unittest.TestCase):
    def test_requisites(self):
        _, content = documents.build(payload("enp", date(2026, 10, 28)), date(2026, 10, 28), LE)
        _, cells = text_of(content)
        for value in ("18201061201010000510", "03100643000000018500", "40102810445370000059",
                      "017003983", "7727406020", "770701001", LE["inn"]):
            self.assertIn(value, cells)
        self.assertEqual(cells[cells.index("КПП плательщика") + 1], "0")
        self.assertNotIn(LE["kpp"], cells)

    def test_filename_uses_obligation_code(self):
        name, _ = documents.build(payload("usn_pay", date(2026, 10, 28)), date(2026, 10, 28), LE)
        self.assertEqual(name, "usn_pay_7743212897_20261028.docx")


class ReportPeriods(unittest.TestCase):
    def period(self, code: str, nominal: date) -> tuple:
        return documents.report_period(code, payload(code, nominal), nominal)

    def test_cumulative_forms(self):
        self.assertEqual(self.period("rsv", date(2027, 1, 25)), ("34", 2026))
        self.assertEqual(self.period("rsv", date(2027, 4, 25)), ("21", 2027))
        self.assertEqual(self.period("rsv", date(2027, 7, 25)), ("31", 2027))
        self.assertEqual(self.period("rsv", date(2026, 10, 25)), ("33", 2026))
        self.assertEqual(self.period("ndfl6", date(2027, 2, 25)), ("34", 2026))
        self.assertEqual(self.period("profit_decl", date(2027, 3, 25)), ("34", 2026))
        self.assertEqual(self.period("profit_decl", date(2027, 4, 25)), ("21", 2027))

    def test_vat_quarters(self):
        self.assertEqual(self.period("vat_decl", date(2027, 1, 25)), ("24", 2026))
        self.assertEqual(self.period("vat_decl", date(2027, 4, 25)), ("21", 2027))
        self.assertEqual(self.period("vat_decl", date(2027, 7, 25)), ("22", 2027))
        self.assertEqual(self.period("vat_decl", date(2026, 10, 25)), ("23", 2026))

    def test_annual_forms(self):
        self.assertEqual(self.period("usn_decl", date(2027, 3, 25)), ("34", 2026))
        self.assertEqual(self.period("ip_3ndfl", date(2027, 4, 30)), ("34", 2026))
        self.assertEqual(self.period("buh", date(2027, 3, 31)), (None, 2026))

    def test_monthly_and_sfr_forms_have_no_code(self):
        self.assertEqual(self.period("psfl", date(2026, 10, 26)), (None, None))
        self.assertEqual(self.period("efs1", date(2026, 10, 26)), (None, None))

    def test_nominal_date_wins_over_shifted_due(self):
        p = payload("rsv", date(2027, 4, 25))
        self.assertEqual(documents.report_period("rsv", p, date(2027, 4, 26)), ("21", 2027))


class ReportBrief(unittest.TestCase):
    def test_title_page_codes(self):
        _, content = documents.build(payload("vat_decl", date(2027, 1, 25), "За IV квартал 2026"),
                                     date(2027, 1, 25), LE)
        text, cells = text_of(content)
        self.assertIn("1151001", cells)
        self.assertIn("24", cells)
        self.assertIn("2026", cells)
        self.assertIn(LE["kpp"], cells)
        self.assertIn("Книга продаж", text)
        self.assertIn("памятка, а не бланк", text)
        self.assertNotIn("Подготовить документ", text)

    def test_ip_has_no_kpp_row(self):
        _, content = documents.build(payload("ip_3ndfl", date(2027, 4, 30)), date(2027, 4, 30), IP)
        text, cells = text_of(content)
        self.assertNotIn("КПП", cells)
        self.assertIn("ОГРНИП", cells)
        self.assertIn("1151020", cells)
        self.assertIn("личный кабинет ИП", text)

    def test_efs1_points_to_sfr(self):
        _, content = documents.build(payload("efs1", date(2027, 1, 25)), date(2027, 1, 25), LE)
        text, cells = text_of(content)
        self.assertNotIn("Форма по КНД", cells)
        self.assertIn("Социального фонда", text)


if __name__ == "__main__":
    unittest.main()
