import json
import os
from pathlib import Path

os.environ.setdefault("MAX_TOKEN", "export")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://export@localhost/export")
os.environ.setdefault("SECRET_KEY", "export-only-" * 4)

from main import app

target = Path(__file__).resolve().parents[1] / "openapi.json"
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(target)
