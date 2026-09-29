from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

MSK = ZoneInfo("Europe/Moscow")
REMIND_HOUR = 9


def today_msk() -> date:
    return datetime.now(MSK).date()

REMIND_OFFSETS: dict[str, tuple[int, ...]] = {
    "d30-7-1": (30, 7, 1, 0),
    "d7-3-1": (7, 3, 1, 0),
    "d3-0": (3, 0),
    "d0": (0,),
}


class NotificationSettings(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    chat: bool = True
    push: bool = False
    email: bool = False
    email_address: str | None = None
    quiet: bool = True
    quiet_range: str = Field("22:00–08:00", pattern=r"^\d{2}:\d{2}–\d{2}:\d{2}$")
    remind: Literal["d30-7-1", "d7-3-1", "d3-0", "d0"] = "d30-7-1"

    @classmethod
    def of(cls, stored: dict | None) -> NotificationSettings:
        return cls.model_validate(stored or {})

    def is_quiet(self, now: datetime) -> bool:
        if not self.quiet:
            return False
        start, end = (time.fromisoformat(part) for part in self.quiet_range.split("–"))
        t = now.astimezone(MSK).time()
        return start <= t or t < end if start > end else start <= t < end


def reminder_label(due: date, today: date, settings: NotificationSettings) -> str | None:
    days_left = (due - today).days
    if days_left < 0:
        return f"overdue:{today:%y%m%d}"
    if days_left in REMIND_OFFSETS[settings.remind]:
        return f"T-{days_left}"
    return None
