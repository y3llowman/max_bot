from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user
from databases import get_db
from databases.users_db import User
from notifications.planner import NotificationSettings

router = APIRouter(tags=["settings"], prefix="/settings")


@router.get("/notifications", response_model=NotificationSettings, response_model_exclude_none=True,
            summary="Настройки уведомлений")
async def get_notification_settings(user: User = Depends(get_current_user)):
    return NotificationSettings.of(user.notification_settings)


@router.put("/notifications", status_code=204, summary="Сохранить настройки уведомлений")
async def save_notification_settings(
    settings: NotificationSettings,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.notification_settings = settings.model_dump()
    await db.commit()


@router.post("/notifications/seen", status_code=204, summary="Лента просмотрена — гасит отметку непрочитанного")
async def mark_notifications_seen(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.notifications_seen_at = datetime.now(timezone.utc)
    await db.commit()
