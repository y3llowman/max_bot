from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from databases import get_db
from databases.businesses_db import Business, current_business
from databases.users_db import User
from core.security import decode_access_token


bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Bearer token required", headers={"WWW-Authenticate": "Bearer"})

    user_id = decode_access_token(credentials.credentials)
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
