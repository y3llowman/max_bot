import os
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("MAX_TOKEN", "test")

from radar import laws
from radar.deadlines import Profile

PUBLISHED = date(2026, 8, 4)


def meta(header: str, name: str, block: str = "president", eo: str = "0001202608040001") -> dict:
    return {"eoNumber": eo, "complexName": f'{header}\n "{name}"', "name": f'"{name}"', "block": block,
            "publishDateShort": f"{PUBLISHED}T00:00:00", "pagesCount": 3, "pdfFileLength": 400_000}


def topics(name: str, block: str = "president") -> list[str] | None:
    law = laws.classify(meta("Федеральный закон от 04.08.2026 № 293-ФЗ", name, block), [], None)
    return None if law is None else law.topics


class Titles(unittest.TestCase):
    def test_tax_code_articles_map_to_chapters(self):
        self.assertEqual(topics("О внесении изменений в статьи 166 и 168 части второй Налогового кодекса "
                                "Российской Федерации"), ["vat"])
        self.assertEqual(topics("О внесении изменений в статьи 85 и 102 части первой и статью 227-1 части второй "
                                "Налогового кодекса Российской Федерации"), ["foreign"])

    def test_named_laws(self):
        self.assertEqual(topics("О внесении изменений в Трудовой кодекс Российской Федерации"), ["labor"])
        self.assertEqual(topics("О внесении изменений в статьи 5 и 20 Федерального закона «Об основах "
                                "государственного регулирования торговой деятельности в Российской Федерации»"), ["retail"])
        self.assertEqual(topics("Об утверждении особенностей проведения специальной оценки условий труда рабочих мест "
                                "в организациях, осуществляющих отдельные виды деятельности - субъектах малого "
                                "предпринимательства", "federal_authorities"), ["labor"])

    def test_ausn_is_not_usn(self):
        self.assertEqual(topics('О введении в действие на территории Нижегородской области специального налогового '
                                'режима "Автоматизированная упрощенная система налогообложения"'), ["ausn"])

    def test_acts_for_state_bodies_are_skipped(self):
        for name in (
            "Об утверждении Порядка представления сведений о доходах, расходах, об имуществе и обязательствах "
            "имущественного характера в ФАС России и ее территориальных органах",
            "Об утверждении Положения о проверке достоверности и полноты сведений, представляемых гражданами, "
            "претендующими на замещение отдельных должностей, и работниками Федеральной службы по контролю "
            "за алкогольным и табачным рынками",
            "Об утверждении перечня должностных лиц территориальных органов Фонда пенсионного и социального "
            "страхования Российской Федерации, уполномоченных на вынесение решений",
        ):
            with self.subTest(name[:40]):
                self.assertEqual(topics(name, "federal_authorities"), [])

    def test_opaque_amendments_wait_for_text(self):
        self.assertIsNone(topics("О внесении изменений в отдельные законодательные акты Российской Федерации"))
        self.assertIsNone(topics("О внесении изменений в часть вторую Налогового кодекса Российской Федерации"))
        self.assertIsNone(topics("О внесении изменений в Кодекс Российской Федерации об административных правонарушениях"))
        self.assertEqual(topics("О внесении изменений в Федеральный закон «О карантине растений»"), [])

    def test_amended_act_found_by_number(self):
        name = "О внесении изменений в постановление Правительства Российской Федерации от 31 мая 2025 г. № 819"
        self.assertEqual(laws.act_refs(name), [("government", "819", date(2025, 5, 31))])
        m = meta("Постановление Правительства Российской Федерации от 31.08.2026 № 1116", name, "government")
        self.assertIsNone(laws.classify(m, [], None))
        law = laws.classify(m, ["Об утверждении Правил маркировки средствами идентификации отдельных видов "
                                "товаров для детей"], None)
        self.assertEqual(law.topics, ["marking"])


LAW_TEXT = """РОССИЙСКАЯ ФЕДЕРАЦИЯ
ФЕДЕРАЛЬНЫЙ ЗАКОН
О внесении изменений в отдельные законодательные акты Российской Федерации
Принят Государственной Думой 21 июля 2026 года
Статья 1
Внести в часть вторую Налогового кодекса Российской Федерации (Собрание законодательства Российской Федерации, 2000, № 32, ст. 3340; 2025, № 30, ст. 4448) следующие изменения:
1) в пункте 1 статьи 346 12 слова "60 миллионов рублей" заменить словами "65 миллионов рублей";
2) статью 346 13 дополнить пунктом 4 2 следующего содержания:
"4 2. Положения статьи 12 Федерального закона от 29 июля 2004 года № 98-ФЗ применяются";
Статья 2
Внести в Федеральный закон от 22 мая 2003 года № 54-ФЗ "О применении контрольно-кассовой техники при осуществлении расчетов в Российской Федерации" (Собрание законодательства Российской Федерации, 2003, № 21, ст. 1957) следующие изменения:
1) в статье 1 1 слова "фискальный накопитель" заменить словами "фискальный модуль";
Статья 3
В статье 4 Федерального закона от 28 марта 1998 года № 52-ФЗ "Об обязательном государственном страховании жизни и здоровья военнослужащих" слова "органы исполнительной власти" заменить словами "исполнительные органы".
Статья 4
1. Настоящий Федеральный закон вступает в силу по истечении десяти дней после дня его официального опубликования, за исключением статьи 1 настоящего Федерального закона.
2. Статья 1 настоящего Федерального закона вступает в силу с 1 января 2027 года.
Президент Российской Федерации"""


class Text(unittest.TestCase):
    def test_amended_acts_and_tax_code_articles(self):
        m = meta("Федеральный закон от 04.08.2026 № 331-ФЗ", "О внесении изменений в отдельные законодательные акты "
                                                          "Российской Федерации")
        law = laws.classify(m, [], LAW_TEXT)
        self.assertEqual(law.topics, ["usn", "kkt"])
        self.assertEqual(law.amended, ["О применении контрольно-кассовой техники при осуществлении расчетов "
                                       "в Российской Федерации"])
        self.assertEqual(law.effective, [date(2026, 8, 15), date(2027, 1, 1)])

    def test_state_duty_is_not_profit_tax(self):
        text = ("Статья 1\nВнести в часть вторую Налогового кодекса Российской Федерации следующие изменения:\n"
                "1) в пункте 1 статьи 333 28 цифры \"1200\" заменить цифрами \"2000\";\n"
                "2) пункт 2 статьи 333 29 изложить в следующей редакции:")
        m = meta("Федеральный закон от 26.06.2026 № 190-ФЗ", "О внесении изменений в часть вторую Налогового "
                                                          "кодекса Российской Федерации")
        self.assertEqual(laws.classify(m, [], text).topics, [])

    def test_effective_dates(self):
        self.assertEqual(laws.effective_dates("Настоящее постановление вступает в силу со дня его официального "
                                              "опубликования.", PUBLISHED), [PUBLISHED])
        self.assertEqual(laws.effective_dates("Настоящий приказ вступает в силу с 1 марта 2027 г.", PUBLISHED),
                         [date(2027, 3, 1)])
        self.assertEqual(laws.effective_dates("С 1 марта 2027 г. участник оборота формирует УПД.", PUBLISHED), [])


class Regions(unittest.TestCase):
    def test_region_of_regional_law(self):
        for header, code in (("Закон Амурской области от 07.09.2026 № 816-ОЗ", "28"),
                             ("Закон города Москвы от 10.09.2026 № 20", "77"),
                             ("Закон Московской области от 10.09.2026 № 150/2026-ОЗ", "50"),
                             ("Закон Ямало-Ненецкого автономного округа от 10.09.2026 № 70-ЗАО", "89"),
                             ("Закон Ненецкого автономного округа от 10.09.2026 № 12-оз", "83"),
                             ("Закон Республики Алтай от 10.09.2026 № 40-РЗ", "04"),
                             ("Закон Алтайского края от 10.09.2026 № 55-ЗС", "22"),
                             ("Закон Республики Коми от 10.09.2026 № 70-РЗ", "11"),
                             ("Закон Кемеровской области - Кузбасса от 24.09.2026 № 104-ОЗ", "42"),
                             ("Областной закон Новгородской области от 04.09.2026 № 918-ОЗ", "53"),
                             ("Закон Санкт-Петербурга от 10.09.2026 № 400-80", "78")):
            with self.subTest(header):
                self.assertEqual(laws.region_of(header), code)


def profile(**kw) -> Profile:
    base = dict(inn="7707083893", is_legal_entity=True, region_code="16", okved_main="41.20",
                tax_regime="usn_income", has_employees=True, headcount=5, headcount_exact=True)
    return Profile(**(base | kw))


class Drafts(unittest.TestCase):
    TODAY = date(2026, 9, 28)

    def law(self, topics, **kw) -> laws.Law:
        return laws.Law("0001202609250001", "Федеральный закон от 25.09.2026 № 400-ФЗ", "О внесении изменений…",
                        date(2026, 9, 25), topics, **kw)

    def test_law_for_matching_profile(self):
        [d] = laws.drafts(self.law(["usn"], effective=[date(2027, 1, 1)]), profile(), self.TODAY)
        self.assertEqual((d.type, d.key, d.due), ("law.upcoming", "law:0001202609250001:7707083893", date(2027, 1, 1)))
        self.assertEqual(d.payload["reasons"], ["вы на УСН доходы"])
        self.assertIn("Декларация по УСН", d.payload["obligations"])
        self.assertEqual(laws.drafts(self.law(["usn"]), profile(tax_regime="osno"), self.TODAY), [])

    def test_already_in_force_is_not_a_task(self):
        [d] = laws.drafts(self.law(["labor"], effective=[date(2026, 9, 25)]), profile(), self.TODAY)
        self.assertIsNone(d.due)

    def test_regional_law_only_for_its_region(self):
        self.assertEqual(laws.drafts(self.law(["usn"], region="28"), profile(region_code="16"), self.TODAY), [])
        self.assertEqual(len(laws.drafts(self.law(["usn"], region="28"), profile(region_code="28"), self.TODAY)), 1)

    def test_unknown_flag_asks_once_answer_decides(self):
        [q] = laws.drafts(self.law(["kkt", "marking"]), profile(), self.TODAY)[:1]
        self.assertEqual((q.type, q.key), ("profile.question", "q:7707083893:cash_register"))
        self.assertEqual(len(laws.drafts(self.law(["kkt", "marking"]), profile(), self.TODAY)), 2)
        [d] = laws.drafts(self.law(["kkt"]), profile(flags={"cash_register": True}), self.TODAY)
        self.assertEqual((d.type, d.payload["reasons"]), ("law.upcoming", ["вы принимаете оплату через кассу"]))
        self.assertEqual(laws.drafts(self.law(["kkt"]), profile(flags={"cash_register": False}), self.TODAY), [])

    def test_industry_by_main_okved(self):
        [d] = laws.drafts(self.law(["catering"]), profile(okved_main="56.10"), self.TODAY)
        self.assertEqual(d.payload["reasons"], ["ваш основной вид деятельности — общепит (ОКВЭД 56.10)"])
        self.assertEqual(laws.drafts(self.law(["catering"]), profile(), self.TODAY), [])


if __name__ == "__main__":
    unittest.main()
