import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import database as db
from telegram_commands import sync_bot_commands


class FakeBot:
    def __init__(self):
        self.set_calls = []
        self.delete_calls = []

    async def set_my_commands(self, commands, scope=None, **kwargs):
        self.set_calls.append((scope, [command.command for command in commands]))
        return True

    async def delete_my_commands(self, scope=None, **kwargs):
        self.delete_calls.append(scope)
        return True


def make_config(*, admin_ids=None, group_id=None, configured_group_id=None):
    return SimpleNamespace(
        bot=SimpleNamespace(
            admin_ids=admin_ids or [],
            group_id=group_id,
            configured_group_id=configured_group_id,
        )
    )


def scope_signature(scope):
    scope_type = type(scope).__name__
    chat_id = getattr(scope, "chat_id", None)
    return scope_type, chat_id


class TelegramCommandsTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "points_bot.db"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def test_sync_bot_commands_sets_bound_group_scopes(self):
        bot = FakeBot()
        config = make_config(admin_ids=[42], group_id=-100)

        await sync_bot_commands(bot, config)

        set_map = {scope_signature(scope): commands for scope, commands in bot.set_calls}

        self.assertEqual(
            set_map[("BotCommandScopeAllPrivateChats", None)],
            ["help", "settings"],
        )
        self.assertEqual(
            set_map[("BotCommandScopeChat", 42)],
            ["help", "settings", "backup", "restore"],
        )
        self.assertEqual(
            set_map[("BotCommandScopeChat", -100)],
            ["help", "checkin", "points", "rank", "lotteries"],
        )
        self.assertIn(
            "lottery",
            set_map[("BotCommandScopeChatAdministrators", -100)],
        )
        self.assertIn(
            "unbind_group",
            set_map[("BotCommandScopeChatAdministrators", -100)],
        )
        self.assertIn(
            ("BotCommandScopeAllChatAdministrators", None),
            [scope_signature(scope) for scope in bot.delete_calls],
        )

    async def test_sync_bot_commands_clears_old_scopes_and_exposes_bind_when_unbound(self):
        bot = FakeBot()
        config = make_config(admin_ids=[42], group_id=None, configured_group_id=None)

        await sync_bot_commands(bot, config, previous_bound_group_id=-100)

        set_map = {scope_signature(scope): commands for scope, commands in bot.set_calls}
        deleted_scopes = [scope_signature(scope) for scope in bot.delete_calls]

        self.assertEqual(
            set_map[("BotCommandScopeAllChatAdministrators", None)],
            ["help", "bind_group"],
        )
        self.assertIn(("BotCommandScopeChat", -100), deleted_scopes)
        self.assertIn(("BotCommandScopeChatAdministrators", -100), deleted_scopes)

    async def test_sync_bot_commands_omits_unbind_for_fixed_group_binding(self):
        bot = FakeBot()
        config = make_config(admin_ids=[42], group_id=-100, configured_group_id=-100)

        await sync_bot_commands(bot, config)

        set_map = {scope_signature(scope): commands for scope, commands in bot.set_calls}
        self.assertNotIn(
            "unbind_group",
            set_map[("BotCommandScopeChatAdministrators", -100)],
        )


if __name__ == "__main__":
    unittest.main()
