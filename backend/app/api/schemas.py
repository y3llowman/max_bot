"""Ответы API мини-приложения — зеркало miniapp/src/api/types.ts.

Фронт ждёт camelCase (fullName, nextDue, updatedAt): поля описаны в snake_case,
а наружу уходят по алиасам. Необязательные поля в контракте — `?:`, а не null,
поэтому роуты с ними отдают ответ с response_model_exclude_none.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Source(CamelModel):
    name: str
    demo: bool
    updated_at: datetime


class Benefit(CamelModel):
    title: str
    basis: str
    url: str


class Company(CamelModel):
    name: str
    full_name: str
    initials: str
    regime: str
    inn: str
    kpp: str | None = None
    ogrn: str
    okved: str | None = None       # «41.20 — Строительство жилых и нежилых зданий»
    category: str | None = None    # «Микропредприятие»
    headcount: str | None = None   # «16–25 человек»
    region: str | None = None      # «Республика Татарстан»
    needs_answers: bool            # режим или численность не указаны — обязанности неполные
    source: Source
    benefits: list[Benefit] = []   # льготы, которые доступны при численности компании (radar.deadlines)


class Task(CamelModel):
    id: str
    title: str
    subtitle: str
    status: Literal["overdue", "soon", "planned", "done"]
    due: date
    periodicity: str | None = None  # «Ежеквартально»


class Link(CamelModel):
    label: str
    url: str


class TaskSection(CamelModel):
    id: str
    icon: str
    title: str
    caption: str
    body: list[str] | None = None
    steps: list[str] | None = None
    link: Link | None = None


class TaskDetails(Task):
    heading: str
    sections: list[TaskSection]
    document: bool = False  # есть черновик для «Подготовить документ»
    next: Task | None = None


class Counters(CamelModel):
    overdue: int
    soon: int
    done: int


class DashboardData(CamelModel):
    counters: Counters
    tasks: list[Task]
    next_due: date | None = None
    unread: bool
