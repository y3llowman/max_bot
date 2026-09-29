import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from core.inn import is_valid_inn


class InnTest(unittest.TestCase):
    def test_valid(self):
        for inn in ("7743212897", "1650273744", "3666155612", "7707083893", "500100732259"):
            self.assertTrue(is_valid_inn(inn), inn)

    def test_invalid(self):
        for inn in ("7707083890", "7743212898", "500100732258", "123", "77432128970", "77432128a7", " 7743212897", ""):
            self.assertFalse(is_valid_inn(inn), inn)


if __name__ == "__main__":
    unittest.main()
