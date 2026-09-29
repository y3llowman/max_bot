from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from databases import get_db
from databases.businesses_db import Business, current_business
from databases.users_db import User
from core.security import decode_access_token


async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    user_id = decode_access_token(authorization.removeprefix("Bearer ").strip())
    result = await db.execute(select(User).where(User.max_user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_current_business(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Business:
    business = await current_business(db, user.id)
    if business is None:
        raise HTTPException(status_code=404, detail="Company not connected")
    return business
