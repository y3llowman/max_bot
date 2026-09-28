"""Новые таблицы радара. Base — ваш общий DeclarativeBase из проекта."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from databases.users_db import Base


class RegistrySnapshot(Base):
    """Сырые снимки реестров: diff считаем между двумя последними по (inn, source)."""
    __tablename__ = "registry_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inn: Mapped[str] = mapped_column(String(12), index=True)
    source: Mapped[str] = mapped_column(String(8))             # 'egrul' | 'msp'
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # None = «не найдено»
    data_hash: Mapped[str] = mapped_column(String(40))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_snap_inn_src_time", "inn", "source", "fetched_at"),)


class BusinessProfile(Base):
    """То, чего нет в реестрах (режим, численность, признаки), и поправки пользователя к реестру —
    из вопросов бота и экрана «Данные компании» в мини-приложении. Поправка важнее реестра; пусто — берём реестр."""
    __tablename__ = "business_profiles"
    inn: Mapped[str] = mapped_column(String(12), ForeignKey("businesses.inn"), primary_key=True)
    tax_regime: Mapped[str | None] = mapped_column(String(16), nullable=True)
    has_employees: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    headcount: Mapped[int | None] = mapped_column(Integer, nullable=True)  # нижняя граница диапазона, HEADCOUNT_RU
    flags: Mapped[dict] = mapped_column(JSONB, default=dict)       # {"works_with_selfemployed": true, ...}
    bank_biks: Mapped[list] = mapped_column(JSONB, default=list)   # для проверки блокировок в «БАНКИНФОРМ»
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    okved_main: Mapped[str | None] = mapped_column(String(20), nullable=True)   # поправка основного ОКВЭД
    region_code: Mapped[str | None] = mapped_column(String(2), nullable=True)   # поправка региона
    has_licenses: Mapped[bool | None] = mapped_column(Boolean, nullable=True)   # поправка признака лицензий
    patent_from: Mapped[date | None] = mapped_column(Date, nullable=True)       # срок патента (ПСН)
    patent_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class LawRecord(Base):
    """Разобранные акты с pravo.gov.ru (radar/laws.py). Хранятся и нерелевантные (topics пустой) —
    чтобы не разбирать их заново каждый день."""
    __tablename__ = "laws"
    eo_number: Mapped[str] = mapped_column(String(32), primary_key=True)   # номер опубликования на портале
    header: Mapped[str] = mapped_column(String(500))                      # «Федеральный закон от … № …»
    name: Mapped[str] = mapped_column(Text)
    published: Mapped[date] = mapped_column(Date, index=True)
    topics: Mapped[list] = mapped_column(JSONB, default=list)             # коды radar.laws.TOPICS; [] — не про бизнес
    region: Mapped[str | None] = mapped_column(String(2), nullable=True)  # закон субъекта — код региона
    amended: Mapped[list] = mapped_column(JSONB, default=list)            # названия изменяемых актов
    effective: Mapped[list] = mapped_column(JSONB, default=list)          # даты вступления в силу, ISO
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pdf_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RadarEvent(Base):
    __tablename__ = "radar_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inn: Mapped[str] = mapped_column(String(12), index=True)
    type: Mapped[str] = mapped_column(String(48))
    kind: Mapped[str] = mapped_column(String(10))               # 'once' | 'condition'
    key: Mapped[str] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(8), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    due: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|done|snoozed|muted
    in_list: Mapped[bool] = mapped_column(Boolean, default=False)  # «В список дел»: задача в приложении и без срока
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        # разовое событие уникально навсегда
        Index("uq_event_once", "key", unique=True, postgresql_where=text("kind = 'once'")),
        # состояние: одно открытое на ключ; после resolve может «открыться» заново
        Index("uq_event_condition_open", "key", unique=True,
              postgresql_where=text("kind = 'condition' AND resolved_at IS NULL")),
    )


class Notification(Base):
    """Outbox: планировщик кладёт сюда, диспетчер отправляет по одному на пользователя. dedup_key =
    f'{event_id}:{user_id}:{label}'. Без события — готовый текст и клавиатура (карточки тура /demo)."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("radar_events.id"), nullable=True)
    template: Mapped[str] = mapped_column(String(48))
    label: Mapped[str] = mapped_column(String(16))              # alert | T-3 | T0 | T+1 | repeat | digest
    dedup_key: Mapped[str] = mapped_column(String(200), unique=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|sent|failed|cancelled
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)          # для сообщений без события
    keyboard: Mapped[dict | None] = mapped_column(JSONB, nullable=True)   # формат radar.render.keyboard
