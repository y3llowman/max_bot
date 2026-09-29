from dataclasses import asdict
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from data_fetching.msp_open_data import MspRecord
from databases.users_db import Base
from notifications.models import Notification, RadarEvent


class Business(Base):
    __tablename__ = "businesses"

    inn: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    subject_type: Mapped[str] = mapped_column(String(2))
    category: Mapped[int] = mapped_column(Integer)
    ogrn: Mapped[str] = mapped_column(String(15))
    main_activity_code: Mapped[str] = mapped_column(String(20))
    main_activity_name: Mapped[str] = mapped_column(String(500))
    region_code: Mapped[str] = mapped_column(String(10))
    is_new: Mapped[bool] = mapped_column(Boolean)
    date_registered: Mapped[str] = mapped_column(String(20))
    date_excluded: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employees_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_licenses: Mapped[bool] = mapped_column(Boolean)
    is_hitech: Mapped[bool] = mapped_column(Boolean)
    is_partnership: Mapped[bool] = mapped_column(Boolean)
    is_social: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserBusiness(Base):
    __tablename__ = "user_businesses"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    inn: Mapped[str] = mapped_column(String(12), ForeignKey("businesses.inn"), primary_key=True, index=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MspRegistryEntry(Base):
    __tablename__ = "msp_registry"

    inn: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    subject_type: Mapped[str] = mapped_column(String(2))
    category: Mapped[int] = mapped_column(Integer)
    ogrn: Mapped[str] = mapped_column(String(15))
    main_activity_code: Mapped[str] = mapped_column(String(20))
    main_activity_name: Mapped[str] = mapped_column(Text)
    region_code: Mapped[str] = mapped_column(String(10))
    is_new: Mapped[bool] = mapped_column(Boolean)
    date_registered: Mapped[str] = mapped_column(String(20))
    date_excluded: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employees_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_licenses: Mapped[bool] = mapped_column(Boolean)
    is_hitech: Mapped[bool] = mapped_column(Boolean)
    is_partnership: Mapped[bool] = mapped_column(Boolean)
    is_social: Mapped[bool] = mapped_column(Boolean)


class MspRegistryLoad(Base):
    __tablename__ = "msp_registry_loads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(500))
    data_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    records: Mapped[int] = mapped_column(Integer)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompanyTaken(Exception):
    pass


async def save_business(db: AsyncSession, user_id: int, record: MspRecord) -> Business:
    taken = await db.scalar(select(UserBusiness.user_id).where(UserBusiness.inn == record.inn,
                                                              UserBusiness.user_id != user_id).limit(1))
    if taken is not None:
        raise CompanyTaken(record.inn)
    now = datetime.now(timezone.utc)

    business = await db.get(Business, record.inn) or Business(inn=record.inn)
    for field, value in asdict(record).items():
        setattr(business, field, value)
    business.updated_at = now
    db.add(business)

    others = select(UserBusiness.inn).where(UserBusiness.user_id == user_id, UserBusiness.inn != record.inn)
    await db.execute(update(Notification)
                     .where(Notification.user_id == user_id, Notification.status == "pending",
                            Notification.event_id.in_(select(RadarEvent.id).where(RadarEvent.inn.in_(others))))
                     .values(status="cancelled"))
    await db.execute(delete(UserBusiness).where(UserBusiness.user_id == user_id, UserBusiness.inn != record.inn))

    link = await db.get(UserBusiness, (user_id, record.inn)) or UserBusiness(user_id=user_id, inn=record.inn)
    link.connected_at = now
    db.add(link)

    await db.commit()
    return business


async def current_business(db: AsyncSession, user_id: int) -> Business | None:
    result = await db.execute(
        select(Business)
        .join(UserBusiness)
        .where(UserBusiness.user_id == user_id)
        .order_by(UserBusiness.connected_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
