from aiogram import F
from aiogram.types import Message
from html import escape
import database as db
import asyncio
from .common import ensure_points_group

async def auto_delete(message: Message, reply_msg: Message, delay: int = 30):
    """自动删除触发消息和机器人回复"""
    await asyncio.sleep(delay)
    try:
        await message.delete()
        await reply_msg.delete()
    except:
        pass

def register_rank_handlers(dp, config):
    # 排行榜 - 直接汉字触发
    @dp.message(F.text == "排行榜")
    async def cmd_rank(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        ranking = db.get_ranking(group_id, config.rank.top_n)

        if not ranking:
            reply_msg = await message.reply("还没有人获得积分")
            asyncio.create_task(auto_delete(message, reply_msg, delay=30))
            return

        text = "积分排行榜\n\n"
        medals = ["🥇", "🥈", "🥉"]

        for i, user in enumerate(ranking, 1):
            medal = medals[i-1] if i <= 3 else f"{i}."
            name = escape(user['username'] or f"用户{user['user_id']}")
            text += f"{medal} {name}: {user['points']} 积分\n"

        reply_msg = await message.reply(text)
        asyncio.create_task(auto_delete(message, reply_msg, delay=30))

    # 积分 - 直接汉字触发
    @dp.message(F.text == "积分")
    async def cmd_my_points(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.full_name

        user = db.get_or_create_user(user_id, group_id, username)

        reply_msg = await message.reply(
            f"当前积分：{user['points']}\n"
            f"今日聊天积分：{user.get('daily_chat_points', 0)}/{config.chat.daily_limit}"
        )
        asyncio.create_task(auto_delete(message, reply_msg, delay=30))
