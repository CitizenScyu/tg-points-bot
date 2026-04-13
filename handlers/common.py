from typing import Optional

from aiogram.types import Message

import database as db

GROUP_CHAT_TYPES = {"group", "supergroup"}


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


async def ensure_points_group(
    message: Message,
    config,
    *,
    reply_on_private: bool = True,
    reply_on_mismatch: bool = True,
) -> Optional[int]:
    if message.chat.type not in GROUP_CHAT_TYPES:
        if reply_on_private:
            await message.reply("请在已绑定的群组中使用此功能")
        return None

    bound_group_id = get_bound_group_id(config)
    if bound_group_id is None:
        bound_group_id = message.chat.id
        db.set_bound_group_id(bound_group_id)
        config.bot.group_id = bound_group_id

    if message.chat.id != bound_group_id:
        if reply_on_mismatch:
            await message.reply("此机器人只服务已绑定的群组")
        return None

    return message.chat.id
