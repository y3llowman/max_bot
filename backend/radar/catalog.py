from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


ICON = {Severity.CRITICAL: "🔴", Severity.WARNING: "🟠", Severity.INFO: "🔵"}


class Delivery(str, Enum):
    IMMEDIATE = "immediate"
    DIGEST = "digest"


@dataclass(frozen=True)
class EventType:
    code: str
    title: str
    severity: Severity
    delivery: Delivery
    kind: str = "once"
    repeat_days: int | None = None
    remind_before: tuple[int, ...] = ()


_TYPES = [
    EventType("egrul.unreliable", "Отметка о недостоверности в ЕГРЮЛ",
              Severity.CRITICAL, Delivery.IMMEDIATE, kind="condition", repeat_days=14),
    EventType("egrul.unreliable_resolved", "Отметка о недостоверности снята",
              Severity.INFO, Delivery.IMMEDIATE),
    EventType("egrul.director_disqualified", "Руководитель дисквалифицирован",
              Severity.CRITICAL, Delivery.IMMEDIATE, kind="condition", repeat_days=14),
    EventType("egrul.disqualification_ended", "Срок дисквалификации руководителя истёк",
              Severity.WARNING, Delivery.IMMEDIATE),
    EventType("egrul.termination", "Ликвидация, реорганизация или предстоящее исключение",
              Severity.CRITICAL, Delivery.IMMEDIATE, kind="condition", repeat_days=7),
    EventType("egrul.changed", "Изменились сведения в ЕГРЮЛ",
              Severity.WARNING, Delivery.IMMEDIATE),
    EventType("mvd.foreign_director", "Уведомление МВД о трудовом договоре с иностранцем",
              Severity.WARNING, Delivery.IMMEDIATE),
    EventType("msp.not_found", "Компании нет в реестре МСП",
              Severity.WARNING, Delivery.IMMEDIATE, kind="condition", repeat_days=30),
    EventType("msp.excluded", "Компания исключена из реестра МСП",
              Severity.CRITICAL, Delivery.IMMEDIATE, kind="condition", repeat_days=30),
    EventType("msp.category_changed", "Изменилась категория МСП",
              Severity.WARNING, Delivery.IMMEDIATE, remind_before=(14, 3)),
    EventType("law.upcoming", "Вышел акт, который вас касается",
              Severity.WARNING, Delivery.IMMEDIATE, remind_before=(7, 0)),
    EventType("profile.question", "Уточняющий вопрос", Severity.INFO, Delivery.IMMEDIATE),
    EventType("inspection.planned", "Запланирована проверка",
              Severity.WARNING, Delivery.IMMEDIATE, remind_before=(30, 7, 1)),
    EventType("inspection.warning", "Объявлено предостережение", Severity.WARNING, Delivery.IMMEDIATE),
    EventType("deadline", "Срок отчётности или уплаты",
              Severity.WARNING, Delivery.IMMEDIATE, remind_before=(3, 1, 0, -1)),
    EventType("deadline.info", "Плановое событие",
              Severity.INFO, Delivery.DIGEST, remind_before=(7,)),
]

CATALOG: dict[str, EventType] = {t.code: t for t in _TYPES}

ON_RESOLVE: dict[str, str] = {"egrul.unreliable": "egrul.unreliable_resolved",
                               "egrul.director_disqualified": "egrul.disqualification_ended"}
