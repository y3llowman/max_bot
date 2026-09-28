"""Каталог событий радара: что за событие, насколько важно и как доставлять.

kind:
  condition — «состояние», которое держится во времени (отметка о недостоверности,
              дисквалификация). Открыто, пока детектор его видит; исчезло — закрываем.
  once      — разовое событие (изменение в ЕГРЮЛ, срок отчётности). Уникально по key навсегда.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


ICON = {Severity.CRITICAL: "🔴", Severity.WARNING: "🟠", Severity.INFO: "🔵"}


class Delivery(str, Enum):
    IMMEDIATE = "immediate"  # отдельным сообщением в ближайшее «окно» 09:00–21:00 по местному
    DIGEST = "digest"        # только в еженедельной сводке (пн 09:00)


@dataclass(frozen=True)
class EventType:
    code: str
    title: str
    severity: Severity
    delivery: Delivery
    kind: str = "once"                 # "once" | "condition"
    repeat_days: int | None = None     # повторять, пока событие открыто и не «Сделано»
    remind_before: tuple[int, ...] = ()  # для событий со сроком; 0 = в день срока, -1 = просрочка


_TYPES = [
    # --- ЕГРЮЛ: состояния ---
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
    # --- ЕГРЮЛ: изменения (diff двух снимков) ---
    EventType("egrul.changed", "Изменились сведения в ЕГРЮЛ",
              Severity.WARNING, Delivery.IMMEDIATE),
    EventType("mvd.foreign_director", "Уведомление МВД о трудовом договоре с иностранцем",
              Severity.WARNING, Delivery.IMMEDIATE),
    # --- Реестр МСП ---
    EventType("msp.not_found", "Компании нет в реестре МСП",
              Severity.WARNING, Delivery.IMMEDIATE, kind="condition", repeat_days=30),
    EventType("msp.excluded", "Компания исключена из реестра МСП",
              Severity.CRITICAL, Delivery.IMMEDIATE, kind="condition", repeat_days=30),
    EventType("msp.category_changed", "Изменилась категория МСП",
              Severity.WARNING, Delivery.IMMEDIATE, remind_before=(14, 3)),
    # --- Новые законы с pravo.gov.ru (radar/laws.py); срок — вступление в силу, если оно впереди ---
    EventType("law.upcoming", "Вышел акт, который вас касается",
              Severity.WARNING, Delivery.IMMEDIATE, remind_before=(7, 0)),
    EventType("profile.question", "Уточняющий вопрос", Severity.INFO, Delivery.IMMEDIATE),
    # --- Ежедневные проверки по внешним сервисам ---
    EventType("inspection.planned", "Запланирована проверка",
              Severity.WARNING, Delivery.IMMEDIATE, remind_before=(30, 7, 1)),
    EventType("inspection.warning", "Объявлено предостережение", Severity.WARNING, Delivery.IMMEDIATE),
    # --- Календарь ---
    EventType("deadline", "Срок отчётности или уплаты",
              Severity.WARNING, Delivery.IMMEDIATE, remind_before=(3, 1, 0, -1)),
    EventType("deadline.info", "Плановое событие",
              Severity.INFO, Delivery.DIGEST, remind_before=(7,)),
]

CATALOG: dict[str, EventType] = {t.code: t for t in _TYPES}

# Что отправить, когда состояние исчезло (condition закрылся сам)
ON_RESOLVE: dict[str, str] = {"egrul.unreliable": "egrul.unreliable_resolved",
                               "egrul.director_disqualified": "egrul.disqualification_ended"}
