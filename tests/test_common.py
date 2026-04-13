import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import database as db
from handlers.common import (
    bind_group,
    clear_group_binding,
    ensure_points_group,
    has_group_management_rights,
    is_bound_group_admin,
)


class DummyBot:
    def __init__(self, status="member", fail=False):
        self.status = status
        self.fail = fail

    async def get_chat_member(self, chat_id, user_id):
        if self.fail:
            raise RuntimeError("lookup failed")
        return SimpleNamespace(status=self.status)


class DummyMessage:
    def __init__(self, chat_type="group", chat_id=-100, user_id=1, bot=None):
        self.chat = SimpleNamespace(type=chat_type, id=chat_id)
        self.from_user = SimpleNamespace(id=user_id)
        self.bot = bot or DummyBot()
        self.replies = []

    async def reply(self, text):
        self.replies.append(text)


def make_config(admin_ids=None, group_id=None, configured_group_id=None):
    return SimpleNamespace(
        bot=SimpleNamespace(
            admin_ids=admin_ids or [],
            group_id=group_id,
            configured_group_id=configured_group_id,
        )
    )


class CommonHandlerTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "points_bot.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def test_ensure_points_group_requires_explicit_binding(self):
        config = make_config()
        message = DummyMessage()

        group_id = await ensure_points_group(message, config)

        self.assertIsNone(group_id)
        self.assertIsNone(db.get_bound_group_id())
        self.assertEqual(
            message.replies,
            ["机器人尚未绑定群组，请管理员在目标群发送 /bind_group 或 /绑定群组"],
        )

    async def test_ensure_points_group_returns_bound_group(self):
        config = make_config()
        bind_group(config, -100)
        message = DummyMessage(chat_id=-100)

        group_id = await ensure_points_group(message, config)

        self.assertEqual(group_id, -100)
        self.assertEqual(message.replies, [])

    async def test_clear_group_binding_resets_runtime_and_db_state(self):
        config = make_config()
        bind_group(config, -100)

        clear_group_binding(config)

        self.assertIsNone(config.bot.group_id)
        self.assertIsNone(db.get_bound_group_id())

    async def test_group_management_rights_accept_bot_admin(self):
        config = make_config(admin_ids=[42])
        message = DummyMessage(chat_type="private", user_id=42)

        allowed = await has_group_management_rights(message, config)

        self.assertTrue(allowed)

    async def test_group_management_rights_accept_group_admin(self):
        config = make_config()
        message = DummyMessage(bot=DummyBot(status="administrator"))

        allowed = await has_group_management_rights(message, config)

        self.assertTrue(allowed)

    async def test_is_bound_group_admin_checks_bound_group_membership(self):
        config = make_config()
        bind_group(config, -100)

        allowed = await is_bound_group_admin(DummyBot(status="administrator"), config, 7)

        self.assertTrue(allowed)
