import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("MAX_TOKEN", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://max@localhost:5544/maxtest")
os.environ.setdefault("SECRET_KEY", "test-secret-key-" * 4)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from main import app


class OpenApiTest(unittest.TestCase):
    def test_committed_spec_matches_code(self):
        committed = json.loads((ROOT / "openapi.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, app.openapi(), "обновите openapi.json: python backend/export_openapi.py")


if __name__ == "__main__":
    unittest.main()
