import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

from fastapi import HTTPException, status
from jose import JWTError, jwt

from core.config import MAX_BOT_TOKEN, MAX_INIT_DATA_MAX_AGE, SECRET_KEY

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=12)

if len(SECRET_KEY.get_secret_value()) < 32:
    raise RuntimeError("SECRET_KEY не задан или короче 32 символов: `openssl rand -hex 32` → SECRET_KEY=… в .env")

def validate_max_init_data(init_data: str) -> dict:
    raw_pairs = parse_qsl(init_data, keep_blank_values=True)
    if not raw_pairs:
        raise HTTPException(status_code=401, detail="Empty initData")

    keys = [key for key, _ in raw_pairs]
    if len(keys) != len(set(keys)) or keys.count("hash") != 1:
        raise HTTPException(status_code=401, detail="Invalid initData parameters")

    pairs = dict(raw_pairs)
    received_hash = pairs.pop("hash")

    try:
        auth_date = int(pairs["auth_date"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid auth_date") from exc

    age = time.time() - auth_date
    if age < -60 or age > MAX_INIT_DATA_MAX_AGE:
        raise HTTPException(status_code=401, detail="Expired initData")

    launch_params = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(
        b"WebAppData", MAX_BOT_TOKEN.get_secret_value().encode(), hashlib.sha256
    ).digest()
    calculated = hmac.new(secret_key, launch_params.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid initData signature")

    try:
        return json.loads(pairs["user"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid initData user") from exc


def create_access_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + TOKEN_TTL
    return jwt.encode({"sub": str(user_id), "exp": expires}, SECRET_KEY.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY.get_secret_value(), algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
