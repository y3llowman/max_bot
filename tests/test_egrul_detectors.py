"""Детекторы ЕГРЮЛ и разбор выписки — без БД и сети.

Запуск из корня репозитория: python -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from data_fetching import egrul_client  # noqa: E402
from radar import detectors as det  # noqa: E402
from radar.render import build_context, company_ctx, render  # noqa: E402

TODAY = date(2026, 9, 27)
INN = "7701234567"
ADDRESS = "Место нахождения и адрес юридического лица"
DIRECTOR = "Сведения о лице, имеющем право без доверенности действовать от имени юридического лица"
UNRELIABLE = "сведения недостоверны (результаты проверки достоверности содержащихся в ЕГРЮЛ сведений о юридическом лице)"


def extract(**fields) -> dict:
    return {"address": "115035, г. Москва, ул. Садовническая, д. 1", "tax_authority_name": "ИФНС России № 1 по г. Москве",
            "director": {"surname": "СТРОК", "name": "МАРИНА", "patronymic": "ИВАНОВНА",
                         "citizenship": "гражданин Российской Федерации"},
            "founders": [{"surname": "СТРОК", "name": "МАРИНА", "patronymic": "ИВАНОВНА", "share_percent": 100.0}],
            "notes": [], "status": None, "status_date": None, "director_disqualification_end": None} | fields


def text_of(draft: det.Draft) -> str:
    """Сообщение, как его отправит worker._send: шаблоны со StrictUndefined падают на недостающих полях."""
    ctx = build_context(draft.type, draft.payload, company_ctx(None, {"name": 'ООО "МОСТАР"'}, INN), TODAY, src="egrul")
    return render(draft.type, ctx)


class ConditionsTest(unittest.TestCase):
    def test_clean_extract_has_no_conditions(self):
        self.assertEqual(det.egrul_conditions(INN, extract(), TODAY), [])

    def test_unreliable_mark_gives_exclusion_date(self):
        notes = [{"section": ADDRESS, "text": UNRELIABLE, "date": "19.08.2024"},
                 {"section": DIRECTOR, "text": UNRELIABLE, "date": "20.11.2024"}]
        [draft] = det.egrul_conditions(INN, extract(notes=notes), TODAY)
        self.assertEqual((draft.type, draft.key, draft.due), ("egrul.unreliable", f"egrul.unreliable:{INN}", date(2025, 2, 19)))
        self.assertEqual(draft.payload["about"], ["адрес", "руководитель"])
        text = text_of(draft)
        self.assertIn("Касается: адрес, руководитель.", text)
        self.assertIn("Запись внесена 19 августа 2024", text)
        self.assertIn("возможно с 19 февраля 2025", text)

    def test_other_notes_are_ignored(self):
        notes = [{"section": ADDRESS, "text": "адрес изменён в связи с переименованием", "date": "01.02.2026"}]
        self.assertEqual(det.egrul_conditions(INN, extract(notes=notes), TODAY), [])

    def test_disqualification_only_while_it_lasts(self):
        cur = extract(director_disqualification_start="01.03.2026", director_disqualification_end="01.03.2027",
                      director_disqualification_court_date="15.02.2026")
        [draft] = det.egrul_conditions(INN, cur, TODAY)
        self.assertEqual(draft.type, "egrul.director_disqualified")
        self.assertIn("Строк М.И. дисквалифицирован с 1 марта 2026 по 1 марта 2027", text_of(draft))
        self.assertEqual(det.egrul_conditions(INN, cur, date(2027, 3, 2)), [])

    def test_upcoming_exclusion_has_objection_deadline(self):
        cur = extract(status="Регистрирующим органом принято решение о предстоящем исключении недействующего "
                             "юридического лица из ЕГРЮЛ", status_date="12.05.2026")
        [draft] = det.egrul_conditions(INN, cur, TODAY)
        self.assertEqual((draft.type, draft.due), ("egrul.termination", date(2026, 8, 12)))
        text = text_of(draft)
        self.assertIn("Подайте не позже 12 августа 2026", text)
        self.assertIn("Р38001", text)

    def test_liquidation_is_alert_without_deadline(self):
        [draft] = det.egrul_conditions(INN, extract(status="Находится в стадии ликвидации", status_date="01.09.2026"), TODAY)
        self.assertIsNone(draft.due)
        self.assertIn("Идёт ликвидация или реорганизация", text_of(draft))


class ChangesTest(unittest.TestCase):
    def test_first_snapshot_and_same_snapshot_give_nothing(self):
        self.assertEqual(det.egrul_changes(INN, None, extract(), TODAY), [])
        self.assertEqual(det.egrul_changes(INN, extract(), extract(), TODAY), [])

    def test_field_missing_in_old_snapshot_is_not_a_change(self):
        self.assertEqual(det.egrul_changes(INN, extract(address=None), extract(), TODAY), [])

    def test_new_foreign_director(self):
        new = extract(director={"surname": "АЛИЕВ", "name": "РУСТАМ", "citizenship": "гражданин Республики Узбекистан"})
        changed, mvd = det.egrul_changes(INN, extract(), new, TODAY)
        self.assertEqual((changed.type, changed.payload["old"], changed.payload["new"]),
                         ("egrul.changed", "Строк Марина Ивановна", "Алиев Рустам"))
        self.assertIn("Изменились сведения в ЕГРЮЛ: руководитель", text_of(changed))
        self.assertEqual((mvd.type, mvd.due), ("mvd.foreign_director", TODAY))
        self.assertIn("Алиев Р., гражданство: гражданин Республики Узбекистан", text_of(mvd))

    def test_founders_keep_company_names(self):
        new = extract(founders=[{"full_name": 'ООО "ХОЛДИНГ"', "share_percent": 100.0}])
        [draft] = det.egrul_changes(INN, extract(), new, TODAY)
        text = text_of(draft)
        self.assertIn("Было: Строк Марина Ивановна (100%)", text)
        self.assertIn("Стало: ООО &#34;ХОЛДИНГ&#34; (100%)", text)


class ResolutionsTest(unittest.TestCase):
    def event(self, type_, payload=None):
        return SimpleNamespace(type=type_, key=f"{type_}:{INN}", payload=payload or {})

    def test_unreliable_mark_removed(self):
        [draft] = det.resolutions([self.event("egrul.unreliable")], TODAY)
        self.assertEqual(draft.type, "egrul.unreliable_resolved")
        self.assertIn("Отметка о недостоверности снята", text_of(draft))

    def test_disqualification_ended_only_after_its_end(self):
        payload = {"director": {"fio": "Строк Марина Ивановна"}, "start": "01.03.2026", "end": "20.09.2026",
                   "court_date": None}
        [draft] = det.resolutions([self.event("egrul.director_disqualified", payload)], TODAY)
        self.assertIn("закончилась 7 дней назад", text_of(draft))
        early = payload | {"end": "01.03.2027"}  # руководителя сменили раньше срока
        self.assertEqual(det.resolutions([self.event("egrul.director_disqualified", early)], TODAY), [])

    def test_msp_conditions_have_no_resolution_message(self):
        self.assertEqual(det.resolutions([self.event("msp.excluded")], TODAY), [])


class ParseExtractTest(unittest.TestCase):
    """Строки таблицы — как их отдаёт PyMuPDF для настоящих выписок: с отметками о недостоверности
    и компании в стадии ликвидации."""
    ROWS = [
        ["Место нахождения и адрес юридического лица", None, None],
        ["5", "Адрес юридического лица", "632450,\nНОВОСИБИРСКАЯ ОБЛАСТЬ,\nС. ДОВОЛЬНОЕ"],
        ["6", "ГРН и дата внесения в ЕГРЮЛ записи,\nсодержащей указанные сведения", "1025405013193\n19.12.2002"],
        ["8", "Дополнительные сведения", "сведения недостоверны (результаты\nпроверки достоверности)"],
        ["9", "ГРН и дата внесения в ЕГРЮЛ записи,\nсодержащей указанные сведения", "2245400751286\n19.08.2024"],
        ["Сведения о состоянии юридического лица", None, None],
        ["10", "Состояние", "Находится в стадии ликвидации"],
        ["11", "ГРН и дата внесения в ЕГРЮЛ записи,\nсодержащей указанные сведения", "2267700000001\n01.09.2026"],
        ["Сведения о лице, имеющем право без доверенности действовать от имени юридического\nлица", None, None],
        ["21", "Фамилия\nИмя\nОтчество", "ТУРКОВ\nВЛАДИМИР\nНИКОЛАЕВИЧ"],
        ["23", "ГРН и дата внесения в ЕГРЮЛ записи,\nсодержащей указанные сведения", "2125456018246\n28.05.2012"],
        ["29", "Дополнительные сведения", "сведения недостоверны"],
        ["30", "ГРН и дата внесения в ЕГРЮЛ записи,\nсодержащей указанные сведения", "2245401044249\n20.11.2024"],
    ]

    def test_notes_and_status_get_entry_dates(self):
        with patch.object(egrul_client.pymupdf, "open"), patch.object(egrul_client, "_table_rows", return_value=self.ROWS):
            parsed = egrul_client.parse_extract_pdf(b"")
        self.assertEqual([(n.section, n.date) for n in parsed.notes], [(ADDRESS, "19.08.2024"), (DIRECTOR, "20.11.2024")])
        self.assertEqual((parsed.status, parsed.status_date), ("Находится в стадии ликвидации", "01.09.2026"))
        self.assertEqual(parsed.address, "632450, НОВОСИБИРСКАЯ ОБЛАСТЬ, С. ДОВОЛЬНОЕ")


if __name__ == "__main__":
    unittest.main()
