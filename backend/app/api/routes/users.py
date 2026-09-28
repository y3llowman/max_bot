from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.depends import get_current_user
from core.config import MAX_BOT_TOKEN
from databases import get_db
from databases.users_db import User
from core.security import create_access_token, validate_max_init_data

router = APIRouter(tags=["auth"], prefix="/user")


class AuthRequest(BaseModel):
    initData: str


@router.post("/auth")
async def webapp_auth(payload: AuthRequest, db: AsyncSession = Depends(get_db)):
    user_data = validate_max_init_data(payload.initData)
    max_user_id = int(user_data["id"])

    result = await db.execute(select(User).where(User.max_user_id == max_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(max_user_id=max_user_id)
        db.add(user)

    user.username = user_data.get("username")
    user.first_name = user_data.get("first_name")
    user.last_name = user_data.get("last_name")
    user.language_code = user_data.get("language_code")
    user.photo_url = user_data.get("photo_url")
    user.last_login = datetime.now(timezone.utc)
    user.is_active = True  # открыл приложение — снова доступен, даже если раньше блокировал бота
    await db.commit()

    return {"access_token": create_access_token(max_user_id), "token_type": "bearer"}


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.max_user_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language_code": user.language_code,
        "photo_url": user.photo_url,
        "is_staff": user.is_staff,
    }
