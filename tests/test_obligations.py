"""Каталог обязанностей и правила напоминаний — без БД.

Запуск из корня репозитория: python -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from notifications.planner import MSK, NotificationSettings, reminder_label  # noqa: E402
from radar.deadlines import Profile  # noqa: E402
from radar.obligations import BY_CODE, OBLIGATIONS, due_dates, next_workday  # noqa: E402

TODAY = date(2026, 9, 26)
YEAR_AHEAD = date(2027, 9, 26)


def applicable(p: Profile) -> set[str]:
    return {o.code for o in OBLIGATIONS if o.applies(p)}


def dues(code: str, p: Profile) -> list[tuple[date, date, str]]:
    return due_dates(BY_CODE[code], p, TODAY, YEAR_AHEAD)


class WorkdayTest(unittest.TestCase):
    def test_weekend_moves_to_monday(self):
        self.assertEqual(next_workday(date(2026, 3, 28)), date(2026, 3, 30))  # суббота

    def test_new_year_holidays_and_decree(self):
        self.assertEqual(next_workday(date(2026, 1, 3)), date(2026, 1, 12))   # 9 января — перенос
        self.assertEqual(next_workday(date(2026, 12, 31)), date(2027, 1, 11))  # 31 декабря — перенос
        # 2027, постановление № 1187: 20.02 (сб) — рабочий, 22.02 и 5.11 — выходные, 1 и 9 мая, 12 июня — на пн
        self.assertEqual(next_workday(date(2027, 2, 20)), date(2027, 2, 20))
        self.assertEqual(next_workday(date(2027, 2, 21)), date(2027, 2, 24))
        self.assertEqual(next_workday(date(2027, 5, 1)), date(2027, 5, 4))
        self.assertEqual(next_workday(date(2027, 5, 9)), date(2027, 5, 11))
        self.assertEqual(next_workday(date(2027, 6, 12)), date(2027, 6, 15))
        self.assertEqual(next_workday(date(2027, 11, 4)), date(2027, 11, 8))

    def test_holiday_on_weekend_gives_extra_day_off(self):
        self.assertEqual(next_workday(date(2026, 5, 9)), date(2026, 5, 12))   # 9 мая — суббота → 11 мая выходной

    def test_workday_is_kept(self):
        self.assertEqual(next_workday(date(2026, 10, 26)), date(2026, 10, 26))


class ApplicabilityTest(unittest.TestCase):
    def test_company_on_usn_with_more_than_35_employees(self):
        p = Profile(inn="7701234567", is_legal_entity=True, tax_regime="usn_income", has_employees=True, headcount=36)
        self.assertEqual(applicable(p), {"usn_decl", "usn_notice", "usn_pay", "ndfl_notice", "enp", "psfl",
                                         "rsv", "ndfl6", "efs1", "quota", "buh"})

    def test_quota_only_above_35(self):
        p = Profile(inn="7701234567", is_legal_entity=True, has_employees=True, headcount=26)
        self.assertNotIn("quota", applicable(p))

    def test_ip_without_answers_sees_only_what_is_certain(self):
        self.assertEqual(applicable(Profile(inn="500100732259", is_legal_entity=False)), {"ip_contrib"})

    def test_ausn_ip_has_no_contributions(self):
        self.assertEqual(applicable(Profile(inn="500100732259", is_legal_entity=False, tax_regime="ausn")), set())

    def test_osno_company(self):
        codes = applicable(Profile(inn="7701234567", is_legal_entity=True, tax_regime="osno", has_employees=False))
        self.assertEqual(codes, {"vat_decl", "profit_decl", "enp", "buh"})

    def test_osno_ip_files_vat(self):
        codes = applicable(Profile(inn="500100732259", is_legal_entity=False, tax_regime="osno", has_employees=False))
        self.assertEqual(codes, {"vat_decl", "ip_3ndfl", "enp", "ip_contrib"})

    def test_why_is_filled(self):
        p = Profile(inn="7701234567", is_legal_entity=True, tax_regime="usn_ie", has_employees=True, headcount=36)
        for o in OBLIGATIONS:
            why = o.applies(p)
            self.assertTrue(why is None or why.strip(), o.code)


class DueDatesTest(unittest.TestCase):
    def test_usn_declaration_differs_for_company_and_ip(self):
        company = Profile(inn="7701234567", is_legal_entity=True, tax_regime="usn_income")
        ip = Profile(inn="500100732259", is_legal_entity=False, tax_regime="usn_income")
        self.assertEqual(dues("usn_decl", company), [(date(2027, 3, 25), date(2027, 3, 25), "За 2026 год")])
        self.assertEqual(dues("usn_decl", ip), [(date(2027, 4, 26), date(2027, 4, 25), "За 2026 год")])

    def test_ip_pays_annual_usn_tax_with_first_advance(self):
        ip = Profile(inn="500100732259", is_legal_entity=False, tax_regime="usn_income")
        periods = [period for _, _, period in dues("usn_pay", ip)]
        self.assertIn("Налог за 2026 год и аванс за I квартал 2027", periods)
        self.assertEqual(len(periods), len(set(periods)))

    def test_rsv_quarters(self):
        p = Profile(inn="7701234567", is_legal_entity=True, has_employees=True)
        self.assertEqual([(due, period) for due, _, period in dues("rsv", p)], [
            (date(2026, 10, 26), "За 9 месяцев 2026"),  # 25.10.2026 — воскресенье
            (date(2027, 1, 25), "За 2026 год"),
            (date(2027, 4, 26), "За I квартал 2027"),
            (date(2027, 7, 26), "За полугодие 2027"),
        ])

    def test_monthly_window_is_one_year(self):
        p = Profile(inn="7701234567", is_legal_entity=True, has_employees=True, headcount=36)
        self.assertEqual(len(dues("quota", p)), 12)
        self.assertEqual(dues("quota", p)[0][2], "За сентябрь 2026")


class ReminderTest(unittest.TestCase):
    def test_labels_follow_settings(self):
        s = NotificationSettings()  # по умолчанию d30-7-1
        self.assertEqual(reminder_label(date(2026, 10, 26), TODAY, s), "T-30")
        self.assertIsNone(reminder_label(date(2026, 10, 20), TODAY, s))
        self.assertEqual(reminder_label(TODAY, TODAY, s), "T-0")
        self.assertEqual(reminder_label(date(2026, 9, 20), TODAY, s), "overdue:260926")
        self.assertIsNone(reminder_label(date(2026, 10, 26), TODAY, NotificationSettings(remind="d3-0")))

    def test_quiet_hours_across_midnight(self):
        s = NotificationSettings(quiet=True, quiet_range="22:00–08:00")
        self.assertTrue(s.is_quiet(datetime(2026, 9, 26, 23, 30, tzinfo=MSK)))
        self.assertTrue(s.is_quiet(datetime(2026, 9, 26, 7, 59, tzinfo=MSK)))
        self.assertFalse(s.is_quiet(datetime(2026, 9, 26, 9, 0, tzinfo=MSK)))
        self.assertFalse(NotificationSettings(quiet=False).is_quiet(datetime(2026, 9, 26, 23, 30, tzinfo=MSK)))

    def test_settings_roundtrip_camel_case(self):
        s = NotificationSettings.model_validate({"chat": False, "quietRange": "23:00–07:00", "remind": "d0"})
        self.assertEqual(s.model_dump(by_alias=True)["quietRange"], "23:00–07:00")
        self.assertEqual(NotificationSettings.of(s.model_dump()), s)


if __name__ == "__main__":
    unittest.main()
