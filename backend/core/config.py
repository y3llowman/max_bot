import logging
from pathlib import Path

from .env import ENV

BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR.parent / "frontend" / "build"  # npm run build в frontend/
HOST = ENV.HOST
PORT = ENV.PORT
DEBUG = ENV.DEBUG
PROJECT_NAME = ENV.PROJECT_NAME
SECRET_KEY = ENV.SECRET_KEY
MAX_BOT_TOKEN = ENV.MAX_BOT_TOKEN
MAX_INIT_DATA_MAX_AGE = ENV.MAX_INIT_DATA_MAX_AGE

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
