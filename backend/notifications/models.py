from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from databases.users_db import Base


class RegistrySnapshot(Base):
    __tablename__ = "registry_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inn: Mapped[str] = mapped_column(String(12), index=True)
    source: Mapped[str] = mapped_column(String(8))
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    data_hash: Mapped[str] = mapped_column(String(40))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_snap_inn_src_time", "inn", "source", "fetched_at"),)


class BusinessProfile(Base):
    __tablename__ = "business_profiles"
    inn: Mapped[str] = mapped_column(String(12), ForeignKey("businesses.inn"), primary_key=True)
    tax_regime: Mapped[str | None] = mapped_column(String(16), nullable=True)
    has_employees: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    headcount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flags: Mapped[dict] = mapped_column(JSONB, default=dict)
    bank_biks: Mapped[list] = mapped_column(JSONB, default=list)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    okved_main: Mapped[str | None] = mapped_column(String(20), nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    has_licenses: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    patent_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    patent_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    kpp: Mapped[str | None] = mapped_column(String(9), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    director_position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    director_name: Mapped[str | None] = mapped_column(String(200), nullable=True)


class LawRecord(Base):
    __tablename__ = "laws"
    eo_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    header: Mapped[str] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(Text)
    published: Mapped[date] = mapped_column(Date, index=True)
    topics: Mapped[list] = mapped_column(JSONB, default=list)
    region: Mapped[str | None] = mapped_column(String(2), nullable=True)
    amended: Mapped[list] = mapped_column(JSONB, default=list)
    effective: Mapped[list] = mapped_column(JSONB, default=list)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pdf_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RadarEvent(Base):
    __tablename__ = "radar_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inn: Mapped[str] = mapped_column(String(12), index=True)
    type: Mapped[str] = mapped_column(String(48))
    kind: Mapped[str] = mapped_column(String(10))
    key: Mapped[str] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(8), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    due: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="open")
    in_list: Mapped[bool] = mapped_column(Boolean, default=False)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("uq_event_once", "key", unique=True, postgresql_where=text("kind = 'once'")),
        Index("uq_event_condition_open", "key", unique=True,
              postgresql_where=text("kind = 'condition' AND resolved_at IS NULL")),
    )


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("radar_events.id"), nullable=True)
    template: Mapped[str] = mapped_column(String(48))
    label: Mapped[str] = mapped_column(String(16))
    dedup_key: Mapped[str] = mapped_column(String(200), unique=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    keyboard: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
