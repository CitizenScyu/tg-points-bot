from typing import Optional

from aiogram.types import Message

import database as db

GROUP_CHAT_TYPES = {"group", "supergroup"}
GROUP_MANAGER_STATUSES = {"administrator", "creator"}


def get_bound_group_id(config) -> Optional[int]:
    if config.bot.group_id is not None:
        bound_group_id = int(config.bot.group_id)
        if db.get_bound_group_id() != bound_group_id:
            db.set_bound_group_id(bound_group_id)
        return bound_group_id

    saved_group_id = db.get_bound_group_id()
    if saved_group_id is not None:
        config.bot.group_id = saved_group_id
    return config.bot.group_id


def has_fixed_group_binding(config) -> bool:
    return getattr(config.bot, "configured_group_id", None) is not None


def bind_group(config, group_id: int) -> None:
    db.set_bound_group_id(group_id)
    config.bot.group_id = group_id


def clear_group_binding(config) -> None:
    db.clear_bound_group_id()
    config.bot.group_id = None


def is_bot_admin(config, user_id: int) -> bool:
    return user_id in config.bot.admin_ids


async def is_group_admin(message: Message, user_id: Optional[int] = None) -> bool:
    if message.chat.type not in GROUP_CHAT_TYPES:
        return False

    target_user_id = user_id or message.from_user.id
    return await is_group_admin_by_chat_id(message.bot, message.chat.id, target_user_id)


async def is_group_admin_by_chat_id(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in GROUP_MANAGER_STATUSES


async def has_group_management_rights(message: Message, config) -> bool:
    return is_bot_admin(config, message.from_user.id) or await is_group_admin(message)


async def is_bound_group_admin(bot, config, user_id: int) -> bool:
    bound_group_id = get_bound_group_id(config)
    if bound_group_id is None:
        return False
    return await is_group_admin_by_chat_id(bot, bound_group_id, user_id)


async def ensure_points_group(
    message: Message,
    config,
    *,
    reply_on_private: bool = True,
    reply_on_mismatch: bool = True,
    reply_on_unbound: bool = True,
) -> Optional[int]:
    if message.chat.type not in GROUP_CHAT_TYPES:
        if reply_on_private:
            await message.reply("请在已绑定的群组中使用此功能")
        return None

    bound_group_id = get_bound_group_id(config)
    if bound_group_id is None:
        if reply_on_unbound:
            await message.reply("机器人尚未绑定群组，请管理员在目标群发送 /bind_group 或 /绑定群组")
        return None

    if message.chat.id != bound_group_id:
        if reply_on_mismatch:
            await message.reply("此机器人只服务已绑定的群组")
        return None

    return message.chat.id
