import logging
from typing import Iterable, Optional

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeChatAdministrators,
)

import database as db

logger = logging.getLogger(__name__)


def _get_bound_group_id(config) -> Optional[int]:
    if config.bot.group_id is not None:
        bound_group_id = int(config.bot.group_id)
        if db.get_bound_group_id() != bound_group_id:
            db.set_bound_group_id(bound_group_id)
        return bound_group_id

    saved_group_id = db.get_bound_group_id()
    if saved_group_id is not None:
        config.bot.group_id = saved_group_id
    return config.bot.group_id


def _has_fixed_group_binding(config) -> bool:
    return getattr(config.bot, "configured_group_id", None) is not None


def _commands(items: Iterable[tuple[str, str]]) -> list[BotCommand]:
    return [BotCommand(command=command, description=description) for command, description in items]


PRIVATE_COMMANDS = _commands(
    [
        ("help", "查看帮助"),
        ("settings", "管理员私聊配置"),
    ]
)

BOT_ADMIN_PRIVATE_COMMANDS = _commands(
    [
        ("help", "查看帮助"),
        ("settings", "管理员私聊配置"),
        ("backup", "手动备份数据"),
        ("restore", "从备份恢复数据"),
    ]
)

ALL_GROUP_COMMANDS = _commands(
    [
        ("help", "查看帮助"),
    ]
)

BOUND_GROUP_MEMBER_COMMANDS = _commands(
    [
        ("help", "查看帮助"),
        ("checkin", "每日签到"),
        ("points", "查看我的积分"),
        ("rank", "查看积分排行"),
        ("lotteries", "查看进行中的抽奖"),
    ]
)

UNBOUND_GROUP_ADMIN_COMMANDS = _commands(
    [
        ("help", "查看帮助"),
        ("bind_group", "绑定当前群组"),
    ]
)


def _build_bound_group_admin_commands(config) -> list[BotCommand]:
    items = [
        ("help", "查看帮助"),
        ("checkin", "每日签到"),
        ("points", "查看我的积分"),
        ("rank", "查看积分排行"),
        ("lotteries", "查看进行中的抽奖"),
        ("lottery", "创建抽奖"),
        ("draw", "手动开奖"),
        ("cancel_lottery", "取消抽奖"),
    ]
    if not _has_fixed_group_binding(config):
        items.append(("unbind_group", "解绑当前群组"))
    return _commands(items)


async def _safe_set_commands(bot: Bot, commands: list[BotCommand], scope) -> None:
    try:
        await bot.set_my_commands(commands=commands, scope=scope)
    except Exception:
        logger.exception("同步 Telegram 命令失败: scope=%s", type(scope).__name__)


async def _safe_delete_commands(bot: Bot, scope) -> None:
    try:
        await bot.delete_my_commands(scope=scope)
    except Exception:
        logger.exception("删除 Telegram 命令作用域失败: scope=%s", type(scope).__name__)


async def sync_bot_commands(bot: Bot, config, *, previous_bound_group_id: Optional[int] = None) -> None:
    bound_group_id = _get_bound_group_id(config)

    await _safe_set_commands(bot, PRIVATE_COMMANDS, BotCommandScopeAllPrivateChats())
    await _safe_set_commands(bot, ALL_GROUP_COMMANDS, BotCommandScopeAllGroupChats())

    for admin_id in config.bot.admin_ids:
        await _safe_set_commands(
            bot,
            BOT_ADMIN_PRIVATE_COMMANDS,
            BotCommandScopeChat(chat_id=admin_id),
        )

    group_scope_ids_to_clear = set()
    if previous_bound_group_id is not None:
        group_scope_ids_to_clear.add(previous_bound_group_id)
    if bound_group_id is None:
        group_scope_ids_to_clear.update(
            group_id for group_id in [getattr(config.bot, "configured_group_id", None)] if group_id is not None
        )

    if bound_group_id is not None:
        await _safe_set_commands(
            bot,
            BOUND_GROUP_MEMBER_COMMANDS,
            BotCommandScopeChat(chat_id=bound_group_id),
        )
        await _safe_set_commands(
            bot,
            _build_bound_group_admin_commands(config),
            BotCommandScopeChatAdministrators(chat_id=bound_group_id),
        )
        await _safe_delete_commands(bot, BotCommandScopeAllChatAdministrators())

        if previous_bound_group_id is not None and previous_bound_group_id != bound_group_id:
            group_scope_ids_to_clear.add(previous_bound_group_id)
    elif not _has_fixed_group_binding(config):
        await _safe_set_commands(
            bot,
            UNBOUND_GROUP_ADMIN_COMMANDS,
            BotCommandScopeAllChatAdministrators(),
        )
    else:
        await _safe_delete_commands(bot, BotCommandScopeAllChatAdministrators())

    for group_id in group_scope_ids_to_clear:
        if bound_group_id is not None and group_id == bound_group_id:
            continue
        await _safe_delete_commands(bot, BotCommandScopeChat(chat_id=group_id))
        await _safe_delete_commands(bot, BotCommandScopeChatAdministrators(chat_id=group_id))
