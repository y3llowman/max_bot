from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]


class Me(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    photo_url: str | None = None
    is_staff: bool


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
    okved: str | None = None
    category: str | None = None
    headcount: str | None = None
    region: str | None = None
    needs_answers: bool
    source: Source
    benefits: list[Benefit] = []


class Option(CamelModel):
    value: str
    label: str


class ProfileOptions(CamelModel):
    regimes: list[Option]
    headcounts: list[Option]
    regions: list[Option]
    flags: list[Option]


class ProfileForm(CamelModel):
    is_legal_entity: bool
    regime: str | None = None
    headcount: str | None = None
    registry_headcount: int | None = None
    okved: str
    registry_okved: str
    region: str
    registry_region: str
    has_licenses: bool
    flags: dict[str, bool | None]
    patent_from: date | None = None
    patent_to: date | None = None
    kpp: str | None = None
    address: str | None = None
    director_position: str | None = None
    director_name: str | None = None
    options: ProfileOptions


class ProfileUpdate(CamelModel):
    regime: str | None = None
    headcount: str | None = None
    okved: str
    region: str
    has_licenses: bool
    flags: dict[str, bool | None] = {}
    patent_from: date | None = None
    patent_to: date | None = None
    kpp: str | None = None
    address: str | None = None
    director_position: str | None = None
    director_name: str | None = None


class Task(CamelModel):
    id: str
    title: str
    subtitle: str
    status: Literal["overdue", "soon", "planned", "done"]
    due: date | None = None
    periodicity: str | None = None
    listed: bool = False


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
    document: bool = False
    next: Task | None = None


class FeedItem(CamelModel):
    id: str
    title: str
    subtitle: str
    sent_at: datetime
    due: date | None = None
    status: Literal["open", "done", "muted"]
    listed: bool
    severity: Literal["critical", "warning", "info"]


class Counters(CamelModel):
    overdue: int
    soon: int
    done: int


class DashboardData(CamelModel):
    counters: Counters
    tasks: list[Task]
    next_due: date | None = None
    unread: bool
