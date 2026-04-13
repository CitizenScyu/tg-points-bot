import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, r"D:\ClaudeCode\tg-points-bot")

import database as db


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "points_bot.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_group_isolation_keeps_separate_user_rows(self):
        db.get_or_create_user(1001, -100, "alice")
        db.get_or_create_user(1001, -200, "alice")

        db.update_user_points(1001, -100, 10)
        db.update_user_points(1001, -200, 20)

        self.assertEqual(db.get_user_points(1001, -100), 10)
        self.assertEqual(db.get_user_points(1001, -200), 20)
        self.assertEqual(len(db.get_ranking(-100)), 1)
        self.assertEqual(len(db.get_ranking(-200)), 1)

    def test_update_and_set_points_require_existing_group_user(self):
        self.assertIsNone(db.update_user_points(9999, -100, 5))
        self.assertIsNone(db.set_user_points(9999, -100, 5))

    def test_create_lottery_rejects_invalid_values(self):
        with self.assertRaisesRegex(ValueError, "参与费必须大于 0"):
            db.create_lottery(-100, "bad", "gift", 0, 1)

        with self.assertRaisesRegex(ValueError, "最少人数不能小于 1"):
            db.create_lottery(-100, "bad", "gift", 10, 1, 0)

    def test_join_lottery_checks_group_scope(self):
        db.get_or_create_user(1, -100, "alice")
        db.update_user_points(1, -100, 50)
        lottery_id = db.create_lottery(-100, "weekend", "gift", 10, 999)

        success, message = db.join_lottery(lottery_id, -200, 1)
        self.assertFalse(success)
        self.assertEqual(message, "请在创建抽奖的群组中参与")
        self.assertEqual(db.get_user_points(1, -100), 50)

    def test_init_db_migrates_legacy_user_schema(self):
        db_path = db.DB_PATH
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(
                """
                DROP TABLE IF EXISTS users;
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY,
                    group_id INTEGER NOT NULL,
                    username TEXT,
                    points INTEGER DEFAULT 0,
                    last_checkin TEXT,
                    daily_chat_points INTEGER DEFAULT 0,
                    last_chat_date TEXT,
                    last_chat_time TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO users (user_id, group_id, username, points)
                VALUES (1, -100, 'alice', 12);
                """
            )
        finally:
            conn.close()

        db.init_db()

        conn = sqlite3.connect(str(db_path))
        try:
            columns = conn.execute("PRAGMA table_info(users)").fetchall()
            pk_columns = [row[1] for row in columns if row[5]]
            row = conn.execute(
                "SELECT group_id, user_id, username, points FROM users"
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(pk_columns, ["group_id", "user_id"])
        self.assertEqual(row, (-100, 1, "alice", 12))


if __name__ == "__main__":
    unittest.main()
