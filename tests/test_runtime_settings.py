import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import database as db
from runtime_settings import apply_runtime_settings, update_runtime_setting


def make_config():
    return SimpleNamespace(
        checkin=SimpleNamespace(points=10),
        chat=SimpleNamespace(
            text_min_length=5,
            text_points=1,
            sticker_points=1,
            photo_points=2,
            daily_limit=150,
            cooldown_seconds=10,
        ),
        rank=SimpleNamespace(top_n=10),
        lottery=SimpleNamespace(default_min_participants=1),
    )


class RuntimeSettingsTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "points_bot.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_apply_runtime_settings_applies_persisted_overrides(self):
        db.set_config_value("checkin.points", 25)
        db.set_config_value("chat.daily_limit", 220)

        config = make_config()
        apply_runtime_settings(config)

        self.assertEqual(config.checkin.points, 25)
        self.assertEqual(config.chat.daily_limit, 220)

    def test_apply_runtime_settings_ignores_invalid_override(self):
        db.set_config_value("rank.top_n", 0)

        config = make_config()
        apply_runtime_settings(config)

        self.assertEqual(config.rank.top_n, 10)

    def test_update_runtime_setting_persists_and_updates_config(self):
        config = make_config()

        value = update_runtime_setting(config, "chat.cooldown_seconds", "45")

        self.assertEqual(value, 45)
        self.assertEqual(config.chat.cooldown_seconds, 45)
        self.assertEqual(db.get_config_value("chat.cooldown_seconds"), 45)

    def test_update_runtime_setting_rejects_out_of_range_value(self):
        config = make_config()

        with self.assertRaisesRegex(ValueError, "排行榜显示人数 不能小于 1"):
            update_runtime_setting(config, "rank.top_n", 0)


if __name__ == "__main__":
    unittest.main()
