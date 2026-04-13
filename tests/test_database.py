import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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

    def test_update_user_points_rejects_negative_balance(self):
        db.get_or_create_user(1001, -100, "alice")
        db.update_user_points(1001, -100, 5)

        self.assertIsNone(db.update_user_points(1001, -100, -10))
        self.assertEqual(db.get_user_points(1001, -100), 5)

    def test_set_user_points_rejects_negative_value(self):
        db.get_or_create_user(1001, -100, "alice")

        with self.assertRaisesRegex(ValueError, "积分不能小于 0"):
            db.set_user_points(1001, -100, -1)

    def test_create_lottery_rejects_invalid_values(self):
        with self.assertRaisesRegex(ValueError, "参与费必须大于 0"):
            db.create_lottery(-100, "bad", "gift", 0, 1)

        with self.assertRaisesRegex(ValueError, "最少人数不能小于 1"):
            db.create_lottery(-100, "bad", "gift", 10, 1, 0)

        with self.assertRaisesRegex(ValueError, "按时间开奖必须设置开奖时间"):
            db.create_lottery(-100, "bad", "gift", 10, 1, draw_mode="time")

    def test_join_lottery_checks_group_scope(self):
        db.get_or_create_user(1, -100, "alice")
        db.update_user_points(1, -100, 50)
        lottery_id = db.create_lottery(-100, "weekend", "gift", 10, 999)

        success, message = db.join_lottery(lottery_id, -200, 1)
        self.assertFalse(success)
        self.assertEqual(message, "请在创建抽奖的群组中参与")
        self.assertEqual(db.get_user_points(1, -100), 50)

    def test_join_lottery_auto_finishes_when_participant_threshold_is_reached(self):
        db.get_or_create_user(1, -100, "alice")
        db.get_or_create_user(2, -100, "bob")
        db.update_user_points(1, -100, 50)
        db.update_user_points(2, -100, 50)

        lottery_id = db.create_lottery(
            -100,
            "weekend",
            "gift",
            10,
            999,
            min_participants=2,
            draw_mode="participant_count",
        )

        first_result = db.join_lottery_with_result(lottery_id, -100, 1)
        second_result = db.join_lottery_with_result(lottery_id, -100, 2)

        self.assertTrue(first_result["success"])
        self.assertFalse(first_result["auto_finished"])
        self.assertTrue(second_result["success"])
        self.assertTrue(second_result["auto_finished"])
        self.assertIn(second_result["winner_id"], [1, 2])
        self.assertEqual(db.get_lottery(lottery_id, -100)["status"], "finished")

    def test_settle_due_time_lottery_refunds_when_participants_are_insufficient(self):
        db.get_or_create_user(1, -100, "alice")
        db.update_user_points(1, -100, 50)
        lottery_id = db.create_lottery(
            -100,
            "deadline",
            "gift",
            10,
            999,
            min_participants=2,
            end_time="2026-04-13T10:00:00",
            draw_mode="time",
        )
        join_result = db.join_lottery_with_result(lottery_id, -100, 1)

        settlement = db.settle_due_time_lottery(lottery_id, -100)

        self.assertTrue(join_result["success"])
        self.assertEqual(settlement["status"], "cancelled")
        self.assertEqual(settlement["reason"], "insufficient_participants")
        self.assertEqual(db.get_user_points(1, -100), 50)
        self.assertEqual(db.get_lottery(lottery_id, -100)["status"], "cancelled")

    def test_set_lottery_announcement_message_persists_message_reference(self):
        lottery_id = db.create_lottery(-100, "weekly", "gift", 10, 1)

        updated = db.set_lottery_announcement_message(lottery_id, -100, -100, 321)
        lottery = db.get_lottery(lottery_id, -100)

        self.assertTrue(updated)
        self.assertEqual(lottery["announcement_chat_id"], -100)
        self.assertEqual(lottery["announcement_message_id"], 321)

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

    def test_init_db_adds_draw_mode_to_legacy_lottery_schema(self):
        db_path = db.DB_PATH
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(
                """
                DROP TABLE IF EXISTS lotteries;
                CREATE TABLE lotteries (
                    lottery_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    prize TEXT NOT NULL,
                    cost INTEGER NOT NULL,
                    creator_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'active',
                    min_participants INTEGER DEFAULT 1,
                    end_time TEXT,
                    winner_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT
                );
                INSERT INTO lotteries (group_id, title, prize, cost, creator_id)
                VALUES (-100, 'legacy', 'gift', 10, 1);
                """
            )
        finally:
            conn.close()

        db.init_db()

        conn = sqlite3.connect(str(db_path))
        try:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(lotteries)").fetchall()]
            draw_mode = conn.execute("SELECT draw_mode FROM lotteries").fetchone()[0]
        finally:
            conn.close()

        self.assertIn("draw_mode", columns)
        self.assertIn("announcement_chat_id", columns)
        self.assertIn("announcement_message_id", columns)
        self.assertEqual(draw_mode, "manual")


if __name__ == "__main__":
    unittest.main()
