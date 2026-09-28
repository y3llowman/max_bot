"""Каталог обязанностей: что сдать или заплатить, кого это касается и когда срок.

Обязанность — это данные и два правила:
  applies(p)        → None, если не касается; иначе строка — ответ на «почему я это вижу»;
  schedule(p, year) → номинальные сроки за год с подписью периода.
Перенос срока с выходного на рабочий день (п. 7 ст. 6.1 НК РФ) делает next_workday().

Сроки и штрафы сверены с календарём бухгалтера на 2026 год. Если меняется НК, сверять заново.
В каталог не вошли СОУТ, ЭПД и ККТ: их сроки нельзя вычислить из реестров.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from radar.deadlines import REGIME_RU, Profile

Schedule = Callable[[Profile, int], list[tuple[date, str]]]

MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль",
              "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]

NK1 = "https://www.consultant.ru/document/cons_doc_LAW_19671/"
NK2 = "https://www.consultant.ru/document/cons_doc_LAW_28165/"
LAW_402 = "https://www.consultant.ru/document/cons_doc_LAW_122855/"
LAW_565 = "https://www.consultant.ru/document/cons_doc_LAW_464093/"
FNS = "https://www.nalog.gov.ru/"

PENALTY_119 = ("5% от суммы к уплате по отчёту за каждый месяц просрочки, не больше 30% "
               "и не меньше 1 000 ₽ (ст. 119 НК РФ). Через 20 рабочих дней после срока "
               "ФНС может приостановить операции по счёту (ст. 76 НК РФ).")
PENALTY_NOTICE = ("200 ₽ за каждое непредставленное уведомление (п. 1 ст. 126 НК РФ). "
                  "Без уведомления платёж не распределится по налогам, и начислят пени.")
PENALTY_LATE_PAYMENT = "Пени за каждый день просрочки (ст. 75 НК РФ)."
FNS_EDO = "Электронно через оператора ЭДО или личный кабинет налогоплательщика"


@dataclass(frozen=True)
class Obligation:
    code: str
    title: str
    what: str
    how: tuple[str, ...]
    where: str
    where_url: str
    format: str
    basis: str
    basis_url: str | None
    penalty: str
    periodicity: str
    applies: Callable[[Profile], str | None]
    schedule: Schedule
    document: str | None = None    # код черновика для «Подготовить документ» (radar/documents.py)

    def payload(self, why: str, period: str) -> dict:
        """Поля для radar_events.payload: их читают экран задачи и шаблон deadline.group."""
        return {
            "code": self.code, "title": self.title, "period": period, "what": self.what,
            "how": list(self.how), "where": self.where, "where_url": self.where_url,
            "format": self.format, "basis": self.basis, "basis_url": self.basis_url,
            "penalty": self.penalty, "periodicity": self.periodicity, "why": why,
            "document": self.document,
        }


# ---------------------------------------------------------------- рабочие дни
# Праздники по ст. 112 ТК РФ. Если праздник выпал на выходной, выходной переносится на следующий
# рабочий день, кроме январских: их переносит постановление правительства (DECREE_DAYS_OFF).
HOLIDAYS = ((1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),
            (2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4))
DECREE_DAYS_OFF = {
    date(2026, 1, 9), date(2026, 12, 31),                       # постановление № 1466 от 24.09.2025
    date(2027, 2, 22), date(2027, 11, 5), date(2027, 12, 31),   # постановление № 1187 от 17.09.2026
}
# выходные, которые постановление сделало рабочими: срок, выпавший на них, не переносится
DECREE_WORKDAYS = {date(2027, 2, 20)}                           # № 1187: суббота 20.02 → понедельник 22.02


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5 and d not in DECREE_WORKDAYS


def days_off(year: int) -> set[date]:
    off = set(DECREE_DAYS_OFF)
    for month, day in HOLIDAYS:
        holiday = date(year, month, day)
        off.add(holiday)
        if month != 1 and holiday.weekday() >= 5:
            moved = holiday + timedelta(days=1)
            while is_weekend(moved) or moved in off:
                moved += timedelta(days=1)
            off.add(moved)
    return off


def next_workday(d: date) -> date:
    off = days_off(d.year) | days_off(d.year + 1)
    while is_weekend(d) or d in off:
        d += timedelta(days=1)
    return d


# ---------------------------------------------------------------- расписания
def monthly(day: int) -> Schedule:
    """day-го числа каждого месяца — за прошлый месяц."""
    def schedule(p: Profile, year: int) -> list[tuple[date, str]]:
        out = []
        for month in range(1, 13):
            prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
            out.append((date(year, month, day), f"За {MONTHS_NOM[prev_month - 1]} {prev_year}"))
        return out
    return schedule


def cumulative(day: int, annual: tuple[int, int], annual_label: str = "За {year} год") -> Schedule:
    """Отчёт нарастающим итогом: за I квартал, полугодие и 9 месяцев — day-го числа месяца
    после периода; за прошлый год — в дату annual (месяц, день)."""
    def schedule(p: Profile, year: int) -> list[tuple[date, str]]:
        return [
            (date(year, *annual), annual_label.format(year=year - 1)),
            (date(year, 4, day), f"За I квартал {year}"),
            (date(year, 7, day), f"За полугодие {year}"),
            (date(year, 10, day), f"За 9 месяцев {year}"),
        ]
    return schedule


def yearly(month: int, day: int, label: str = "За {year} год") -> Schedule:
    return lambda p, year: [(date(year, month, day), label.format(year=year - 1))]


def vat_quarters(p: Profile, year: int) -> list[tuple[date, str]]:
    return [(date(year, 1, 25), f"За IV квартал {year - 1}"), (date(year, 4, 25), f"За I квартал {year}"),
            (date(year, 7, 25), f"За II квартал {year}"), (date(year, 10, 25), f"За III квартал {year}")]


USN_ADVANCES = ((4, "Аванс за I квартал"), (7, "Аванс за полугодие"), (10, "Аванс за 9 месяцев"))


def usn_notice_schedule(p: Profile, year: int) -> list[tuple[date, str]]:
    return [(date(year, month, 25), f"{label} {year}") for month, label in USN_ADVANCES]


def usn_pay_schedule(p: Profile, year: int) -> list[tuple[date, str]]:
    out = [(date(year, month, 28), f"{label} {year}") for month, label in USN_ADVANCES]
    annual = f"Налог за {year - 1} год"
    if p.is_legal_entity:
        out.append((date(year, 3, 28), annual))
    else:  # у ИП налог за год и аванс за I квартал — в один день
        out[0] = (date(year, 4, 28), f"{annual} и аванс за I квартал {year}")
    return out


def ndfl_notice_schedule(p: Profile, year: int) -> list[tuple[date, str]]:
    return [(date(year, month, 25), f"За 1–22 {MONTHS_GEN[month - 1]}") for month in range(1, 13)]


def enp_schedule(p: Profile, year: int) -> list[tuple[date, str]]:
    return [(date(year, month, 28), f"{MONTHS_NOM[month - 1].capitalize()} {year}") for month in range(1, 13)]


def ip_ndfl_notice_schedule(p: Profile, year: int) -> list[tuple[date, str]]:
    return [(date(year, month, 25), f"{label} {year}") for month, label in USN_ADVANCES]


def ip_ndfl_pay_schedule(p: Profile, year: int) -> list[tuple[date, str]]:
    """Авансы — до 28-го числа после квартала, налог за год — до 15 июля (п. 6 и 8 ст. 227 НК РФ)."""
    out = [(date(year, month, 28), f"{label} {year}") for month, label in USN_ADVANCES]
    return out + [(date(year, 7, 15), f"Налог за {year - 1} год")]


def patent_schedule(p: Profile, year: int) -> list[tuple[date, str]]:
    """п. 2 ст. 346.51 НК РФ: патент до 6 месяцев — вся сумма до конца срока; от 6 месяцев — треть
    в течение 90 дней от начала, остальное до конца срока. Кончается 31 декабря — платить до 28 декабря."""
    if not (p.patent_from and p.patent_to):
        return []
    start, end = p.patent_from, p.patent_to
    last = date(end.year, 12, 28) if (end.month, end.day) == (12, 31) else end
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    term = f"Патент {start:%d.%m.%Y}–{end:%d.%m.%Y}"
    payments = ([(last, f"{term}: вся сумма")] if months <= 6
                else [(start + timedelta(days=89), f"{term}: треть суммы"), (last, f"{term}: остальные две трети")])
    return [(d, label) for d, label in payments if d.year == year]


def ip_contrib_schedule(p: Profile, year: int) -> list[tuple[date, str]]:
    return [(date(year, 7, 1), f"1% с дохода свыше 300 000 ₽ за {year - 1} год"),
            (date(year, 12, 28), f"Фиксированные взносы за {year} год")]


# ---------------------------------------------------------------- применимость
def on_usn(p: Profile) -> str | None:
    if p.tax_regime in ("usn_income", "usn_ie"):
        return f"вы на {REGIME_RU[p.tax_regime]}"
    return None


def has_staff(p: Profile) -> str | None:
    """Отчётность работодателя. На АУСН её нет: НДФЛ за сотрудников по умолчанию считает и платит банк,
    взносы (кроме травматизма) не платятся, РСВ, 6-НДФЛ и персонифицированные сведения не сдаются
    (закон № 17-ФЗ) — остаётся только стаж в ЕФС-1 (efs1_ausn)."""
    if not p.has_employees or p.tax_regime == "ausn":
        return None
    return "у вас есть сотрудники — вы налоговый агент и страхователь"


def ausn_employer(p: Profile) -> str | None:
    if p.has_employees and p.tax_regime == "ausn":
        return "у вас есть сотрудники: сведения о стаже в Соцфонд сдают и на АУСН"
    return None


def ausn(p: Profile) -> str | None:
    return "вы на АУСН: налог считает ФНС, а заплатить его нужно самим" if p.tax_regime == "ausn" else None


def patent(p: Profile) -> str | None:
    if p.tax_regime == "psn" and p.patent_from and p.patent_to:
        return f"у вас патент на {p.patent_from:%d.%m.%Y}–{p.patent_to:%d.%m.%Y}"
    return None


def legal_entity(p: Profile) -> str | None:
    return "вы — организация: бухгалтерскую отчётность сдают все юрлица" if p.is_legal_entity else None


def osno(p: Profile) -> str | None:
    """НДС платят и организации, и ИП на ОСНО (ст. 143 НК РФ)."""
    return "вы на ОСНО и платите НДС" if p.tax_regime == "osno" else None


def osno_company(p: Profile) -> str | None:
    return "вы — организация на ОСНО" if p.is_legal_entity and p.tax_regime == "osno" else None


def osno_ip(p: Profile) -> str | None:
    return "вы — ИП на ОСНО" if not p.is_legal_entity and p.tax_regime == "osno" else None


def ip_not_ausn(p: Profile) -> str | None:
    if p.is_legal_entity or p.tax_regime == "ausn":
        return None
    return "вы — ИП: взносы «за себя» платят все ИП, даже без дохода"


def monthly_payments(p: Profile) -> str | None:
    if p.tax_regime == "ausn":
        return None  # налог АУСН — отдельной обязанностью ausn_pay, НДФЛ сотрудников платит банк
    if p.has_employees:
        return "у вас есть сотрудники: НДФЛ и взносы платят каждый месяц"
    if p.tax_regime == "osno":
        return "вы на ОСНО: НДС платят каждый месяц"
    return None


def quota(p: Profile) -> str | None:
    if p.headcount is not None and p.headcount > 35:
        return "в штате больше 35 человек — регион обязан установить вам квоту 2–4%"
    return None


# ---------------------------------------------------------------- каталог
OBLIGATIONS: tuple[Obligation, ...] = (
    Obligation(
        code="usn_decl", title="Декларация по УСН",
        what="Сдайте годовую декларацию по упрощённой системе.",
        how=("Сверьте доходы (и расходы, если УСН «доходы минус расходы») по книге учёта за год.",
             "Нажмите «Подготовить документ» — пришлём памятку: коды для титульного листа и что подготовить.",
             "Проверьте, что авансы за год учтены.",
             "Подпишите декларацию и отправьте в налоговую."),
        where="ФНС по месту учёта", where_url=FNS, format=FNS_EDO + " или на бумаге",
        basis="ст. 346.23 НК РФ", basis_url=NK2, penalty=PENALTY_119, periodicity="Раз в год",
        applies=on_usn,
        schedule=lambda p, year: [(date(year, 3 if p.is_legal_entity else 4, 25), f"За {year - 1} год")],
        document="report_brief",
    ),
    Obligation(
        code="usn_notice", title="Уведомление об авансе по УСН",
        what="Сообщите налоговой сумму аванса по УСН, чтобы она списала его с единого налогового счёта.",
        how=("Посчитайте аванс нарастающим итогом с начала года.",
             "Нажмите «Подготовить документ» — пришлём черновик с реквизитами и КБК.",
             "Впишите сумму и отправьте уведомление в налоговую."),
        where="ФНС по месту учёта", where_url=FNS, format=FNS_EDO,
        basis="п. 9 ст. 58 НК РФ", basis_url=NK1, penalty=PENALTY_NOTICE, periodicity="Ежеквартально",
        applies=on_usn, schedule=usn_notice_schedule, document="notice",
    ),
    Obligation(
        code="usn_pay", title="Уплата налога по УСН",
        what="Пополните единый налоговый счёт на сумму аванса или налога по УСН.",
        how=("Проверьте сумму в уведомлении или декларации.",
             "Нажмите «Подготовить документ» — пришлём реквизиты платёжки на ЕНП.",
             "Заплатите единым налоговым платежом (ЕНП) по реквизитам Казначейства."),
        where="Банк — платёж на единый налоговый счёт", where_url=FNS, format="Платёжное поручение",
        basis="ст. 346.21 НК РФ", basis_url=NK2, penalty=PENALTY_LATE_PAYMENT, periodicity="Ежеквартально",
        applies=on_usn, schedule=usn_pay_schedule, document="enp_payment",
    ),
    Obligation(
        code="ndfl_notice", title="Уведомление по НДФЛ и взносам",
        what="Сообщите налоговой суммы НДФЛ, удержанного с 1 по 22 число, и страховых взносов за прошлый месяц.",
        how=("Сверьте НДФЛ, удержанный с зарплат с 1 по 22 число.",
             "Нажмите «Подготовить документ» — пришлём черновик с реквизитами и КБК.",
             "Отправьте уведомление. НДФЛ за 23-е — конец месяца — отдельным уведомлением до 3-го числа."),
        where="ФНС по месту учёта", where_url=FNS, format=FNS_EDO,
        basis="п. 9 ст. 58 НК РФ", basis_url=NK1, penalty=PENALTY_NOTICE, periodicity="Ежемесячно",
        applies=has_staff, schedule=ndfl_notice_schedule, document="notice",
    ),
    Obligation(
        code="enp", title="Уплата ЕНП",
        what="Пополните единый налоговый счёт на сумму налогов и взносов из уведомлений.",
        how=("Сложите суммы из уведомлений и деклараций этого месяца.",
             "Нажмите «Подготовить документ» — пришлём реквизиты платёжки на ЕНП.",
             "Заплатите одним платежом на единый налоговый счёт."),
        where="Банк — платёж на единый налоговый счёт", where_url=FNS, format="Платёжное поручение",
        basis="ст. 11.3 и п. 1 ст. 58 НК РФ", basis_url=NK1, penalty=PENALTY_LATE_PAYMENT,
        periodicity="Ежемесячно", applies=monthly_payments, schedule=enp_schedule,
        document="enp_payment",
    ),
    Obligation(
        code="psfl", title="Персонифицированные сведения",
        what="Сдайте сведения о выплатах сотрудникам и исполнителям за прошлый месяц.",
        how=("Проверьте список работников и исполнителей по договорам ГПХ.",
             "Нажмите «Подготовить документ» — пришлём памятку: коды для титульного листа и что подготовить.",
             "Сформируйте отчёт в бухгалтерской программе и отправьте в налоговую."),
        where="ФНС по месту учёта", where_url=FNS, format=FNS_EDO,
        basis="пп. 2 п. 7 ст. 431 НК РФ", basis_url=NK2,
        penalty="200 ₽ за отчёт (ст. 126 НК РФ). Через 20 рабочих дней после срока ФНС может приостановить операции по счёту.",
        periodicity="Ежемесячно", applies=has_staff, schedule=monthly(25),
        document="report_brief",
    ),
    Obligation(
        code="rsv", title="Расчёт по страховым взносам (РСВ)",
        what="Сдайте расчёт по страховым взносам за отчётный период.",
        how=("Сверьте начисленные взносы с выплатами сотрудникам.",
             "Нажмите «Подготовить документ» — пришлём памятку: коды для титульного листа и что подготовить.",
             "Проверьте, что суммы совпадают с уведомлениями за месяцы квартала.",
             "Подпишите и отправьте расчёт в налоговую."),
        where="ФНС по месту учёта", where_url=FNS, format=FNS_EDO + "; при 10 работниках и меньше — можно на бумаге",
        basis="п. 7 ст. 431 НК РФ", basis_url=NK2, penalty=PENALTY_119, periodicity="Ежеквартально",
        applies=has_staff, schedule=cumulative(25, annual=(1, 25)),
        document="report_brief",
    ),
    Obligation(
        code="ndfl6", title="Расчёт 6-НДФЛ",
        what="Сдайте расчёт по НДФЛ, который вы удержали и перечислили за сотрудников.",
        how=("Сверьте удержанный НДФЛ с уведомлениями за период.",
             "Нажмите «Подготовить документ» — пришлём памятку: коды для титульного листа и что подготовить.",
             "Сформируйте расчёт нарастающим итогом с начала года.",
             "Подпишите и отправьте в налоговую."),
        where="ФНС по месту учёта", where_url=FNS, format=FNS_EDO + "; при 10 работниках и меньше — можно на бумаге",
        basis="п. 2 ст. 230 НК РФ", basis_url=NK2,
        penalty=("1 000 ₽ за каждый полный или неполный месяц просрочки (п. 1.2 ст. 126 НК РФ). "
                 "Через 20 рабочих дней после срока ФНС может приостановить операции по счёту."),
        periodicity="Ежеквартально", applies=has_staff,
        schedule=cumulative(25, annual=(2, 25)),
        document="report_brief",
    ),
    Obligation(
        code="efs1", title="ЕФС-1 в Социальный фонд",
        what="Сдайте раздел 2 формы ЕФС-1 о взносах на травматизм, а в январе ещё и подраздел 1.2 о стаже.",
        how=("Сверьте начисленные взносы на травматизм за период.",
             "Нажмите «Подготовить документ» — пришлём памятку: коды для титульного листа и что подготовить.",
             "В январе добавьте сведения о стаже всех работников за прошлый год.",
             "Отправьте форму в Социальный фонд."),
        where="Социальный фонд России", where_url="https://sfr.gov.ru/",
        format="Электронно через оператора ЭДО или кабинет страхователя; при 10 работниках и меньше — можно на бумаге",
        basis="ст. 24 закона № 125-ФЗ, ст. 11 закона № 27-ФЗ", basis_url=None,
        penalty=("Раздел 2: 5% от взносов за последние 3 месяца за каждый месяц просрочки, не больше 30% "
                 "и не меньше 1 000 ₽ (ст. 26.30 закона № 125-ФЗ). Стаж: 500 ₽ за каждого работника "
                 "(ст. 17 закона № 27-ФЗ)."),
        periodicity="Ежеквартально", applies=has_staff,
        schedule=cumulative(25, annual=(1, 25), annual_label="За {year} год: стаж и взносы на травматизм"),
        document="report_brief",
    ),
    Obligation(
        code="efs1_ausn", title="ЕФС-1: стаж сотрудников",
        what="Сдайте подраздел 1.2 формы ЕФС-1 о стаже работников за прошлый год — на АУСН это остаётся за вами.",
        how=("Сверьте периоды работы каждого сотрудника за год.",
             "Нажмите «Подготовить документ» — пришлём памятку: что подготовить.",
             "Отправьте форму в Социальный фонд. О приёме и увольнении (подраздел 1.1) сообщайте, как и раньше, "
             "на следующий рабочий день."),
        where="Социальный фонд России", where_url="https://sfr.gov.ru/",
        format="Электронно через оператора ЭДО или кабинет страхователя; при 10 работниках и меньше — можно на бумаге",
        basis="ст. 11 закона № 27-ФЗ", basis_url=None,
        penalty="500 ₽ за каждого работника, по которому не сданы сведения (ст. 17 закона № 27-ФЗ).",
        periodicity="Раз в год", applies=ausn_employer, schedule=yearly(1, 25), document="report_brief",
    ),
    Obligation(
        code="ausn_pay", title="Уплата налога по АУСН",
        what="Заплатите налог по АУСН за прошлый месяц: ФНС сама считает его по данным банка и до 15-го числа "
             "присылает сумму в личный кабинет.",
        how=("Проверьте сумму в личном кабинете налогоплательщика или в банке.",
             "Нажмите «Подготовить документ» — пришлём реквизиты платёжки на ЕНП.",
             "Заплатите единым налоговым платежом до 25-го числа."),
        where="Банк — платёж на единый налоговый счёт", where_url="https://ausn.nalog.gov.ru/",
        format="Платёжное поручение или согласие на списание в банке",
        basis="закон № 17-ФЗ об АУСН", basis_url=None, penalty=PENALTY_LATE_PAYMENT,
        periodicity="Ежемесячно", applies=ausn, schedule=monthly(25), document="enp_payment",
    ),
    Obligation(
        code="quota", title="Сведения о выполнении квоты для инвалидов",
        what="Сообщите в службу занятости, как выполнена квота для приёма инвалидов за прошлый месяц.",
        how=("Уточните размер квоты в законе вашего региона: от 2 до 4% среднесписочной численности.",
             "Нажмите «Подготовить документ» — пришлём черновик приказа о квотируемых местах.",
             "Заполните форму № 7 в личном кабинете работодателя на «Работе России»."),
        where="Служба занятости — портал «Работа России»", where_url="https://trudvsem.ru/",
        format="Электронно в личном кабинете работодателя",
        basis="ст. 38 закона № 565-ФЗ, форма № 7 (приказ Минтруда № 204н)", basis_url=LAW_565,
        penalty=("Непредставление сведений — от 3 000 до 5 000 ₽ для организации (ст. 19.7 КоАП РФ). "
                 "Отказ принять инвалида в пределах квоты — от 5 000 до 10 000 ₽ руководителю (ст. 5.42 КоАП РФ)."),
        periodicity="Ежемесячно", applies=quota, schedule=monthly(10), document="quota_order",
    ),
    Obligation(
        code="buh", title="Бухгалтерская отчётность",
        what="Сдайте годовой баланс и отчёт о финансовых результатах.",
        how=("Закройте год в бухгалтерской программе.",
             "Нажмите «Подготовить документ» — пришлём памятку: коды для титульного листа и что подготовить.",
             "Сформируйте баланс и отчёт о финансовых результатах (упрощённые формы — для малого бизнеса).",
             "Отправьте в налоговую: отчётность попадёт в государственный информационный ресурс ГИР БО."),
        where="ФНС — ГИР БО", where_url="https://bo.nalog.gov.ru/", format="Только электронно",
        basis="ст. 18 закона № 402-ФЗ «О бухгалтерском учёте»", basis_url=LAW_402,
        penalty="200 ₽ за каждый непредставленный документ (п. 1 ст. 126 НК РФ) и 300–500 ₽ руководителю (ст. 15.6 КоАП РФ).",
        periodicity="Раз в год", applies=legal_entity, schedule=yearly(3, 31),
        document="report_brief",
    ),
    Obligation(
        code="vat_decl", title="Декларация по НДС",
        what="Сдайте декларацию по НДС за прошедший квартал.",
        how=("Сверьте счета-фактуры в книгах покупок и продаж.",
             "Нажмите «Подготовить документ» — пришлём памятку: коды для титульного листа и что подготовить.",
             "Проверьте вычеты и восстановленный НДС.",
             "Подпишите и отправьте декларацию через оператора ЭДО."),
        where="ФНС по месту учёта", where_url=FNS,
        format="Только электронно через оператора ЭДО: бумажная декларация считается непредставленной",
        basis="п. 5 ст. 174 НК РФ", basis_url=NK2, penalty=PENALTY_119, periodicity="Ежеквартально",
        applies=osno, schedule=vat_quarters,
        document="report_brief",
    ),
    Obligation(
        code="profit_decl", title="Декларация по налогу на прибыль",
        what="Сдайте декларацию по налогу на прибыль за отчётный период.",
        how=("Сверьте доходы и расходы в налоговом учёте.",
             "Нажмите «Подготовить документ» — пришлём памятку: коды для титульного листа и что подготовить.",
             "Проверьте авансовые платежи за период.",
             "Подпишите и отправьте декларацию в налоговую."),
        where="ФНС по месту учёта", where_url=FNS, format=FNS_EDO,
        basis="ст. 289 НК РФ", basis_url=NK2, penalty=PENALTY_119, periodicity="Ежеквартально",
        applies=osno_company, schedule=cumulative(25, annual=(3, 25)),
        document="report_brief",
    ),
    Obligation(
        code="ip_3ndfl", title="Декларация 3-НДФЛ",
        what="Сдайте декларацию о доходах от предпринимательской деятельности за прошлый год.",
        how=("Соберите доходы и профессиональные вычеты за год.",
             "Нажмите «Подготовить документ» — пришлём памятку: коды для титульного листа и что подготовить.",
             "Заполните 3-НДФЛ в личном кабинете ИП или бухгалтерской программе.",
             "Подпишите и отправьте в налоговую."),
        where="ФНС по месту учёта", where_url=FNS, format=FNS_EDO + " или на бумаге",
        basis="ст. 229 НК РФ", basis_url=NK2, penalty=PENALTY_119, periodicity="Раз в год",
        applies=osno_ip, schedule=yearly(4, 30),
        document="report_brief",
    ),
    Obligation(
        code="ip_ndfl_notice", title="Уведомление об авансе по НДФЛ (ИП)",
        what="Сообщите налоговой сумму аванса по НДФЛ с доходов от бизнеса, чтобы она списала его с единого "
             "налогового счёта.",
        how=("Посчитайте аванс нарастающим итогом с начала года по прогрессивной шкале.",
             "Нажмите «Подготовить документ» — пришлём черновик с реквизитами.",
             "Сверьте КБК в личном кабинете ИП: он зависит от суммы дохода.",
             "Впишите сумму и отправьте уведомление."),
        where="ФНС по месту учёта", where_url=FNS, format=FNS_EDO,
        basis="п. 9 ст. 58 и п. 8 ст. 227 НК РФ", basis_url=NK1, penalty=PENALTY_NOTICE, periodicity="Ежеквартально",
        applies=osno_ip, schedule=ip_ndfl_notice_schedule, document="notice",
    ),
    Obligation(
        code="ip_ndfl_pay", title="Уплата НДФЛ ИП",
        what="Пополните единый налоговый счёт на сумму аванса по НДФЛ или налога за прошлый год.",
        how=("Проверьте сумму в уведомлении или декларации 3-НДФЛ.",
             "Нажмите «Подготовить документ» — пришлём реквизиты платёжки на ЕНП.",
             "Заплатите единым налоговым платежом."),
        where="Банк — платёж на единый налоговый счёт", where_url=FNS, format="Платёжное поручение",
        basis="п. 6 и 8 ст. 227 НК РФ", basis_url=NK2, penalty=PENALTY_LATE_PAYMENT, periodicity="Ежеквартально",
        applies=osno_ip, schedule=ip_ndfl_pay_schedule, document="enp_payment",
    ),
    Obligation(
        code="patent_pay", title="Оплата патента",
        what="Заплатите за патент: до 6 месяцев — всю сумму до конца срока, дольше — треть в первые 90 дней, "
             "остальное до конца срока.",
        how=("Проверьте сумму в патенте или личном кабинете ИП.",
             "Нажмите «Подготовить документ» — пришлём реквизиты платёжки на ЕНП.",
             "Заплатите единым налоговым платежом."),
        where="Банк — платёж на единый налоговый счёт", where_url="https://www.nalog.gov.ru/rn77/taxation/taxes/patent/",
        format="Платёжное поручение", basis="п. 2 ст. 346.51 НК РФ", basis_url=NK2,
        penalty=PENALTY_LATE_PAYMENT + " Неуплата в срок — утрата права на патент (п. 6 ст. 346.45 НК РФ).",
        periodicity="По сроку патента", applies=patent, schedule=patent_schedule, document="enp_payment",
    ),
    Obligation(
        code="ip_contrib", title="Страховые взносы ИП «за себя»",
        what="Заплатите фиксированные взносы, а с дохода свыше 300 000 ₽ — ещё 1%.",
        how=("Проверьте сумму фиксированных взносов на текущий год на сайте ФНС.",
             "Посчитайте 1% с дохода свыше 300 000 ₽ за прошлый год.",
             "Нажмите «Подготовить документ» — пришлём реквизиты платёжки на ЕНП.",
             "Заплатите единым налоговым платежом."),
        where="Банк — платёж на единый налоговый счёт", where_url=FNS, format="Платёжное поручение",
        basis="ст. 430 и 432 НК РФ", basis_url=NK2, penalty=PENALTY_LATE_PAYMENT, periodicity="Раз в год",
        applies=ip_not_ausn, schedule=ip_contrib_schedule, document="enp_payment",
    ),
)

BY_CODE = {o.code: o for o in OBLIGATIONS}


def due_dates(o: Obligation, p: Profile, start: date, end: date) -> list[tuple[date, date, str]]:
    """Сроки обязанности в окне [start, end]: (срок с переносом, номинальный срок, период)."""
    out = []
    for year in range(start.year, end.year + 1):
        for nominal, period in o.schedule(p, year):
            due = next_workday(nominal)
            if start <= due <= end:
                out.append((due, nominal, period))
    return out
