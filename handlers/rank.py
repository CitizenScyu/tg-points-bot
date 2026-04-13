from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message
from html import escape
import database as db
from .common import ensure_points_group
from .utils import schedule_auto_delete

def register_rank_handlers(dp, config):
    async def handle_rank(message: Message):
        group_id = await ensure_points_group(message, config)
        if group_id is None:
            return

        ranking = db.get_ranking(group_id, config.rank.top_n)

        if not ranking:
            reply_msg = await message.reply("还没有人获得积分")
            schedule_auto_delete(message, reply_msg, delay=30)
            return

        text = "积分排行榜\n\n"
        medals = ["🥇", "🥈", "🥉"]

        for i, user in enumerate(ranking, 1):
            medal = medals[i-1] if i <= 3 else f"{i}."
            name = escape(user['username'] or f"用户{user['user_id']}")
            text += f"{medal} {name}: {user['points']} 积分\n"

        reply_msg = await message.reply(text)
        schedule_auto_delete(message, reply_msg, delay=30)

    @dp.message(F.text == "排行榜")
    async def cmd_rank_text(message: Message):
        await handle_rank(message)

    @dp.message(Command("rank"))
    async def cmd_rank_slash(message: Message):
        await handle_rank(message)

    async def handle_points(message: Message):
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
        schedule_auto_delete(message, reply_msg, delay=30)

    @dp.message(F.text == "积分")
    async def cmd_points_text(message: Message):
        await handle_points(message)

    @dp.message(Command("points"))
    async def cmd_points_slash(message: Message):
        await handle_points(message)
